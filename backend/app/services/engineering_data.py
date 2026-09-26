from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _pct(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return round((value - baseline) / baseline * 100, 2)


def _quality(results_dir: Path) -> dict[str, Any] | None:
    base = _load(results_dir / 'base_eval.json')
    tuned = _load(results_dir / 'tuned_eval.json')
    if not base or not tuned:
        return None
    quality = {
        'base_score': base.get('mean_rubric_score'),
        'tuned_score': tuned.get('mean_rubric_score'),
        'base_answer_leak_rate': base.get('answer_leak_rate'),
        'tuned_answer_leak_rate': tuned.get('answer_leak_rate'),
        'base_question_rate': base.get('probing_question_rate'),
        'tuned_question_rate': tuned.get('probing_question_rate'),
        'base_guidance_marker_rate': base.get('guidance_marker_rate'),
        'tuned_guidance_marker_rate': tuned.get('guidance_marker_rate'),
        'base_concise_rate': base.get('concise_rate'),
        'tuned_concise_rate': tuned.get('concise_rate'),
    }
    if quality['base_score'] is not None and quality['tuned_score'] is not None:
        quality['score_delta_points'] = round(quality['tuned_score'] - quality['base_score'], 2)
    if quality['base_answer_leak_rate'] not in (None, 0) and quality['tuned_answer_leak_rate'] is not None:
        quality['answer_leak_reduction_pct'] = round((quality['base_answer_leak_rate'] - quality['tuned_answer_leak_rate']) / quality['base_answer_leak_rate'] * 100, 2)
    return quality


def _profile_method(profile: str) -> str:
    value = profile.lower()
    if 'ngram' in value:
        return 'ngram'
    if 'mtp' in value:
        match = re.search(r'mtp(?:-spec)?([1-9])', value)
        return f'mtp{match.group(1)}' if match else 'mtp1'
    match = re.search(r'mtp(?:-spec)?([1-9])', value)
    if match:
        return f'mtp{match.group(1)}'
    if 'base' in value:
        return 'base'
    if 'tuned' in value:
        return 'tuned'
    return 'standard' if 'quant' in value or 'nvfp4' in value else value


def _acceptance(samples: Any) -> tuple[float | None, float | None]:
    rows = [x for x in samples if isinstance(x, dict)] if isinstance(samples, list) else []
    accepted = sum(float(x.get('num_accepted_draft_tokens') or 0) for x in rows)
    drafted = sum(float(x.get('num_draft_tokens') or 0) for x in rows)
    steps = sum(float(x.get('num_spec_steps') or 0) for x in rows)
    return (accepted / drafted if drafted else None, 1 + accepted / steps if steps else None)


def _selected_method(results_dir: Path, profiles: list[dict[str, Any]]) -> str | None:
    try:
        lines = (results_dir / 'recommended_serving.env').read_text(encoding='utf-8').splitlines()
        env = dict(line.split('=', 1) for line in lines if '=' in line and not line.lstrip().startswith('#'))
        method = env.get('SPECULATION_METHOD', '').strip().lower()
        if method in {'none', 'standard'}:
            return 'standard'
        if method == 'mtp':
            return 'mtp1'
        if method in {p['method'] for p in profiles}:
            return method
    except OSError:
        pass
    summary = _load(results_dir / 'summary.json') or _load(results_dir / 'comparison.json') or {}
    spec = str(summary.get('speculative_decoding', {}).get('spec_profile') or '')
    return _profile_method(spec) if spec else None


def _benchmarks(results_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(results_dir.glob('*_bench.json')):
        data = _load(path)
        if not data or not data.get('profile'):
            continue
        method = _profile_method(str(data['profile']))
        acceptance, mean_length = _acceptance(data.get('spec_metrics_samples'))
        rows.append({
            'method': method,
            'label': str(data['profile']),
            'artifact': path.name,
            'profile': data.get('profile'),
            'model': data.get('model'),
            'requests': data.get('requests'),
            'concurrency': data.get('concurrency'),
            'ttft_p50_s': data.get('ttft_p50_s'),
            'ttft_p95_s': data.get('ttft_p95_s'),
            'decode_tok_s_p50': data.get('decode_tok_s_p50'),
            'aggregate_output_tok_s': data.get('aggregate_output_tok_s'),
            'draft_acceptance_rate': acceptance,
            'mean_acceptance_length': mean_length,
        })
    selected = _selected_method(results_dir, rows)
    summary = _load(results_dir / 'summary.json') or _load(results_dir / 'comparison.json') or {}
    target_profile = str(summary.get('speculative_decoding', {}).get('spec_profile') or '')
    for row in rows:
        row['recommended'] = row['profile'] == target_profile if target_profile else row['method'] == selected
    return rows


def competition_results(results_dir: Path) -> dict[str, Any]:
    quality = _quality(results_dir)
    benchmarks = _benchmarks(results_dir)
    result: dict[str, Any] = {'available': bool(quality or benchmarks)}
    if quality:
        result['socratic_quality'] = quality
    base = next((x for x in benchmarks if x['method'] == 'base'), None)
    tuned = next((x for x in benchmarks if x['method'] == 'tuned'), None)
    if base and tuned:
        result['serving_base_vs_tuned'] = {
            'base_ttft_p50_s': base['ttft_p50_s'], 'tuned_ttft_p50_s': tuned['ttft_p50_s'],
            'base_decode_tok_s_p50': base['decode_tok_s_p50'], 'tuned_decode_tok_s_p50': tuned['decode_tok_s_p50'],
            'base_aggregate_tok_s': base['aggregate_output_tok_s'], 'tuned_aggregate_tok_s': tuned['aggregate_output_tok_s'],
        }
    standard = next((x for x in benchmarks if x['method'] == 'standard'), None)
    selected = next((x for x in benchmarks if x.get('recommended')), None)
    if standard and selected and selected is not standard:
        result['speculative_decoding'] = {
            'baseline_profile': standard['profile'], 'spec_profile': selected['profile'],
            'ttft_change_pct': _pct(selected['ttft_p50_s'], standard['ttft_p50_s']),
            'decode_tok_s_change_pct': _pct(selected['decode_tok_s_p50'], standard['decode_tok_s_p50']),
            'aggregate_tok_s_change_pct': _pct(selected['aggregate_output_tok_s'], standard['aggregate_output_tok_s']),
            'baseline_decode_tok_s_p50': standard['decode_tok_s_p50'], 'spec_decode_tok_s_p50': selected['decode_tok_s_p50'],
            'baseline_ttft_p50_s': standard['ttft_p50_s'], 'spec_ttft_p50_s': selected['ttft_p50_s'],
        }
    if not result['available']:
        result['message'] = 'No measured evaluation or serving artifacts are available yet.'
    return result


def serving_profile_results(results_dir: Path) -> dict[str, Any]:
    profiles = _benchmarks(results_dir)
    if not profiles:
        return {'available': False, 'profiles': [], 'message': 'No serving benchmark artifacts are available yet.'}
    selected = next((x['method'] for x in profiles if x.get('recommended')), None)
    return {'available': True, 'selected_method': selected, 'profiles': profiles, 'message': 'Loaded from measured benchmark artifacts at request time.'}
