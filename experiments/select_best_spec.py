#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(); p.add_argument('--tuned',required=True); p.add_argument('--ngram'); p.add_argument('--eagle3'); p.add_argument('--output',default='experiments/results/spec_selection.json'); a=p.parse_args()
    base=json.loads(Path(a.tuned).read_text())
    choices=[]
    for method,path in [('ngram',a.ngram),('eagle3',a.eagle3)]:
        if path and Path(path).exists():
            d=json.loads(Path(path).read_text())
            # Interactive objective: prioritize decode speed, reject >25% TTFT regression.
            ttft_ratio=d['ttft_p50_s']/max(base['ttft_p50_s'],1e-6)
            speed_ratio=d['decode_tok_s_p50']/max(base['decode_tok_s_p50'],1e-6)
            aggregate_ratio=d['aggregate_output_tok_s']/max(base['aggregate_output_tok_s'],1e-6)
            eligible=ttft_ratio <= 1.25 and (speed_ratio > 1.02 or aggregate_ratio > 1.02)
            score=(0.65*speed_ratio + 0.35*aggregate_ratio) / max(1.0, ttft_ratio)
            choices.append({'method':method,'path':path,'eligible':eligible,'score':score,'ttft_ratio':ttft_ratio,'speed_ratio':speed_ratio,'aggregate_ratio':aggregate_ratio})
    eligible=[c for c in choices if c['eligible']]
    best=max(eligible,key=lambda x:x['score']) if eligible else {'method':'none','path':a.tuned,'eligible':True,'score':1.0}
    out={'recommended_method':best['method'],'baseline':a.tuned,'candidates':choices,'reason':'Measured on DGX Spark; speculation selected only when it improves the interactive workload without a large TTFT regression.'}
    Path(a.output).write_text(json.dumps(out,indent=2),encoding='utf-8')
    env=Path(a.output).with_name('recommended_serving.env'); env.write_text(f"SPECULATION_METHOD={best['method']}\nUSE_TUNED_SOCRATIC_MODEL=1\n",encoding='utf-8')
    print(json.dumps(out,indent=2))
if __name__=='__main__': main()
