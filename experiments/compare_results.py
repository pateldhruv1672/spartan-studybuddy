#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path


def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def pct(a,b): return None if b == 0 else round((a-b)/b*100,2)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base-eval',required=True); p.add_argument('--tuned-eval',required=True)
    p.add_argument('--base-bench'); p.add_argument('--tuned-bench'); p.add_argument('--spec-bench')
    p.add_argument('--output',default='experiments/results/summary.json')
    a=p.parse_args(); be=load(a.base_eval); te=load(a.tuned_eval)
    out={
      'socratic_quality': {
        'base_score':be['mean_rubric_score'],'tuned_score':te['mean_rubric_score'],
        'score_delta_points':round(te['mean_rubric_score']-be['mean_rubric_score'],2),
        'base_answer_leak_rate':be['answer_leak_rate'],'tuned_answer_leak_rate':te['answer_leak_rate'],
        'answer_leak_reduction_pct': round((be['answer_leak_rate']-te['answer_leak_rate'])/be['answer_leak_rate']*100,2) if be['answer_leak_rate'] else 0.0,
        'base_question_rate':be['probing_question_rate'],'tuned_question_rate':te['probing_question_rate'],
      }
    }
    if a.base_bench and a.tuned_bench:
      bb,tb=load(a.base_bench),load(a.tuned_bench)
      out['serving_base_vs_tuned']={
        'base_ttft_p50_s':bb['ttft_p50_s'],'tuned_ttft_p50_s':tb['ttft_p50_s'],
        'base_decode_tok_s_p50':bb['decode_tok_s_p50'],'tuned_decode_tok_s_p50':tb['decode_tok_s_p50'],
        'base_aggregate_tok_s':bb['aggregate_output_tok_s'],'tuned_aggregate_tok_s':tb['aggregate_output_tok_s'],
      }
    if a.tuned_bench and a.spec_bench:
      tb,sb=load(a.tuned_bench),load(a.spec_bench)
      out['speculative_decoding']={
        'baseline_profile':tb['profile'],'spec_profile':sb['profile'],
        'ttft_change_pct':pct(sb['ttft_p50_s'],tb['ttft_p50_s']),
        'decode_tok_s_change_pct':pct(sb['decode_tok_s_p50'],tb['decode_tok_s_p50']),
        'aggregate_tok_s_change_pct':pct(sb['aggregate_output_tok_s'],tb['aggregate_output_tok_s']),
        'baseline_decode_tok_s_p50':tb['decode_tok_s_p50'],'spec_decode_tok_s_p50':sb['decode_tok_s_p50'],
        'baseline_ttft_p50_s':tb['ttft_p50_s'],'spec_ttft_p50_s':sb['ttft_p50_s'],
      }
    path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out,indent=2))
if __name__=='__main__': main()
