#!/usr/bin/env python3
from __future__ import annotations
import json, os, time, urllib.request
KEY=os.getenv('VLLM_API_KEY','local-edge')
base=os.getenv('VLLM_INSTRUCT_URL','http://127.0.0.1:8101/v1').rstrip('/')
model=os.getenv('VLLM_INSTRUCT_MODEL','spartan-teacher')

def post(url,payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {KEY}'})
    t=time.perf_counter()
    with urllib.request.urlopen(req,timeout=240) as r: body=json.loads(r.read())
    return body,time.perf_counter()-t
for name,thinking in [('teacher-fast',False),('teacher-reasoning',True)]:
    body,elapsed=post(base+'/chat/completions',{'model':model,'messages':[{'role':'user','content':'Reply with exactly: Spartan ready'}],'temperature':0,'max_tokens':64,'chat_template_kwargs':{'enable_thinking':thinking}})
    print(f"{name:20} {elapsed:6.2f}s {body['choices'][0]['message'].get('content')!r}")
emb=os.getenv('EMBEDDING_URL','http://127.0.0.1:8105/v1').rstrip('/')
emb_model=os.getenv('EMBEDDING_MODEL','Qwen/Qwen3-Embedding-0.6B')
body,elapsed=post(emb+'/embeddings',{'model':emb_model,'input':['dependency injection in a Python service']})
print(f"{'embeddings':20} {elapsed:6.2f}s dims={len(body['data'][0]['embedding'])}")
