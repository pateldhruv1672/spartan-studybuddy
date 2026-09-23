#!/usr/bin/env python3
"""Mac-side Browser-Use bridge for Spartan StudyBuddy.

The bridge polls agent jobs from the DGX Spark, attaches Browser-Use to the
StudyBuddy Chrome instance on the Mac (preferably via CDP), and uses a LOCAL
model served by the Spark. Default path:

Mac Chrome --CDP--> browser-use --HTTPS/LAN--> StudyBuddy proxy --> vLLM

The default path reuses the locally served Spartan Teacher model in DOM/text mode to keep the 128 GB Spark memory budget predictable. A dedicated browser-use/bu-30b-a3b-preview profile and Ollama remain optional.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import webbrowser
from typing import Any

import httpx

API_BASE = os.getenv("STUDYBUDDY_API", "http://127.0.0.1:8000").rstrip("/")
BRIDGE_TOKEN = os.getenv("STUDYBUDDY_BRIDGE_TOKEN", "spartan-local-bridge")
BROWSER_PROVIDER = os.getenv("STUDYBUDDY_BROWSER_PROVIDER", "vllm-proxy").lower()
BROWSER_MODEL = os.getenv("STUDYBUDDY_BROWSER_MODEL", "spartan-teacher")
OLLAMA_MODEL = os.getenv("STUDYBUDDY_OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_BASE_URL = os.getenv("STUDYBUDDY_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_NUM_CTX = int(os.getenv("STUDYBUDDY_OLLAMA_NUM_CTX", "32768"))
CDP_URL = os.getenv("STUDYBUDDY_CDP_URL", "http://127.0.0.1:9222")
CHROME_PROFILE = os.getenv("STUDYBUDDY_CHROME_PROFILE", "Default")
POLL_SECONDS = float(os.getenv("STUDYBUDDY_BRIDGE_POLL", "2"))
MAX_STEPS = int(os.getenv("STUDYBUDDY_BROWSER_MAX_STEPS", "25"))
FLASH_MODE = os.getenv("STUDYBUDDY_BROWSER_FLASH_MODE", "1") == "1"
USE_VISION = os.getenv("STUDYBUDDY_BROWSER_USE_VISION", "0") == "1"


async def get_jobs() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{API_BASE}/api/agent/jobs/claim?limit=5")
        r.raise_for_status()
        return r.json()


async def complete_job(job_id: str, result: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_BASE}/api/agent/jobs/{job_id}/complete", json=result)
        r.raise_for_status()


def _build_llm():
    """Build a Browser-Use LLM without any paid/cloud AI dependency."""
    if BROWSER_PROVIDER == "ollama":
        from browser_use import ChatOllama

        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            num_ctx=OLLAMA_NUM_CTX,
        )

    # Default: the Mac calls only StudyBuddy's authenticated proxy. The raw
    # vLLM browser-model port remains bound to 127.0.0.1 on the Spark.
    from browser_use import ChatOpenAI

    return ChatOpenAI(
        model=BROWSER_MODEL,
        base_url=f"{API_BASE}/agent-llm/v1",
        api_key=BRIDGE_TOKEN,
        temperature=0.6,
        top_p=0.95,
        # Avoid forcing a second schema layer; Browser-Use performs its own action parsing.
        dont_force_structured_output=True,
    )


def _build_browser():
    """Attach to the visible StudyBuddy Chrome, preserving logins/extensions."""
    from browser_use import Browser

    if CDP_URL:
        return Browser(cdp_url=CDP_URL)
    return Browser.from_system_chrome(profile_directory=CHROME_PROFILE)


async def run_browser_use(task: str) -> dict[str, Any]:
    try:
        from browser_use import Agent
    except Exception as exc:
        return {
            "ok": False,
            "error": "browser-use is not installed on this Mac bridge",
            "detail": str(exc),
            "install": "Run scripts/mac/setup_browser_use.sh",
        }

    try:
        llm = _build_llm()
        browser = _build_browser()
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            use_vision=USE_VISION,
            max_actions_per_step=2,
            flash_mode=FLASH_MODE,
        )
        history = await agent.run(max_steps=MAX_STEPS)
        final = history.final_result() if hasattr(history, "final_result") else str(history)
    except Exception as exc:
        return {
            "ok": False,
            "error": "Browser-Use execution failed",
            "detail": f"{type(exc).__name__}: {exc}",
            "provider": BROWSER_PROVIDER,
            "model": OLLAMA_MODEL if BROWSER_PROVIDER == "ollama" else BROWSER_MODEL,
            "cdp_url": CDP_URL,
        }

    parsed = None
    if isinstance(final, str):
        candidate = final.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.S)
        try:
            parsed = json.loads(candidate)
        except Exception:
            parsed = None
    if isinstance(parsed, dict):
        return {"ok": True, "provider": BROWSER_PROVIDER, "final_result": final, **parsed}
    return {"ok": True, "provider": BROWSER_PROVIDER, "final_result": final}


async def execute(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") or {}
    kind = job.get("kind")
    if kind == "open_resource":
        url = payload.get("url")
        if not url:
            return {"ok": False, "error": "missing url"}
        webbrowser.open(url)
        return {"ok": True, "opened": url}

    if kind in {"resource_scout", "web_research"}:
        seed = payload.get("seed_url")
        query = payload.get("query") or payload.get("instruction") or payload.get("task") or "Find high-quality learning resources."
        plan = payload.get("plan", "")
        task = (
            "You are the browser-side resource scout for Spartan StudyBuddy. "
            "Use public web resources and the user's already-authenticated browser session where appropriate. "
            "Do not use paid AI APIs. Prefer official documentation, university material, primary research, "
            "reputable technical blogs, high-quality YouTube educational videos, and library catalog metadata. "
            "Return ONLY a JSON object. Include a resources array. Each resource must have: title, url, "
            "resource_type, source, difficulty, why, recommended_order, estimated_minutes, topic. If this is web_research, also include synthesis and evidence_notes. Prefer arXiv/primary papers for research claims. Do not wrap JSON in markdown. Never bypass paywalls, DRM, access controls, "
            "CAPTCHAs, or institutional restrictions. If a site requires a human login/MFA step, stop and report it.\n\n"
            f"Task: {query}\nSeed URL: {seed or 'none'}\nResearch plan: {plan}"
        )
        return await run_browser_use(task)

    if kind == "computer_use":
        return {
            "ok": False,
            "error": "computer_use jobs require bridges/computer_use_executor.py and explicit local approval",
        }

    return {"ok": False, "error": f"unsupported job kind: {kind}"}


async def main() -> None:
    seen: set[str] = set()
    print(f"Spartan StudyBuddy Mac bridge -> {API_BASE}")
    print(f"Browser provider: {BROWSER_PROVIDER}; CDP: {CDP_URL or 'system Chrome'}")
    while True:
        try:
            jobs = await get_jobs()
            for job in jobs:
                if job["id"] in seen:
                    continue
                seen.add(job["id"])
                if job.get("requires_approval"):
                    print("\nApproval required:")
                    print(json.dumps({"kind": job["kind"], "payload": job.get("payload")}, indent=2))
                    answer = input("Execute this job? [y/N] ").strip().lower()
                    if answer != "y":
                        await complete_job(job["id"], {"ok": False, "declined": True})
                        continue
                print(f"Executing {job['kind']} ({job['id'][:8]})...")
                result = await execute(job)
                await complete_job(job["id"], result)
                print("Done.")
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"Bridge warning: {exc}", file=sys.stderr)
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
