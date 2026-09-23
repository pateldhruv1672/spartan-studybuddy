#!/usr/bin/env python3
"""Experimental, approval-gated Mac computer-use executor.

This is intentionally NOT autonomous. It executes a tiny allowlist of explicit
GUI actions after printing them for human approval. A VLM/planner can submit a
`computer_use` job, but this bridge remains the safety boundary on the Mac.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

ENABLED = os.getenv("ENABLE_STUDYBUDDY_COMPUTER_USE", "0") == "1"


def execute_actions(actions: list[dict[str, Any]]) -> dict[str, Any]:
    if not ENABLED:
        return {"ok": False, "error": "Set ENABLE_STUDYBUDDY_COMPUTER_USE=1 on the Mac to enable explicit GUI actions."}
    try:
        import pyautogui
    except Exception as exc:
        return {"ok": False, "error": f"pyautogui unavailable: {exc}"}

    allowed = {"move", "click", "scroll", "type", "hotkey"}
    for action in actions:
        if action.get("type") not in allowed:
            return {"ok": False, "error": f"Blocked action type: {action.get('type')}"}

    print(json.dumps(actions, indent=2))
    if input("Execute these GUI actions? [y/N] ").strip().lower() != "y":
        return {"ok": False, "declined": True}

    for a in actions:
        t = a["type"]
        if t == "move": pyautogui.moveTo(a["x"], a["y"], duration=0.2)
        elif t == "click": pyautogui.click(a.get("x"), a.get("y"), clicks=int(a.get("clicks", 1)))
        elif t == "scroll": pyautogui.scroll(int(a.get("amount", 0)))
        elif t == "type": pyautogui.write(str(a.get("text", "")), interval=0.015)
        elif t == "hotkey": pyautogui.hotkey(*a.get("keys", []))
        time.sleep(0.15)
    return {"ok": True, "actions_executed": len(actions)}
