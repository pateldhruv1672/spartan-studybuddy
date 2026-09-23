#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(); p.add_argument('--summary',default='experiments/results/summary.json'); p.add_argument('--output',default='experiments/results/HACKATHON_RESULTS.md'); a=p.parse_args()
    s=json.loads(Path(a.summary).read_text(encoding='utf-8')); q=s['socratic_quality']; serving=s.get('serving_base_vs_tuned',{}); spec=s.get('speculative_decoding',{})
    lines=[
      '# Spartan StudyBuddy — measured model results','',
      '> Generated from measurements on the deployment hardware. Do not replace these values with estimated claims.','',
      '## Socratic behavior', '',
      '| Metric | Base | Fine-tuned |', '|---|---:|---:|',
      f"| Held-out rubric score / 100 | {q['base_score']:.2f} | {q['tuned_score']:.2f} |",
      f"| Direct-answer leakage rate | {q['base_answer_leak_rate']*100:.1f}% | {q['tuned_answer_leak_rate']*100:.1f}% |",
      f"| Probing-question rate | {q['base_question_rate']*100:.1f}% | {q['tuned_question_rate']*100:.1f}% |", '',
    ]
    if serving:
      lines += ['## Base vs tuned serving','', '| Metric | Base | Tuned |','|---|---:|---:|',
        f"| p50 TTFT | {serving['base_ttft_p50_s']:.3f}s | {serving['tuned_ttft_p50_s']:.3f}s |",
        f"| p50 decode throughput | {serving['base_decode_tok_s_p50']:.1f} tok/s | {serving['tuned_decode_tok_s_p50']:.1f} tok/s |",
        f"| aggregate output throughput | {serving['base_aggregate_tok_s']:.1f} tok/s | {serving['tuned_aggregate_tok_s']:.1f} tok/s |", '']
    if spec:
      lines += ['## Speculative decoding A/B','', '| Metric | Tuned | Tuned + speculation | Change |','|---|---:|---:|---:|',
        f"| p50 TTFT | {spec['baseline_ttft_p50_s']:.3f}s | {spec['spec_ttft_p50_s']:.3f}s | {spec['ttft_change_pct']:+.1f}% |",
        f"| p50 decode throughput | {spec['baseline_decode_tok_s_p50']:.1f} tok/s | {spec['spec_decode_tok_s_p50']:.1f} tok/s | {spec['decode_tok_s_change_pct']:+.1f}% |",
        f"| aggregate output throughput | — | — | {spec['aggregate_tok_s_change_pct']:+.1f}% |", '',
        '**Interpretation:** use the speculative profile only if the measured workload improves. Speculative decoding is workload-dependent; the experiment script does not manufacture a speedup.','']
    Path(a.output).write_text('\n'.join(lines),encoding='utf-8'); print(a.output)
if __name__=='__main__': main()
