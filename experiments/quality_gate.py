#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--summary',default='experiments/results/summary.json'); p.add_argument('--min-score-delta',type=float,default=5.0); p.add_argument('--strict',action='store_true'); p.add_argument('--output',default='experiments/results/quality_gate.json'); a=p.parse_args()
    s=json.loads(Path(a.summary).read_text()); q=s['socratic_quality']
    checks={
      'rubric_improved': q['score_delta_points'] >= a.min_score_delta,
      'leakage_not_worse': q['tuned_answer_leak_rate'] <= q['base_answer_leak_rate'],
      'question_rate_not_worse': q['tuned_question_rate'] >= q['base_question_rate'],
    }
    passed=all(checks.values())
    out={'passed':passed,'checks':checks,'min_score_delta':a.min_score_delta,'recommendation':'Ready for hackathon evidence.' if passed else 'Increase/adjust fine-tuning steps or data mix, rerun benchmark, and use measured results only.'}
    Path(a.output).write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2))
    if a.strict and not passed: sys.exit(3)
if __name__=='__main__': main()
