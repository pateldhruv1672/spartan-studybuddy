from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .telemetry import recent_traces


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values.sort()
    return values[min(len(values) - 1, int(fraction * len(values)))]


def snapshot(org_id: str, limit: int = 200) -> dict[str, Any]:
    rows = recent_traces(min(max(limit, 1), 500), org_id)
    latencies = [float(row['latency_ms']) for row in rows if row.get('latency_ms') is not None]
    ttft = [float(row['ttft_ms']) for row in rows if row.get('ttft_ms') is not None]
    successes = sum(1 for row in rows if row.get('success') in (1, True))
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'sample_size': len(rows),
        'success_rate': successes / len(rows) if rows else None,
        'latency_p50_ms': _percentile(latencies, .50),
        'latency_p95_ms': _percentile(latencies, .95),
        'ttft_p50_ms': _percentile(ttft, .50),
        'tokens_in': sum(int(row.get('input_tokens') or 0) for row in rows),
        'tokens_out': sum(int(row.get('output_tokens') or 0) for row in rows),
        'routes': sorted({row['route'] for row in rows if row.get('route')}),
    }
