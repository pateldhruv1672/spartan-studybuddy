#!/usr/bin/env python3
"""Measure StudyBuddy Browser-Use agent pipeline latency/throughput.
Run this on the Mac while the Browser-Use bridge is active.
"""
from __future__ import annotations
import argparse, json, math, statistics, time
from pathlib import Path
import httpx

TASKS = [
    "Find two authoritative beginner resources that teach self-attention. Return title, URL, type, and why each is useful.",
    "Find two high-quality resources for learning convolution output shapes, preferably one video and one written reference.",
    "Find two resources explaining BFS versus DFS for a student who confuses queue and stack behavior.",
]

def percentile(v,p):
    x=sorted(v); return x[min(len(x)-1,max(0,math.ceil(p*len(x))-1))] if x else 0.0

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--api',default='http://127.0.0.1:8000'); ap.add_argument('--jobs',type=int,default=3); ap.add_argument('--label',default='vllm-browser'); ap.add_argument('--poll',type=float,default=1.0); ap.add_argument('--timeout',type=float,default=240); ap.add_argument('--output'); a=ap.parse_args()
    client=httpx.Client(timeout=30); created=[]; start_wall=time.perf_counter()
    for i in range(a.jobs):
        payload={'user_id':'benchmark-agent','kind':'browser_resource_scout','requires_approval':False,'payload':{'task':TASKS[i%len(TASKS)],'mode':'benchmark'}}
        t=time.perf_counter(); r=client.post(a.api.rstrip('/')+'/api/agent/jobs',json=payload); r.raise_for_status(); created.append((r.json()['id'],t))
    remaining={jid:t for jid,t in created}; lat=[]
    deadline=time.perf_counter()+a.timeout
    while remaining and time.perf_counter()<deadline:
        for jid,t0 in list(remaining.items()):
            r=client.get(a.api.rstrip('/')+f'/api/agent/jobs/{jid}'); r.raise_for_status(); job=r.json()
            if job['status'] in {'completed','failed'}:
                lat.append(time.perf_counter()-t0); del remaining[jid]
        if remaining: time.sleep(a.poll)
    wall=time.perf_counter()-start_wall
    result={'label':a.label,'requested_jobs':a.jobs,'completed_jobs':len(lat),'timed_out_jobs':len(remaining),'wall_time_s':round(wall,3),'jobs_per_min':round(len(lat)/max(wall,0.001)*60,3),'latency_p50_s':round(statistics.median(lat),3) if lat else None,'latency_p95_s':round(percentile(lat,.95),3) if lat else None}
    text=json.dumps(result,indent=2); print(text)
    if a.output: Path(a.output).write_text(text,encoding='utf-8')
if __name__=='__main__': main()
