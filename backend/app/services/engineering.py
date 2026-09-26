from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BENCHMARK_PROFILES = (
    ('nvfp4_bench.json', 'NVFP4 standard', 'standard'),
    ('nvfp4_spec_ngram_bench.json', 'NVFP4 + n-gram', 'ngram'),
    ('nvfp4_mtp_bench.json', 'NVFP4 + MTP ×1', 'mtp1'),
    ('nvfp4_mtp2_bench.json', 'NVFP4 + MTP ×2', 'mtp2'),
    ('nvfp4_mtp3_bench.json', 'NVFP4 + MTP ×3', 'mtp3'),
)

def _json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None

def competition_results(results_dir: Path) -> dict[str, Any]:
    summary = _json(results_dir / 'summary.json') or _json(results_dir / 'comparison.json')
    if not summary:
        return {'available': False, 'message': 'Run make competition on the DGX Spark.'}
    quality = summary.setdefault('socratic_quality', {})
    for prefix, filename in (('base', 'base_eval.json'), ('tuned', 'tuned_eval.json')):
        evaluation = _json(results_dir / filename) or {}
        for metric in ('guidance_marker_rate', 'concise_rate'):
            if metric in evaluation:
                quality.setdefault(f'{prefix}_{metric}', evaluation[metric])
    return summary

def _selected_profile(results_dir: Path, summary: dict[str, Any]) -> str | None:
    try:
        lines = (results_dir / 'recommended_serving.env').read_text(encoding='utf-8').splitlines()
    except OSError:
        lines = []
    values = dict(line.split('=', 1) for line in lines if '=' in line and not line.lstrip().startswith('#'))
    method = values.get('SPECULATION_METHOD', '').strip().lower()
    if method in {'none', 'standard'}: return 'standard'
    if method in {'ngram', 'mtp', 'mtp1', 'mtp2', 'mtp3'}: return 'mtp1' if method == 'mtp' else method
    profile = str(summary.get('speculative_decoding', {}).get('spec_profile') or '').lower()
    if 'mtp' in profile: return 'mtp3' if 'spec3' in profile else 'mtp2' if 'spec2' in profile else 'mtp1'
    if 'ngram' in profile: return 'ngram'
    return None

def _acceptance(samples: Any) -> tuple[float | None, float | None]:
    rows = [row for row in samples if isinstance(row, dict)] if isinstance(samples, list) else []
    accepted = sum(float(row.get('num_accepted_draft_tokens') or 0) for row in rows)
    drafted = sum(float(row.get('num_draft_tokens') or 0) for row in rows)
    steps = sum(float(row.get('num_spec_steps') or 0) for row in rows)
    return (accepted / drafted if drafted else None, 1 + accepted / steps if steps else None)

def serving_profile_results(results_dir: Path) -> dict[str, Any]:
    summary = _json(results_dir / 'summary.json') or _json(results_dir / 'comparison.json') or {}
    selected = _selected_profile(results_dir, summary)
    profiles = []
    for filename, label, method in BENCHMARK_PROFILES:
        data = _json(results_dir / filename)
        if not data: continue
        acceptance, mean_length = _acceptance(data.get('spec_metrics_samples'))
        profiles.append({
            'method': method, 'label': label, 'profile': data.get('profile'), 'model': data.get('model'),
            'requests': data.get('requests'), 'concurrency': data.get('concurrency'),
            'ttft_p50_s': data.get('ttft_p50_s'), 'ttft_p95_s': data.get('ttft_p95_s'),
            'decode_tok_s_p50': data.get('decode_tok_s_p50'),
            'aggregate_output_tok_s': data.get('aggregate_output_tok_s'),
            'draft_acceptance_rate': acceptance, 'mean_acceptance_length': mean_length,
            'recommended': method == selected,
        })
    if not profiles:
        return {'available': False, 'selected_method': selected, 'profiles': [], 'message': 'No serving benchmark artifacts are available yet.'}
    return {'available': True, 'selected_method': selected, 'profiles': profiles, 'message': 'Profiles are measured artifacts; the recommendation is never estimated.'}
