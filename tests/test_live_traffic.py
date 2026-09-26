from __future__ import annotations

from app.services import live_traffic


def test_snapshot_aggregates_recent_traces(monkeypatch):
    monkeypatch.setattr(live_traffic, 'recent_traces', lambda limit, org_id: [
        {'latency_ms': 100, 'ttft_ms': 20, 'input_tokens': 3, 'output_tokens': 5, 'success': 1, 'route': 'qa'},
        {'latency_ms': 300, 'ttft_ms': 40, 'input_tokens': 4, 'output_tokens': 6, 'success': 0, 'route': 'socratic'},
    ])
    result = live_traffic.snapshot('org')
    assert result['sample_size'] == 2
    assert result['success_rate'] == .5
    assert result['latency_p50_ms'] == 300
    assert result['tokens_in'] == 7 and result['tokens_out'] == 11
    assert result['routes'] == ['qa', 'socratic']
