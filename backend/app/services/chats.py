from __future__ import annotations
import json,uuid
from ..db import db

def ensure_thread(user_id:str,project_id:str,title:str='StudyBuddy',mode:str='auto',thread_id:str|None=None)->str:
    if thread_id:
        with db() as conn:
            row = conn.execute('SELECT user_id,project_id FROM chat_threads WHERE id=?',(thread_id,)).fetchone()
            if not row or row['user_id'] != user_id or row['project_id'] != project_id:
                raise PermissionError('Conversation is unavailable in this workspace.')
            return thread_id
    tid=str(uuid.uuid4())
    with db() as conn:conn.execute('INSERT INTO chat_threads(id,user_id,project_id,title,mode) VALUES(?,?,?,?,?)',(tid,user_id,project_id,title,mode))
    return tid

def add_message(thread_id:str,role:str,content:str,sources:list|None=None,route:str|None=None,status:str='completed',metadata:dict|None=None)->str:
    mid=str(uuid.uuid4())
    with db() as conn:
        conn.execute('INSERT INTO chat_messages(id,thread_id,role,content,sources_json,route,status,metadata_json) VALUES(?,?,?,?,?,?,?,?)',(mid,thread_id,role,content,json.dumps(sources or []),route,status,json.dumps(metadata or {})))
        conn.execute('UPDATE chat_threads SET updated_at=CURRENT_TIMESTAMP WHERE id=?',(thread_id,))
    return mid

def threads(user_id:str,project_id:str|None=None)->list[dict]:
    sql='SELECT * FROM chat_threads WHERE user_id=?';p=[user_id]
    if project_id:sql+=' AND project_id=?';p.append(project_id)
    sql+=' ORDER BY updated_at DESC'
    with db() as conn:return [dict(r) for r in conn.execute(sql,p).fetchall()]

def messages(thread_id:str)->list[dict]:
    with db() as conn:rows=conn.execute('SELECT * FROM chat_messages WHERE thread_id=? ORDER BY created_at',(thread_id,)).fetchall()
    out=[]
    for r in rows:
        d=dict(r);d['sources']=json.loads(d.pop('sources_json') or '[]')
        d['metadata']=json.loads(d.pop('metadata_json') or '{}')
        d['job_id']=d['metadata'].get('job_id')
        d['mode']=d.get('route');out.append(d)
    return out
