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
import base64
import json
import os
import ipaddress
import socket
import re
import sys
import webbrowser
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import BaseModel

API_BASE = os.getenv("STUDYBUDDY_API", "http://127.0.0.1:8000").rstrip("/")
BRIDGE_TOKEN = os.getenv("STUDYBUDDY_BRIDGE_TOKEN", "")
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
# Bounded, not unlimited: all concurrent scouts share one Chrome instance (many tabs/renderer
# processes at once) and one shared light8b model behind the Spark's /agent-llm proxy.
MAX_CONCURRENT_SCOUTS = int(os.getenv("STUDYBUDDY_BROWSER_MAX_CONCURRENT_SCOUTS", "3"))


async def get_jobs() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{API_BASE}/api/agent/jobs/claim?limit=5", headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
        r.raise_for_status()
        return r.json()


async def complete_job(job_id: str, result: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_BASE}/api/agent/jobs/{job_id}/complete", json=result, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
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
        # False lets vLLM's guided/constrained decoding enforce the action JSON schema.
        # Verified fix: with True, our model emitted malformed actions like
        # {"click": 21062} instead of {"click": {"index": 21062}}.
        dont_force_structured_output=False,
    )


def _build_browser():
    """Attach to the visible StudyBuddy Chrome, preserving logins/extensions.

    keep_alive=True is required for the post-run screenshot/video-duration capture in
    run_browser_use() to work at all: Agent.run() calls self.close() internally right before
    returning, which (without keep_alive) calls browser_session.kill() and tears down the CDP root
    client -- confirmed directly via a live bridge log showing "AssertionError: Root CDP client not
    initialized" on 100% of screenshot attempts, even on fully successful runs. Our own code still
    explicitly closes the tabs/session afterward in run_browser_use()'s finally block once it's done
    reading from the page, so nothing actually leaks by skipping Agent's own auto-close."""
    from browser_use import Browser

    if CDP_URL:
        return Browser(cdp_url=CDP_URL, keep_alive=True)
    return Browser.from_system_chrome(profile_directory=CHROME_PROFILE, keep_alive=True)


class _ScoutResource(BaseModel):
    title: str
    url: str
    resource_type: str
    source: str
    difficulty: str
    why: str
    recommended_order: int = 1
    estimated_minutes: int = 15
    topic: str


class _ScoutOutput(BaseModel):
    """Forces the agent's final `done` action to match this shape via guided decoding, instead of
    letting it end the run with a prose summary -- measured directly: a run that found real, correct
    resources (GeeksforGeeks, Medium, GitHub, a YouTube video) still failed because `done` returned
    free text instead of the required JSON object, and run_browser_use()'s parser had nothing to parse."""
    resources: list[_ScoutResource]
    synthesis: str = ""
    evidence_notes: list[str] = []


class _ArxivSearchAction(BaseModel):
    query: str


def _build_tools():
    """'navigate' (free-form typed URL) is EXCLUDED entirely, not just validated. Every failure mode
    hit this session -- reasoning text leaking into a URL, JSON syntax glued onto a URL, guessed
    domains that don't resolve, and plausible-looking-but-fake URLs/anchors like
    '#content-section-1234567890' that pass syntactic validation but were never real -- was the model
    typing a URL out of its own head. A syntax validator (an earlier version of this function) can
    only catch garbage that LOOKS malformed; it can't catch a clean-looking but entirely invented URL.
    Removing the ability to type a URL at all removes the whole failure class: 'search' builds a
    search-engine URL itself from the query (the model can't hallucinate a domain), and 'click' can
    only act on an index that actually exists in the current page's real DOM (the model can't
    hallucinate a click target). 'go_back' (still enabled) covers returning to search results.

    Also adds arxiv_search: hits arXiv's own public Atom API directly for academic-paper topics,
    instead of trying to reach arxiv.org through search+click.

    Also excludes every action irrelevant to "find one resource, read it, call done" (file
    upload/download-form actions, dropdowns, keystrokes, tab switching, raw JS eval, PDF export,
    file writing, closing tabs -- we close tabs ourselves) -- measured directly: with the full ~23
    action set (each one a candidate the model's structured output has to correctly discriminate
    between on every step), a step occasionally came back as "Model returned empty action" and then
    a hard Pydantic validation dump trying to match it against all 23 action shapes and failing
    every one. Fewer live choices in the guided-decoding grammar per step is a smaller, easier
    target to hit correctly."""
    from browser_use.tools.service import Tools
    from browser_use.agent.views import ActionResult

    tools = Tools(exclude_actions=[
        'navigate', 'input', 'upload_file', 'select_dropdown', 'dropdown_options', 'send_keys',
        'switch', 'save_as_pdf', 'write_file', 'replace_file', 'evaluate', 'close', 'screenshot',
    ])

    @tools.action('Search arXiv.org directly for academic/research papers on a topic. Returns real, verified paper titles, URLs and abstracts -- more reliable than trying to reach arXiv through a general web search. Use this for research-paper-style topics.', param_model=_ArxivSearchAction)
    async def arxiv_search(params: _ArxivSearchAction, browser_session):
        import xml.etree.ElementTree as ET
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get('https://export.arxiv.org/api/query', params={'search_query': f'all:{params.query}', 'start': 0, 'max_results': 5})
            entries = ET.fromstring(r.text).findall('atom:entry', ns)
        except Exception as exc:
            return ActionResult(error=f'arXiv search failed: {exc}')
        if not entries:
            return ActionResult(error=f'No arXiv papers found for "{params.query}". Try a general web search instead.')
        lines = []
        for e in entries:
            title = (e.findtext('atom:title', default='', namespaces=ns) or '').strip().replace('\n', ' ')
            link = next((l.get('href') for l in e.findall('atom:link', ns) if l.get('type') == 'text/html'), '')
            summary = (e.findtext('atom:summary', default='', namespaces=ns) or '').strip().replace('\n', ' ')[:300]
            lines.append(f'- {title}\n  url: {link}\n  abstract: {summary}')
        text = '\n'.join(lines)
        return ActionResult(extracted_content=text, long_term_memory=f'arXiv results for "{params.query}":\n{text}')

    return tools


async def _list_tab_ids() -> set[str]:
    """Raw CDP HTTP (GET /json/list) rather than browser_use's own Browser.get_tabs(), which goes
    through its own cached target list -- measured stale enough after a real run that acting on
    "everything get_tabs() returns" missed most of the actual open tabs."""
    if not CDP_URL:
        return set()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            live = (await c.get(f"{CDP_URL.rstrip('/')}/json/list")).json()
            return {t["id"] for t in live if t.get("id")}
    except Exception:
        return set()


async def _close_tabs(ids: set[str]) -> None:
    if not CDP_URL or not ids:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            for tid in ids:
                try:
                    await c.get(f"{CDP_URL.rstrip('/')}/json/close/{tid}")
                except Exception:
                    pass
    except Exception:
        pass


async def _close_all_tabs() -> None:
    """Closing all targets including the last one is safe here specifically because this bridge
    only ever runs against a real Chrome.app on macOS, which does not quit when its last window/tab
    closes -- the next job just opens a fresh tab itself. Only safe to call when nothing else is
    concurrently using the browser (see run_topic_scout's job-level call, not per-topic)."""
    await _close_tabs(await _list_tab_ids())


async def run_browser_use(task: str, max_steps: int | None = None, output_model_schema: type[BaseModel] = _ScoutOutput, close_before: bool = True) -> dict[str, Any]:
    try:
        from browser_use import Agent
    except Exception as exc:
        return {
            "ok": False,
            "error": "browser-use is not installed on this Mac bridge",
            "detail": str(exc),
            "install": "Run scripts/mac/setup_browser_use.sh",
        }

    # Start from a guaranteed-clean slate. We attach via CDP to the same Chrome window a human may
    # also be using to check the StudyBuddy app itself -- measured directly: a job's first action
    # was to click a button on the user's own already-open onboarding path page, because that page
    # (not a blank tab) was what the agent found when it started. Closing every tab before the run
    # begins means the agent always starts from nothing, regardless of what's open elsewhere.
    # Skippable (close_before=False) for a run that's one of several happening concurrently --
    # closing everything mid-flight would tear down a sibling run's in-progress tabs. The caller is
    # then responsible for doing this once, up front, before any of them start.
    if close_before:
        await _close_all_tabs()

    browser = None
    tabs_before = await _list_tab_ids()
    try:
        llm = _build_llm()
        browser = _build_browser()
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            tools=_build_tools(),
            use_vision=USE_VISION,
            max_actions_per_step=2,
            flash_mode=FLASH_MODE,
            output_model_schema=output_model_schema,
            # Default (60-75s depending on provider auto-detection) was measured too tight
            # specifically for the 'done' action: it carries the full output_model_schema (7
            # required fields for _ScoutResource) on top of whatever other actions are in play,
            # by far the most tokens any single action in this tool set has to generate -- at this
            # model's throughput that reliably ran past the deadline and came back as "Model
            # returned empty action" right as the agent tried to finish, discarding an otherwise
            # fully successful run. Every other action (search/click/scroll/...) is far smaller and
            # was never the one timing out.
            llm_timeout=150,
        )
        history = await agent.run(max_steps=max_steps or MAX_STEPS)
        final = history.final_result() if hasattr(history, "final_result") else str(history)
        # A screenshot of whatever page the agent landed on, taken here in code -- not asked of the
        # LLM, which can't reliably transcribe tens of KB of binary image data into its own JSON
        # output. Best-effort: a failed capture (page navigated away, closed, etc.) shouldn't turn an
        # otherwise-successful resource lookup into a failure.
        screenshot_b64 = None
        try:
            png = await browser.take_screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(png).decode()
        except Exception as shot_exc:
            print(f"Screenshot capture failed (non-fatal): {type(shot_exc).__name__}: {shot_exc}", file=sys.stderr)
        # Ground truth for the single-resource shape (_ScoutResource): the model retypes the URL as
        # free text into its own JSON 'done' output instead of the code reading it from the real
        # browser state -- same failure class as every other URL-hallucination bug this session
        # (navigate typos, fabricated video IDs), just on the output side instead of navigation.
        # Observed directly: a real run landed on the correct Substack post but the model's own
        # 'url' field came back as the bare domain "https://substack.com". The task prompt already
        # tells the agent to be sitting on the resource's page when it calls done, so the CDP
        # session's actual current-tab URL is authoritative here and overrides whatever text the
        # model wrote.
        actual_url = None
        try:
            actual_url = await browser.get_current_page_url()
            if actual_url in (None, "", "about:blank"):
                actual_url = None
        except Exception:
            pass
        # Ground truth for video length too: "see video duration from dom/inspect element stuff"
        # means reading it, not asking the model to eyeball a timestamp off the page and retype it
        # (the model is exactly as unreliable at that as it is at retyping URLs -- see actual_url
        # above). A native <video> element's own .duration is the real length regardless of what a
        # human-facing "12:34" label says; this is a single narrow, read-only CDP eval done by OUR
        # code, not the 'evaluate' agent action (deliberately excluded from Tools() so the model
        # itself can't run arbitrary JS). No-ops harmlessly on any page without a <video> element,
        # e.g. an article -- so it's safe to always attempt.
        video_duration_min = None
        try:
            cdp_session = await browser.get_or_create_cdp_session()
            js_result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={
                    "expression": "(function(){var v=document.querySelector('video');"
                    "return (v&&v.duration&&isFinite(v.duration))?v.duration:null})()",
                    "returnByValue": True,
                },
                session_id=cdp_session.session_id,
            )
            val = (js_result or {}).get("result", {}).get("value")
            if isinstance(val, (int, float)) and val > 0:
                video_duration_min = max(1, round(val / 60))
        except Exception as dur_exc:
            print(f"Video duration capture failed (non-fatal): {type(dur_exc).__name__}: {dur_exc}", file=sys.stderr)
    except Exception as exc:
        return {
            "ok": False,
            "error": "Browser-Use execution failed",
            "detail": f"{type(exc).__name__}: {exc}",
            "provider": BROWSER_PROVIDER,
            "model": OLLAMA_MODEL if BROWSER_PROVIDER == "ollama" else BROWSER_MODEL,
            "cdp_url": CDP_URL,
        }
    finally:
        # Leaving tabs open after a job (including any still-playing media, e.g. an autoplaying
        # YouTube tab) piles up indefinitely across runs (observed: 46 tabs / 38 renderer processes
        # after ~3 hours) and is exactly the kind of leftover state that contaminates the NEXT job's
        # starting page -- see the comment above _close_all_tabs(). Scoped to tabs THIS run created
        # (diffed against tabs_before) rather than closing everything, so a concurrent sibling run's
        # still-in-progress tabs survive.
        tabs_after = await _list_tab_ids()
        await _close_tabs(tabs_after - tabs_before)
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass

    parsed = None
    if isinstance(final, str):
        candidate = final.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.S)
        try:
            parsed = json.loads(candidate)
        except Exception:
            parsed = None
    # Observed in practice: the model sometimes wraps the expected object in a single-item list,
    # e.g. [{"resources": [...]}] instead of {"resources": [...]}. Unwrap that one specific shape
    # rather than accepting any list, so we don't silently misread an actually-different payload.
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if isinstance(parsed, dict):
        if 'resources' in parsed:
            parsed['resources'] = sanitize_resources(parsed['resources'])
        elif 'url' in parsed:
            # Single-resource shape only (see comment above the actual_url capture) -- a
            # 'resources' list can span several pages visited over the run, so the final page
            # isn't ground truth for all of them; only the single-resource _ScoutResource shape
            # guarantees the agent is on the reported page when it calls done.
            if actual_url:
                parsed['url'] = actual_url
            if video_duration_min:
                parsed['estimated_minutes'] = video_duration_min
        return {"ok": True, "provider": BROWSER_PROVIDER, "final_result": final, "screenshot_base64": screenshot_b64, **parsed}
    return {"ok": True, "provider": BROWSER_PROVIDER, "final_result": final, "screenshot_base64": screenshot_b64}


_TOPIC_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,.'&/()+:-]{2,119}$")


def safe_topics(raw: Any, limit: int = 12) -> list[str]:
    """Defence in depth on the Mac side: only short plain-text phrases; never URLs, paths, e-mail addresses or code-like strings."""
    out: list[str] = []
    for t in raw if isinstance(raw, list) else []:
        t = str(t).strip()
        if _TOPIC_OK.match(t) and "://" not in t and "@" not in t and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


_YT_ID_OK = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _valid_resource_url(url: Any) -> bool:
    """Reject resource URLs that are malformed or carry stray JSON syntax from a glitched
    generation (observed in practice: a URL like '...python/}}]}]},{' from the model corrupting
    its own output mid-string). No DNS resolution here -- this only guards what we store, not
    what gets auto-opened (that path already goes through safe_open_url separately)."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        p = urlparse(url.strip())
    except ValueError:
        return False
    if p.scheme not in ('http', 'https') or not p.netloc or re.search(r'[{}\[\]<>"\s]', url):
        return False
    # Real YouTube video IDs are always exactly 11 chars from a fixed charset -- a fabricated
    # placeholder (observed: 'example_video_id', after the agent failed to click through to a
    # real result and gave up) is syntactically a fine-looking URL, so the checks above alone
    # would let it straight into the database as if it were real.
    host = p.hostname or ''
    if host == 'youtu.be':
        return bool(_YT_ID_OK.match(p.path.lstrip('/').split('/')[0]))
    if host.endswith('youtube.com') and p.path == '/watch':
        vid = parse_qs(p.query).get('v', [''])[0]
        return bool(_YT_ID_OK.match(vid))
    return True


def _is_youtube_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or '')
    except ValueError:
        return False
    return host == 'youtu.be' or host.endswith('youtube.com')


def sanitize_resources(resources: Any) -> list[dict]:
    """Drop resources with a malformed URL and de-duplicate by URL, keeping first occurrence
    (order = the model's own recommended_order). Applied to every scout/research job's output
    before it reaches the product, since the model's raw JSON is not otherwise validated."""
    if not isinstance(resources, list):
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for r in resources:
        if not isinstance(r, dict) or not _valid_resource_url(r.get('url')):
            continue
        norm = r['url'].strip().rstrip('/')
        if norm in seen:
            continue
        seen.add(norm)
        out.append(r)
    return out


def build_scout_task(payload: dict[str, Any], kind: str) -> str:
    query = "Research only the approved topics listed below."
    plan = ""
    topics = safe_topics(payload.get("topics"))
    topic_block = ("\nTopics to cover (find resources for EACH; set `topic` to the matching phrase):\n" + "\n".join(f"- {t}" for t in topics)) if topics else ""
    return (
        "You are the browser-side resource scout for Spartan StudyBuddy. "
        "Use only publicly accessible educational resources. "
        "Do not use paid AI APIs. Prefer official documentation, university material, primary research, "
        "reputable technical blogs (GeeksforGeeks and Medium are good defaults for programming/CS topics -- "
        "if Medium shows an 'Open in app' banner/button, ignore it and never click it, it leads to an app-store "
        "page with no article content; the real article is already visible on the page behind/below it), "
        "high-quality YouTube educational videos, and library catalog metadata. "
        "Return ONLY a JSON object. Include a resources array. Each resource must have: title, url, "
        "resource_type (documentation, article, video, paper, book, course or tutorial), source, difficulty, why, recommended_order, estimated_minutes, topic. Copy the exact matching topic phrase; explain what the resource teaches. Visit each page, scroll down to read its actual body content (not just the title), and confirm it really covers the topic before selecting it. If this is web_research, also include synthesis and evidence_notes. Prefer arXiv/primary papers for research claims -- use the arxiv_search action directly for any topic with academic/research depth, instead of searching the web for it. Do not wrap JSON in markdown. Never bypass paywalls, DRM, access controls, "
        "CAPTCHAs, or institutional restrictions. If a site requires a human login/MFA step, stop and report it. "
        "There is no navigate-to-URL action -- you cannot type a URL. For every topic, use the search action to search for it, then use click on a real result from that page to open it. "
        "If a page you clicked to doesn't look right, use go_back and click a different result -- do not click the same result again. "
        "Once a page is open, extract what you need from it immediately and move on; do not click back into a page you already extracted from. "
        "Include at least one YouTube video across all topics when a relevant one exists in search results.\n\n"
        f"Task: {query}{topic_block}\nResearch plan: {plan}"
    )


def build_topic_task(topic: str, target_minutes: int | None = None, resource_type: str | None = None) -> str:
    length_hint = (
        f"The learner has about {target_minutes} minutes for this -- prefer a resource that roughly fits that "
        f"(a quick doc/article for a short budget, a fuller course/video for a longer one), and set estimated_minutes "
        "to your honest estimate of the resource's OWN actual length, not the target itself. "
        if target_minutes else ""
    )
    # Assigned per-topic so the course as a whole ends up with a healthy video/article mix instead of
    # whatever type the scout happens to stumble on first -- see topic_resource_type in onboarding.py.
    type_hint = ""
    if resource_type == "video":
        type_hint = (
            "This topic specifically needs a YouTube VIDEO, not an article or doc page -- search with "
            "terms like \"<topic> tutorial\" or \"<topic> explained\" and pick a real video you clicked "
            "through to from the search results. Only fall back to a non-video resource if, after actually "
            "trying, no genuinely relevant video exists. "
        )
    elif resource_type == "article":
        type_hint = (
            "This topic specifically needs a written ARTICLE, blog post, or documentation page, not a "
            "video. Only fall back to a video if, after actually trying, no genuinely relevant written "
            "resource exists. "
        )
    return (
        "You are the browser-side resource scout for Spartan StudyBuddy. "
        "Use only publicly accessible educational resources. Do not use paid AI APIs. "
        "Prefer official documentation, university material, primary research, "
        "reputable technical blogs (GeeksforGeeks and Medium are good defaults for programming/CS topics -- "
        "if Medium shows an 'Open in app' banner/button, ignore it and never click it, it leads to an app-store "
        "page with no article content; the real article is already visible on the page behind/below it), "
        "high-quality YouTube educational videos, and library catalog metadata. "
        "Prefer arXiv/primary papers for research claims -- use the arxiv_search action directly for topics with academic/research depth. "
        "Never bypass paywalls, DRM, access controls, CAPTCHAs, or institutional restrictions. If a site requires a human login/MFA step, stop and report it. "
        "There is no navigate-to-URL action -- you cannot type a URL. Use the search action, then click a real result to open it. "
        "If a page doesn't look right, use go_back and click a different result -- do not click the same result twice. "
        f'Find exactly ONE good public resource for this single topic: "{topic}". {length_hint}{type_hint}'
        "If a genuinely relevant YouTube video appears in "
        "the search results, prefer it -- but only a real one you actually clicked to, never guess a video exists. Visit the page, "
        "scroll to read its actual body content, confirm it covers the topic, then call done immediately with that one resource. "
        "Do not keep looking for a second or better resource -- the first one that genuinely covers the topic is enough. "
        "Return only a JSON object with: title, url, resource_type (documentation, article, video, paper, book, course or tutorial), "
        f'source, difficulty, why, recommended_order, estimated_minutes, topic (must be exactly "{topic}").'
    )


async def run_topic_scout(topic: str, target_minutes: int | None = None, resource_type: str | None = None, close_before: bool = True) -> dict | None:
    """One small, focused browser-use run per topic instead of one big session juggling all of
    them -- measured directly: an 8B model tracking N topics' worth of state in its own working
    memory across 20+ steps got stuck re-reading a PDF it had already fully extracted 5 times in a
    row instead of recognizing it had what it needed and moving to the next topic. A single-topic
    task never needs that much working memory, and output_model_schema=_ScoutResource (one object,
    not an array) matches how small the job actually is.

    target_minutes: the learner's actual time budget for this topic (from the onboarding plan's
    hours_per_week), so the scout prefers a resource of roughly the right length instead of
    whatever it happens to find -- previously unused, meaning a 15-minute budget and a 3-hour
    budget got treated identically.

    resource_type: 'video' or 'article' when this topic was assigned one (see topic_resource_type in
    onboarding.py), so a course ends up with a balanced mix instead of whatever type each topic
    happens to turn up. Best-effort over the retry budget -- if the requested type genuinely isn't
    findable, the last attempt's result is accepted anyway rather than returning nothing."""
    task = build_topic_task(topic, target_minutes, resource_type)
    last_result = None
    attempts = 2
    for attempt in range(attempts):
        result = await run_browser_use(task, max_steps=10, output_model_schema=_ScoutResource, close_before=close_before)
        if result.get("ok") and result.get("url") and result.get("title") and _valid_resource_url(result.get("url")):
            is_video = result.get("resource_type") == "video" or _is_youtube_url(result.get("url", ""))
            type_mismatch = (resource_type == "video" and not is_video) or (resource_type == "article" and is_video)
            if type_mismatch and attempt < attempts - 1:
                last_result = result
                continue
            r = {k: result.get(k) for k in ("title", "url", "resource_type", "source", "difficulty", "why", "recommended_order", "estimated_minutes", "topic", "screenshot_base64")}
            r.setdefault("topic", topic)
            return r
    if last_result:
        r = {k: last_result.get(k) for k in ("title", "url", "resource_type", "source", "difficulty", "why", "recommended_order", "estimated_minutes", "topic", "screenshot_base64")}
        r.setdefault("topic", topic)
        return r
    return None


def safe_open_url(raw: Any) -> str:
    """Browser jobs may open only public, credential-free HTTPS pages."""
    try:
        parsed = urlparse(str(raw or '').strip());port=parsed.port
    except ValueError as exc:
        raise ValueError('malformed URL') from exc
    host=(parsed.hostname or '').rstrip('.')
    if parsed.scheme!='https' or not host or parsed.username or parsed.password or port not in (None,443):
        raise ValueError('only credential-free HTTPS URLs are allowed')
    try:addresses=[ipaddress.ip_address(host)]
    except ValueError:
        try:addresses=[ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)]
        except socket.gaierror as exc:raise ValueError('host could not be resolved') from exc
    if not addresses or any(not ip.is_global for ip in addresses):
        raise ValueError('local or private addresses are not allowed')
    return parsed.geturl()


async def execute(job: dict[str, Any]) -> dict[str, Any]:

    payload = job.get("payload") or {}
    kind = job.get("kind")
    if kind == "open_resource":
        try:
            url = safe_open_url(payload.get("url"))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        webbrowser.open(url)
        return {"ok": True, "opened": url}

    if kind == "resource_scout":
        topics = safe_topics(payload.get("topics"))
        if not topics:
            return {"ok": False, "error": "No approved public topics supplied"}
        target_minutes_by_topic = payload.get("topic_target_minutes") or {}
        resource_type_by_topic = payload.get("topic_resource_type") or {}
        # One small, focused run per topic (see run_topic_scout) instead of one long session
        # covering all of them -- the previous multi-topic design reliably looped once an 8B
        # model's own working memory got overloaded tracking several topics' progress at once.
        # Concurrent, bounded by MAX_CONCURRENT_SCOUTS: the contamination-guard close happens ONCE
        # here, before any topic starts (each individual run skips it via close_before=False), and
        # each run's own cleanup is scoped to only the tabs it created (see run_browser_use) -- so
        # sibling runs sharing one Chrome instance don't tear each other's tabs down mid-flight.
        await _close_all_tabs()
        sem = asyncio.Semaphore(MAX_CONCURRENT_SCOUTS)
        # A gate (not a per-index delay) so EVERY connect is spaced out, not just the first wave.
        # browser_use's CDP connect() does a full target-discovery+auto-attach handshake against
        # Chrome and is given a *hardcoded* 15s budget (not configurable from here) -- measured
        # directly that sessions hitting that handshake in the same instant serialize inside Chrome
        # and blow the deadline for all of them ("connect() timed out after 15s" -> cascades into
        # "AssertionError: Root CDP client not initialized" wherever the code then touches that
        # browser, e.g. our own screenshot capture). An index-based pre-semaphore delay only
        # staggers the FIRST wave of MAX_CONCURRENT_SCOUTS topics -- once one finishes and frees its
        # slot, whichever topic grabs that slot next starts connecting immediately, with no
        # guarantee it's spaced from whatever ELSE just grabbed a freed slot at the same moment.
        # Holding a lock for CONNECT_STAGGER_S right before each connect guarantees a minimum gap
        # between every connect, first-wave or not.
        connect_gate = asyncio.Lock()
        CONNECT_STAGGER_S = float(os.getenv("STUDYBUDDY_BROWSER_CONNECT_STAGGER_S", "5"))

        async def _scout(t: str) -> dict | None:
            async with sem:
                async with connect_gate:
                    await asyncio.sleep(CONNECT_STAGGER_S)
                return await run_topic_scout(t, target_minutes_by_topic.get(t), resource_type_by_topic.get(t), close_before=False)

        results = await asyncio.gather(*(_scout(t) for t in topics))
        resources = [r for r in results if r]
        if not resources:
            return {"ok": False, "error": "Resource scouting found no usable resource for any topic"}
        return {"ok": True, "resources": sanitize_resources(resources)}

    if kind == "web_research":
        # Cross-topic synthesis genuinely needs one session holding every topic's findings
        # together to write about, unlike resource_scout's independent per-topic lookups -- kept
        # on the original single multi-topic session rather than split per-topic.
        topics = safe_topics(payload.get("topics"))
        if not topics:
            return {"ok": False, "error": "No approved public topics supplied"}
        steps = max(MAX_STEPS, min(len(topics) * 3 + 2, 40))
        for attempt in range(2):
            result = await run_browser_use(build_scout_task(payload, kind), max_steps=steps)
            if result.get("ok") and isinstance(result.get("resources"), list) and result["resources"]:
                return result
        return {"ok": False, "error": "Resource scouting returned no structured resources after two attempts"}

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
