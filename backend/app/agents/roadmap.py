from __future__ import annotations

import re
from typing import Any
from ..services.model_router import router
from ..services.roadmaps import create_roadmap
from ..services.jobs import create_job


def _topics(goal: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}", goal)
    stop = {"learn","want","with","from","that","this","into","build","weeks","week","hours","roadmap","and","the","for","using"}
    candidates = []
    for w in words:
        if w.lower() not in stop and w.lower() not in [x.lower() for x in candidates]:
            candidates.append(w)
    return candidates[:5] or ["Foundations", "Practice"]


async def build_roadmap(user_id: str, goal: str, title: str | None, weeks: int, hours_per_week: int, background: str, is_public: bool) -> dict[str, Any]:
    topics = _topics(goal)
    system = "You design concise, prerequisite-aware learning roadmaps. Return a short rationale, not JSON."
    rationale = await router.complete(system=system, user=f"Goal: {goal}\nBackground: {background}\nWeeks: {weeks}\nHours/week: {hours_per_week}\nLikely topics: {topics}", tier="reasoning", max_tokens=450)
    items: list[dict[str, Any]] = []
    for topic in topics:
        items.extend([
            {"title": f"{topic}: first principles", "kind": "lesson", "source": "resource-scout", "estimated_minutes": 25, "metadata": {"topic": topic, "phase": "learn"}},
            {"title": f"{topic}: guided practice", "kind": "practice", "source": "studybuddy", "estimated_minutes": 35, "metadata": {"topic": topic, "phase": "practice"}},
            {"title": f"{topic}: mastery checkpoint", "kind": "quiz", "source": "studybuddy", "estimated_minutes": 15, "metadata": {"topic": topic, "phase": "check"}},
        ])
    items.append({"title": "Capstone: connect the concepts", "kind": "project", "source": "studybuddy", "estimated_minutes": max(60, hours_per_week * 20), "metadata": {"phase": "build"}})
    roadmap = create_roadmap(user_id, title or f"{goal[:54]} Roadmap", goal, rationale, is_public, items)
    scout = create_job(user_id, "browser_resource_scout", {
        "mode": "roadmap", "roadmap_id": roadmap["id"], "goal": goal, "topics": topics,
        "task": f"Curate an ordered learning-resource list for: {goal}. Include strong YouTube tutorials, official/technical references, important blog posts, and SJSU/O'Reilly catalog resources when relevant. Recommend specific chapters/sections by title when discoverable; do not copy protected book text."
    }, requires_approval=False)
    roadmap["resource_scout_job"] = scout
    return roadmap
