from __future__ import annotations

import json
from pathlib import Path

from app.services.engineering_data import competition_results, serving_profile_results


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding='utf-8')


def test_quality_is_read_from_raw_evaluations(tmp_path: Path):
    write(tmp_path / 'base_eval.json', {'mean_rubric_score': 10, 'answer_leak_rate': .8, 'probing_question_rate': .2, 'guidance_marker_rate': .4, 'concise_rate': .5})
    write(tmp_path / 'tuned_eval.json', {'mean_rubric_score': 20, 'answer_leak_rate': .2, 'probing_question_rate': .6, 'guidance_marker_rate': .9, 'concise_rate': 1.0})
    result = competition_results(tmp_path)
    assert result['socratic_quality']['base_score'] == 10
    assert result['socratic_quality']['tuned_score'] == 20
    assert result['socratic_quality']['score_delta_points'] == 10


def test_benchmarks_are_discovered_and_compared_to_nvfp4(tmp_path: Path):
    write(tmp_path / 'nvfp4_bench.json', {'profile': 'nvfp4-quantized', 'ttft_p50_s': .1, 'decode_tok_s_p50': 10, 'aggregate_output_tok_s': 9})
    write(tmp_path / 'nvfp4_mtp_spec2_bench.json', {'profile': 'nvfp4-mtp-spec2', 'ttft_p50_s': .2, 'decode_tok_s_p50': 20, 'aggregate_output_tok_s': 18, 'spec_metrics_samples': [{'num_accepted_draft_tokens': 3, 'num_draft_tokens': 4, 'num_spec_steps': 2}]})
    write(tmp_path / 'recommended_serving.env', {'SPECULATION_METHOD': 'mtp2'})
    # The helper accepts the same simple env text as the production artifact.
    (tmp_path / 'recommended_serving.env').write_text('SPECULATION_METHOD=mtp2\n', encoding='utf-8')
    result = serving_profile_results(tmp_path)
    assert result['selected_method'] == 'mtp2'
    assert {row['method'] for row in result['profiles']} == {'standard', 'mtp2'}
    assert next(row for row in result['profiles'] if row['method'] == 'mtp2')['recommended'] is True
