from __future__ import annotations
import hashlib,json,time,uuid
from contextlib import contextmanager
from typing import Any
from prometheus_client import Counter,Histogram,Gauge,generate_latest,CONTENT_TYPE_LATEST
from ..db import db
from ..config import settings

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
    prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()
    response_hash=hashlib.sha256(response.encode()).hexdigest()
    prompt_preview=prompt[:4000] if settings.trace_content else ''
    response_preview=response[:6000] if settings.trace_content else ''
    safe_meta={**(metadata or {}),'prompt_sha256':prompt_hash,'response_sha256':response_hash,'content_stored':settings.trace_content}
    with db() as conn:
        conn.execute('''INSERT INTO agent_traces(id,user_id,project_id,thread_id,agent,route,model,prompt_preview,response_preview,retrieved_json,latency_ms,ttft_ms,input_tokens,output_tokens,tokens_per_second,success,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
            tid,user_id,project_id,thread_id,agent,route,model,prompt_preview,response_preview,json.dumps(retrieved or []),latency_ms,ttft_ms,input_tokens,output_tokens,tps,int(success),json.dumps(safe_meta)
        ))
    # Optional hosted trace export. It is OFF unless the operator explicitly supplies
    # LANGSMITH_API_KEY; the local PostgreSQL trace store is always the source of truth.
    try:
        if settings.langsmith_api_key and settings.trace_content:
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

def recent_traces(limit:int=100,org_id:str|None=None)->list[dict[str,Any]]:
    with db() as conn:
        rows=conn.execute('''SELECT t.* FROM agent_traces t LEFT JOIN projects p ON p.id=t.project_id
                             LEFT JOIN users u ON u.id=t.user_id WHERE COALESCE(p.org_id,u.org_id)=?
                             ORDER BY t.created_at DESC LIMIT ?''',(org_id,limit)).fetchall() if org_id else []
    out=[]
    for r in rows:
        d=dict(r); d['retrieved']=json.loads(d.pop('retrieved_json') or '[]'); d['metadata']=json.loads(d.pop('metadata_json') or '{}'); out.append(d)
    return out
