from __future__ import annotations
import json,uuid
from typing import Any
from ..db import db
from .event_store import recent_events

def add_memory(user_id:str,project_id:str|None,kind:str,title:str,content:str,importance:float=.5,metadata:dict|None=None)->dict:
    mid=str(uuid.uuid4())
    with db() as conn: conn.execute('INSERT INTO memory_items(id,user_id,project_id,kind,title,content,importance,metadata_json) VALUES(?,?,?,?,?,?,?,?)',(mid,user_id,project_id,kind,title,content,importance,json.dumps(metadata or {})))
    return {'id':mid,'title':title,'kind':kind}
def memories(user_id:str,project_id:str|None=None,limit:int=30)->list[dict[str,Any]]:
    sql='SELECT * FROM memory_items WHERE user_id=?'; p=[user_id]
    if project_id: sql+=' AND (project_id=? OR project_id IS NULL)'; p.append(project_id)
    sql+=' ORDER BY importance DESC,created_at DESC LIMIT ?'; p.append(limit)
    with db() as conn: rows=conn.execute(sql,p).fetchall()
    out=[]
    for r in rows:
        d=dict(r); d['metadata']=json.loads(d.pop('metadata_json') or '{}'); out.append(d)
    return out
def update_mastery(user_id:str,project_id:str,topic:str,score:float,evidence:dict|None=None)->dict:
    score=max(0,min(1,score))
    with db() as conn:
        r=conn.execute('SELECT score,confidence,evidence_json FROM mastery WHERE user_id=? AND project_id=? AND topic=?',(user_id,project_id,topic)).fetchone()
        if r:
            old=float(r['score']); conf=min(1,float(r['confidence'])+.08); ev=json.loads(r['evidence_json']); ev=(ev+[evidence or {'score':score}])[-20:]; new=old*.75+score*.25
            conn.execute('UPDATE mastery SET score=?,confidence=?,evidence_json=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND project_id=? AND topic=?',(new,conf,json.dumps(ev),user_id,project_id,topic))
        else:
            new=score; conf=.25; conn.execute('INSERT INTO mastery(user_id,project_id,topic,score,confidence,evidence_json) VALUES(?,?,?,?,?,?)',(user_id,project_id,topic,new,conf,json.dumps([evidence or {'score':score}])))
    return {'topic':topic,'score':new,'confidence':conf}
def snapshot(user_id:str,project_id:str)->dict[str,Any]:
    with db() as conn: mastery=[dict(r) for r in conn.execute('SELECT topic,score,confidence,updated_at FROM mastery WHERE user_id=? AND project_id=? ORDER BY score',(user_id,project_id)).fetchall()]
    return {'user_id':user_id,'project_id':project_id,'mastery':mastery,'memories':memories(user_id,project_id,15),'recent_events':recent_events(user_id,project_id,25)}
