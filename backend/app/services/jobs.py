from __future__ import annotations
import json,uuid
from ..db import db
from .telemetry import AGENT_JOBS

def create_job(user_id:str,kind:str,payload:dict,project_id:str|None=None)->dict:
    jid=str(uuid.uuid4())
    with db() as conn:conn.execute('INSERT INTO agent_jobs(id,user_id,project_id,kind,status,payload_json) VALUES(?,?,?,?,?,?)',(jid,user_id,project_id,kind,'queued',json.dumps(payload)))
    AGENT_JOBS.labels(kind,'queued').inc();return get_job(jid)

def get_job(jid:str)->dict:
    with db() as conn:r=conn.execute('SELECT * FROM agent_jobs WHERE id=?',(jid,)).fetchone()
    if not r:raise KeyError(jid)
    d=dict(r);d['payload']=json.loads(d.pop('payload_json') or '{}');d['result']=json.loads(d.pop('result_json') or 'null');return d

def claim_jobs(limit:int=5)->list[dict]:
    with db() as conn:
        ids=[r[0] for r in conn.execute("SELECT id FROM agent_jobs WHERE status='queued' ORDER BY created_at LIMIT ?",(limit,)).fetchall()]
        for jid in ids:conn.execute("UPDATE agent_jobs SET status='running',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",(jid,))
    return [get_job(x) for x in ids]

def next_jobs(limit:int=10)->list[dict]:
    with db() as conn:ids=[r[0] for r in conn.execute("SELECT id FROM agent_jobs WHERE status='queued' ORDER BY created_at LIMIT ?",(limit,)).fetchall()]
    return [get_job(x) for x in ids]

def finish_job(jid:str,result:dict,status:str='completed')->dict:
    with db() as conn:
        row=conn.execute('SELECT kind FROM agent_jobs WHERE id=?',(jid,)).fetchone();conn.execute('UPDATE agent_jobs SET status=?,result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,json.dumps(result),jid))
    if row:AGENT_JOBS.labels(row['kind'],status).inc()
    return get_job(jid)
