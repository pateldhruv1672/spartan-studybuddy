from __future__ import annotations
import json,time,uuid
from contextlib import contextmanager
from typing import Any
from prometheus_client import Counter,Histogram,Gauge,generate_latest,CONTENT_TYPE_LATEST
from ..db import db

MODEL_REQUESTS=Counter('studybuddy_model_requests_total','Model requests',['route','success'])
MODEL_LATENCY=Histogram('studybuddy_model_latency_seconds','Model end-to-end latency',['route'],buckets=(.1,.25,.5,1,2,4,8,16,32,64,128))
MODEL_TTFT=Histogram('studybuddy_model_ttft_seconds','Model time to first token',['route'],buckets=(.05,.1,.25,.5,1,2,4,8,16,32))
MODEL_OUTPUT_TPS=Histogram('studybuddy_model_output_tokens_per_second','Model output token throughput',['route'],buckets=(1,5,10,20,30,40,60,80,120,200))
AGENT_JOBS=Counter('studybuddy_agent_jobs_total','Agent jobs',['kind','status'])
RAG_SEARCH=Histogram('studybuddy_rag_search_seconds','RAG retrieval latency',['mode'],buckets=(.005,.01,.025,.05,.1,.25,.5,1,2,5))
INDEXED_CHUNKS=Counter('studybuddy_indexed_chunks_total','Indexed chunks',['source_type'])
ACTIVE_CONNECTIONS=Gauge('studybuddy_websocket_connections','Active websocket connections')

def metrics_payload(): return generate_latest(), CONTENT_TYPE_LATEST

def trace(*,user_id:str|None,project_id:str|None,thread_id:str|None,agent:str,route:str|None,model:str|None,prompt:str,response:str,retrieved:list|None,latency_ms:float|None,ttft_ms:float|None,input_tokens:int|None,output_tokens:int|None,tps:float|None,success:bool=True,metadata:dict|None=None)->str:
    tid=str(uuid.uuid4())
    with db() as conn:
        conn.execute('''INSERT INTO agent_traces(id,user_id,project_id,thread_id,agent,route,model,prompt_preview,response_preview,retrieved_json,latency_ms,ttft_ms,input_tokens,output_tokens,tokens_per_second,success,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
            tid,user_id,project_id,thread_id,agent,route,model,prompt[:4000],response[:6000],json.dumps(retrieved or []),latency_ms,ttft_ms,input_tokens,output_tokens,tps,int(success),json.dumps(metadata or {})
        ))
    # Optional hosted trace export. It is OFF unless the operator explicitly supplies
    # LANGSMITH_API_KEY; the local PostgreSQL trace store is always the source of truth.
    try:
        from ..config import settings
        if settings.langsmith_api_key:
            from langsmith import Client
            Client(api_key=settings.langsmith_api_key).create_run(
                name=f"studybuddy:{agent}", run_type="chain",
                inputs={"prompt":prompt[:12000],"route":route,"retrieved":retrieved or []},
                outputs={"response":response[:16000]},
                project_name=settings.langsmith_project,
                tags=["spartan-studybuddy", route or "unknown", model or "unknown"],
                extra={"metadata":metadata or {},"local_trace_id":tid,"latency_ms":latency_ms,"ttft_ms":ttft_ms,"tps":tps},
            )
    except Exception as exc:
        # Telemetry exporters must never take down tutoring/inference.
        print(f"LangSmith export skipped: {exc}")
    return tid

def recent_traces(limit:int=100)->list[dict[str,Any]]:
    with db() as conn: rows=conn.execute('SELECT * FROM agent_traces ORDER BY created_at DESC LIMIT ?',(limit,)).fetchall()
    out=[]
    for r in rows:
        d=dict(r); d['retrieved']=json.loads(d.pop('retrieved_json') or '[]'); d['metadata']=json.loads(d.pop('metadata_json') or '{}'); out.append(d)
    return out
