#!/usr/bin/env python3
"""Benchmark an OpenAI-compatible vLLM endpoint for StudyBuddy workloads.

Measures TTFT, end-to-end latency, decode tokens/sec, aggregate output throughput,
and captures per-request speculative-decoding metrics when vLLM returns them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

PROMPTS = [
    "I'm implementing BFS and my traversal looks depth-first. Do not give me final code. Give one Socratic hint that helps me inspect the frontier ordering.",
    "I am studying the Master Theorem. For T(n)=4T(n/2)+n, guide me with one question at a time and don't state the final asymptotic result.",
    "My validation loss rises while training loss keeps falling. Act as a tutor: ask me one diagnostic question and give a minimal hint about what the curves suggest.",
    "I am debugging a Python function that returns None from some recursive calls. Give a short hint that makes me trace the base case and return path, not the finished solution.",
    "Course notes: Attention computes compatibility between queries and keys; logits are scaled before softmax; values are mixed using attention weights. I still don't understand why scaling matters. Teach me with a concise Socratic question.",
    "Course notes: BFS explores by increasing unweighted distance. A queue is FIFO. A stack is LIFO. My code appends successors and calls pop() with no index. Help me reason about the mismatch without writing the corrected line.",
    "I read that overfitting can appear as a growing train-validation gap. I have 98% train accuracy and 71% validation accuracy. Ask me what evidence I should inspect before choosing regularization.",
    "I am learning convolution output shapes. Input width is 64, kernel 3, padding 1, stride 2. Do not calculate it for me; remind me what quantities belong in the formula and ask me to substitute them.",
]

SYSTEM = "You are an educational tutor. Help the learner think clearly and concisely."


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


async def one_request(client: httpx.AsyncClient, base: str, model: str, api_key: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    url = base.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    start = time.perf_counter(); first = None; end = None
    text_parts: list[str] = []
    usage: dict[str, Any] = {}
    spec_metrics: dict[str, Any] | None = None
    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            if chunk.get("metrics", {}).get("speculative_decoding"):
                spec_metrics = chunk["metrics"]["speculative_decoding"]
            choices = chunk.get("choices") or []
            if choices:
                piece = (choices[0].get("delta") or {}).get("content") or ""
                if piece:
                    if first is None:
                        first = time.perf_counter()
                    text_parts.append(piece)
    end = time.perf_counter()
    output_tokens = int(usage.get("completion_tokens") or max(1, len("".join(text_parts).split())))
    ttft = (first or end) - start
    total = end - start
    decode_time = max(0.001, end - (first or end))
    return {
        "ttft_s": ttft,
        "e2e_s": total,
        "output_tokens": output_tokens,
        "decode_tok_s": output_tokens / decode_time,
        "request_tok_s": output_tokens / max(total, 0.001),
        "speculative_decoding": spec_metrics,
        "text": "".join(text_parts),
    }


async def benchmark(args) -> dict[str, Any]:
    prompts = [PROMPTS[i % len(PROMPTS)] for i in range(args.requests)]
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout, connect=10.0)) as client:
        async def wrapped(prompt: str):
            async with sem:
                return await one_request(client, args.base, args.model, args.api_key, prompt, args.max_tokens)
        wall_start = time.perf_counter()
        results = await asyncio.gather(*(wrapped(p) for p in prompts))
        wall = time.perf_counter() - wall_start

    ttft = [r["ttft_s"] for r in results]
    e2e = [r["e2e_s"] for r in results]
    decode = [r["decode_tok_s"] for r in results]
    total_tokens = sum(r["output_tokens"] for r in results)
    acceptance = [r["speculative_decoding"] for r in results if r.get("speculative_decoding")]
    summary = {
        "profile": args.profile,
        "endpoint": args.base,
        "model": args.model,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "max_tokens": args.max_tokens,
        "wall_time_s": round(wall, 4),
        "total_output_tokens": total_tokens,
        "aggregate_output_tok_s": round(total_tokens / max(wall, 0.001), 3),
        "ttft_p50_s": round(statistics.median(ttft), 4),
        "ttft_p95_s": round(percentile(ttft, 0.95), 4),
        "e2e_p50_s": round(statistics.median(e2e), 4),
        "e2e_p95_s": round(percentile(e2e, 0.95), 4),
        "decode_tok_s_p50": round(statistics.median(decode), 3),
        "decode_tok_s_p95": round(percentile(decode, 0.95), 3),
        "spec_metrics_samples": acceptance,
        "samples": results[: min(3, len(results))],
    }
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, help="OpenAI-compatible /v1 base")
    p.add_argument("--model", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--api-key", default="local-edge")
    p.add_argument("--requests", type=int, default=16)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--max-tokens", type=int, default=180)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--output")
    args = p.parse_args()
    result = asyncio.run(benchmark(args))
    rendered = json.dumps(result, indent=2)
    if args.output:
        path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
