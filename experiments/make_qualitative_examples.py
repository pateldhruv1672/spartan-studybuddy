#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--base',required=True); p.add_argument('--tuned',required=True); p.add_argument('--cases',default='training/data/behavior_eval.jsonl'); p.add_argument('--output',default='experiments/results/QUALITATIVE_EXAMPLES.md'); a=p.parse_args()
    base=json.loads(Path(a.base).read_text()); tuned=json.loads(Path(a.tuned).read_text()); cases={json.loads(x)['id']:json.loads(x) for x in Path(a.cases).read_text().splitlines() if x.strip()}; b={x['id']:x for x in base['results']}; t={x['id']:x for x in tuned['results']}
    ids=sorted(b,key=lambda k:(t[k]['score']-b[k]['score']),reverse=True)[:5]
    out=['# Base vs fine-tuned qualitative examples','', '> Same neutral system prompt, held-out cases. These responses are captured from the running models.','']
    for k in ids:
        c=cases[k]; out += [f"## {k} — {c.get('domain','')}",'',f"**Student:** {c['prompt']}",'',f"**Base ({b[k]['score']}/100):** {b[k]['response']}",'',f"**Fine-tuned ({t[k]['score']}/100):** {t[k]['response']}",'']
    Path(a.output).write_text('\n'.join(out),encoding='utf-8'); print(a.output)
if __name__=='__main__': main()
