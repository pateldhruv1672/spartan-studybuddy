from __future__ import annotations

import json
import uuid
from typing import Any

from ..db import db


def create_roadmap(owner_user_id: str, title: str, goal: str, description: str, is_public: bool, items: list[dict[str, Any]]) -> dict[str, Any]:
    roadmap_id = str(uuid.uuid4())
    with db() as conn:
        conn.execute(
            "INSERT INTO roadmaps(id,owner_user_id,title,goal,description,is_public) VALUES(?,?,?,?,?,?)",
            (roadmap_id, owner_user_id, title, goal, description, int(is_public)),
        )
        conn.execute("INSERT INTO roadmap_members(roadmap_id,user_id,xp) VALUES(?,?,0)", (roadmap_id, owner_user_id))
        for pos, item in enumerate(items):
            iid = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO roadmap_items(id,roadmap_id,position,title,kind,resource_url,source,estimated_minutes,metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (iid, roadmap_id, pos, item["title"], item.get("kind", "lesson"), item.get("resource_url"), item.get("source"), int(item.get("estimated_minutes", 15)), json.dumps(item.get("metadata", {}))),
            )
    return get_roadmap(roadmap_id, owner_user_id)


def get_roadmap(roadmap_id: str, user_id: str | None = None) -> dict[str, Any]:
    with db() as conn:
        r = conn.execute("SELECT * FROM roadmaps WHERE id=?", (roadmap_id,)).fetchone()
        if not r:
            raise KeyError(roadmap_id)
        items = conn.execute("SELECT * FROM roadmap_items WHERE roadmap_id=? ORDER BY position", (roadmap_id,)).fetchall()
        members = conn.execute("SELECT user_id,xp FROM roadmap_members WHERE roadmap_id=? ORDER BY xp DESC", (roadmap_id,)).fetchall()
        resources = conn.execute("SELECT * FROM roadmap_resources WHERE roadmap_id=? ORDER BY order_index, created_at", (roadmap_id,)).fetchall()
        progress = {}
        if user_id:
            progress = {row[0]: {"status": row[1], "progress": row[2]} for row in conn.execute(
                "SELECT roadmap_item_id,status,progress FROM progress WHERE user_id=? AND roadmap_item_id IN (SELECT id FROM roadmap_items WHERE roadmap_id=?)",
                (user_id, roadmap_id),
            ).fetchall()}
    result = dict(r)
    result["is_public"] = bool(result["is_public"])
    result["items"] = []
    for row in items:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["progress_state"] = progress.get(item["id"], {"status": "not_started", "progress": 0})
        result["items"].append(item)
    result["leaderboard"] = [dict(m) for m in members]
    result["resources"] = []
    for row in resources:
        resource = dict(row)
        resource["metadata"] = json.loads(resource.pop("metadata_json") or "{}")
        result["resources"].append(resource)
    return result


def add_resources(roadmap_id: str, resources: list[dict[str, Any]]) -> int:
    count = 0
    with db() as conn:
        for i, resource in enumerate(resources):
            url = str(resource.get("url") or "").strip()
            title = str(resource.get("title") or "").strip()
            if not url or not title:
                continue
            rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{roadmap_id}:{url}"))
            conn.execute(
                """INSERT INTO roadmap_resources(id,roadmap_id,title,url,resource_type,source,rationale,order_index,metadata_json)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET roadmap_id=excluded.roadmap_id,title=excluded.title,url=excluded.url,
                resource_type=excluded.resource_type,source=excluded.source,rationale=excluded.rationale,
                order_index=excluded.order_index,metadata_json=excluded.metadata_json""",
                (rid, roadmap_id, title, url, resource.get("resource_type") or resource.get("type"), resource.get("source"), resource.get("why") or resource.get("rationale"), i, json.dumps(resource.get("metadata", {}))),
            )
            count += 1
    return count


def list_roadmaps(user_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT r.* FROM roadmaps r LEFT JOIN roadmap_members m ON m.roadmap_id=r.id
               WHERE r.is_public=1 OR r.owner_user_id=? OR m.user_id=? ORDER BY r.created_at DESC""",
            (user_id, user_id),
        ).fetchall()
    return [dict(r) | {"is_public": bool(r["is_public"])} for r in rows]


def join_roadmap(roadmap_id: str, user_id: str) -> None:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO roadmap_members(roadmap_id,user_id,xp) VALUES(?,?,0)", (roadmap_id, user_id))


def update_progress(item_id: str, user_id: str, status: str, progress: float) -> dict[str, Any]:
    xp_delta = 0
    with db() as conn:
        old = conn.execute("SELECT status FROM progress WHERE user_id=? AND roadmap_item_id=?", (user_id, item_id)).fetchone()
        if status == "completed" and (not old or old[0] != "completed"):
            xp_delta = 100
        conn.execute(
            """INSERT INTO progress(user_id,roadmap_item_id,status,progress) VALUES(?,?,?,?)
               ON CONFLICT(user_id,roadmap_item_id) DO UPDATE SET status=excluded.status,progress=excluded.progress,updated_at=CURRENT_TIMESTAMP""",
            (user_id, item_id, status, progress),
        )
        roadmap = conn.execute("SELECT roadmap_id FROM roadmap_items WHERE id=?", (item_id,)).fetchone()
        if roadmap and xp_delta:
            conn.execute("UPDATE roadmap_members SET xp=xp+? WHERE roadmap_id=? AND user_id=?", (xp_delta, roadmap[0], user_id))
    return {"item_id": item_id, "status": status, "progress": progress, "xp_delta": xp_delta}
