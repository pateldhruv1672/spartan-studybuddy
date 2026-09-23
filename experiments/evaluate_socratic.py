#!/usr/bin/env python3
"""Evaluate Socratic behavior against held-out StudyBuddy prompts.

The primary score is deterministic/rule-based so the experiment requires no cloud
judge. An optional local judge can be added later, but the core comparison stays
reproducible and inspectable for judges.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
import httpx

MINIMAL_SYSTEM = "You are a helpful educational assistant. Respond to the student\'s request."

HINT_MARKERS = (
    "think", "consider", "first", "start", "check", "trace", "compare", "identify",
    "what", "which", "why", "how", "try", "hint", "before"
)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def score_case(case: dict[str, Any], text: str) -> dict[str, Any]:
    low = normalize(text)
    forbidden = [normalize(x) for x in case.get("forbidden", []) if x]
    leaks = [x for x in forbidden if x and x in low]
    asks_question = "?" in text
    hint_marker = any(re.search(rf"\b{re.escape(marker)}\b", low) for marker in HINT_MARKERS)
    words = len(text.split())
    concise = words <= 180
    no_leak = not leaks
    # Transparent weighted rubric: avoiding the final answer dominates the score.
    score = 50 * no_leak + 25 * asks_question + 15 * hint_marker + 10 * concise
    return {
        "id": case["id"], "domain": case.get("domain"), "score": score,
        "no_answer_leak": no_leak, "leaked_literals": leaks,
        "asks_probing_question": asks_question, "contains_guidance_marker": hint_marker,
        "concise": concise, "word_count": words, "response": text,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--api-key", default="local-edge")
    p.add_argument("--cases", default="training/data/behavior_eval.jsonl")
    p.add_argument("--output", required=True)
    p.add_argument("--timeout", type=float, default=120)
    args = p.parse_args()

    cases = load_jsonl(args.cases)
    rows = []
    with httpx.Client(timeout=args.timeout) as client:
        for case in cases:
            payload = {
                "model": args.model,
                "messages": [{"role":"system","content":MINIMAL_SYSTEM},{"role":"user","content":case["prompt"]}],
                "temperature": 0.0,
                "max_tokens": 220,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            r = client.post(args.base.rstrip("/") + "/chat/completions", headers={"Authorization":f"Bearer {args.api_key}"}, json=payload)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            rows.append(score_case(case, text))

    n = max(1, len(rows))
    summary = {
        "profile": args.profile,
        "model": args.model,
        "cases": len(rows),
        "mean_rubric_score": round(sum(r["score"] for r in rows) / n, 2),
        "answer_leak_rate": round(sum(not r["no_answer_leak"] for r in rows) / n, 4),
        "probing_question_rate": round(sum(r["asks_probing_question"] for r in rows) / n, 4),
        "guidance_marker_rate": round(sum(r["contains_guidance_marker"] for r in rows) / n, 4),
        "concise_rate": round(sum(r["concise"] for r in rows) / n, 4),
        "results": rows,
    }
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
