#!/usr/bin/env python3
"""Tiny latency benchmark for StudyBuddy's local vLLM tiers."""
from __future__ import annotations
import argparse, json, statistics, time
import httpx


def run(base: str, model: str, api_key: str, n: int) -> dict:
    lat=[]; ttft=[]
    for _ in range(n):
        start=time.perf_counter(); first=None; text=[]
        with httpx.stream('POST',base.rstrip('/')+'/chat/completions',headers={'Authorization':f'Bearer {api_key}'},json={'model':model,'messages':[{'role':'user','content':'Explain BFS in three concise sentences.'}],'stream':True,'max_tokens':120},timeout=60) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith('data: '): continue
                data=line[6:]
                if data=='[DONE]': break
                try:
                    chunk=json.loads(data); piece=chunk['choices'][0]['delta'].get('content') or ''
                    if piece and first is None:first=time.perf_counter()
                    text.append(piece)
                except Exception: pass
        end=time.perf_counter();lat.append(end-start);ttft.append((first or end)-start)
    return {'runs':n,'median_total_s':round(statistics.median(lat),3),'median_ttft_s':round(statistics.median(ttft),3),'p95_total_s':round(sorted(lat)[max(0,int(.95*len(lat))-1)],3)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--model',required=True);p.add_argument('--api-key',default='local-edge');p.add_argument('-n',type=int,default=5);a=p.parse_args();print(json.dumps(run(a.base,a.model,a.api_key,a.n),indent=2))
