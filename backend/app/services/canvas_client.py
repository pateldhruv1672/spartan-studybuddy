from __future__ import annotations

import html
import re
from typing import Any
import httpx

from .indexer import index_bytes, index_text


class CanvasClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}

    async def _get(self, path_or_url: str, params: dict[str, Any] | None = None) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}{path_or_url}"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def _get_bytes(self, url: str) -> tuple[bytes, str | None]:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            r = await client.get(url, headers=self.headers)
            r.raise_for_status()
            return r.content, r.headers.get("content-type")

    async def courses(self) -> list[dict[str, Any]]:
        return await self._get("/api/v1/courses", {"enrollment_state": "active", "per_page": 100})

    async def sync_course(
        self,
        *,
        user_id: str,
        course_id: str,
        include_files: bool = True,
        include_pages: bool = True,
        include_assignments: bool = True,
    ) -> dict[str, Any]:
        stats = {"course_id": course_id, "files": 0, "pages": 0, "assignments": 0, "errors": []}
        if include_assignments:
            try:
                assignments = await self._get(f"/api/v1/courses/{course_id}/assignments", {"per_page": 100})
                for a in assignments:
                    body = _html_to_text(a.get("description") or "")
                    content = f"Assignment: {a.get('name','')}\nDue: {a.get('due_at')}\n\n{body}"
                    index_text(
                        user_id=user_id, source_type="canvas_assignment", source_name=a.get("name") or f"assignment-{a.get('id')}",
                        source_uri=a.get("html_url"), course_id=course_id, content=content,
                        metadata={"canvas_id": a.get("id"), "due_at": a.get("due_at")},
                        document_id=f"canvas:{course_id}:assignment:{a.get('id')}",
                    )
                    stats["assignments"] += 1
            except Exception as exc:
                stats["errors"].append(f"assignments: {exc}")
        if include_pages:
            try:
                pages = await self._get(f"/api/v1/courses/{course_id}/pages", {"per_page": 100})
                for p in pages:
                    detail = await self._get(f"/api/v1/courses/{course_id}/pages/{p['url']}")
                    index_text(
                        user_id=user_id, source_type="canvas_page", source_name=detail.get("title") or p["url"],
                        source_uri=detail.get("html_url"), course_id=course_id,
                        content=_html_to_text(detail.get("body") or ""),
                        metadata={"canvas_url": p["url"]}, document_id=f"canvas:{course_id}:page:{p['url']}",
                    )
                    stats["pages"] += 1
            except Exception as exc:
                stats["errors"].append(f"pages: {exc}")
        if include_files:
            try:
                files = await self._get(f"/api/v1/courses/{course_id}/files", {"per_page": 100})
                for f in files:
                    try:
                        data, content_type = await self._get_bytes(f["url"])
                        index_bytes(
                            user_id=user_id, source_type="canvas_file", source_name=f.get("display_name") or f.get("filename") or str(f.get("id")),
                            source_uri=f.get("url"), course_id=course_id, data=data, mime_type=content_type or f.get("content-type"),
                            metadata={"canvas_id": f.get("id"), "size": f.get("size")},
                            document_id=f"canvas:{course_id}:file:{f.get('id')}",
                        )
                        stats["files"] += 1
                    except Exception as exc:
                        stats["errors"].append(f"file {f.get('id')}: {exc}")
            except Exception as exc:
                stats["errors"].append(f"files: {exc}")
        return stats


def _html_to_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()
