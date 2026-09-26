from __future__ import annotations

import json
from pathlib import Path

from app.services.engineering import competition_results, serving_profile_results


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding='utf-8')


def test_competition_results_enriches_measured_fields(tmp_path: Path):
    write(tmp_path / 'summary.json', {'socratic_quality': {'base_score': 40}})
    write(tmp_path / 'base_eval.json', {'guidance_marker_rate': .5, 'concise_rate': .75})
    write(tmp_path / 'tuned_eval.json', {'guidance_marker_rate': .9, 'concise_rate': 1.0})
    result = competition_results(tmp_path)
    assert result['socratic_quality']['base_guidance_marker_rate'] == .5
    assert result['socratic_quality']['tuned_concise_rate'] == 1.0


def test_serving_profiles_mark_recommendation(tmp_path: Path):
    write(tmp_path / 'summary.json', {'speculative_decoding': {'spec_profile': 'nvfp4-mtp-spec2'}})
    write(tmp_path / 'nvfp4_mtp2_bench.json', {
        'profile': 'mtp2', 'ttft_p50_s': .25, 'decode_tok_s_p50': 20, 'aggregate_output_tok_s': 19,
        'spec_metrics_samples': [
            {'num_accepted_draft_tokens': 3, 'num_draft_tokens': 4, 'num_spec_steps': 2},
            {'num_accepted_draft_tokens': 6, 'num_draft_tokens': 8, 'num_spec_steps': 4},
        ],
    })
    result = serving_profile_results(tmp_path)
    assert result['available'] is True and result['selected_method'] == 'mtp2'
    row = result['profiles'][0]
    assert row['recommended'] is True and row['draft_acceptance_rate'] == .75 and row['mean_acceptance_length'] == 2.5


def test_missing_results_are_not_fabricated(tmp_path: Path):
    assert competition_results(tmp_path)['available'] is False
    assert serving_profile_results(tmp_path)['profiles'] == []
