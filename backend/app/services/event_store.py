from __future__ import annotations
import json,uuid
from typing import Any
from ..db import db
from ..models import LearningEventIn

def record_event(e:LearningEventIn)->dict[str,Any]:
    eid=e.event_id or str(uuid.uuid4())
    with db() as conn:conn.execute('INSERT OR IGNORE INTO learning_events(id,user_id,project_id,source,type,resource_id,context_json) VALUES(?,?,?,?,?,?,?)',(eid,e.user_id,e.project_id,e.source,e.type,e.resource_id,json.dumps(e.context)))
    return {'id':eid,'recorded':True}

def recent_events(user_id:str,project_id:str|None=None,limit:int=50)->list[dict[str,Any]]:
    sql='SELECT * FROM learning_events WHERE user_id=?';params=[user_id]
    if project_id:sql+=' AND project_id=?';params.append(project_id)
    sql+=' ORDER BY created_at DESC LIMIT ?';params.append(limit)
    with db() as conn:rows=conn.execute(sql,params).fetchall()
    out=[]
    for r in rows:d=dict(r);d['context']=json.loads(d.pop('context_json') or '{}');out.append(d)
    return out

def admin_stats(org_id:str)->dict[str,Any]:
    with db() as conn:
        q=lambda sql,args=():conn.execute(sql,args).fetchone()[0]
        projects=q('SELECT COUNT(*) FROM projects WHERE org_id=?',(org_id,));users=q('SELECT COUNT(*) FROM users WHERE org_id=?',(org_id,));docs=q('SELECT COUNT(*) FROM indexed_documents d JOIN projects p ON p.id=d.project_id WHERE p.org_id=?',(org_id,));chunks=q('SELECT COUNT(*) FROM indexed_chunks c JOIN projects p ON p.id=c.project_id WHERE p.org_id=?',(org_id,));paths=q('SELECT COUNT(*) FROM onboarding_paths o JOIN projects p ON p.id=o.project_id WHERE p.org_id=?',(org_id,));events=q('SELECT COUNT(*) FROM learning_events');traces=q('SELECT COUNT(*) FROM agent_traces')
        events=q('SELECT COUNT(*) FROM learning_events e JOIN users u ON u.id=e.user_id WHERE u.org_id=?',(org_id,))
        traces=q('SELECT COUNT(*) FROM agent_traces t JOIN projects p ON p.id=t.project_id WHERE p.org_id=?',(org_id,))
    from .leaderboard import leaderboard
    top=leaderboard(org_id)[:10]
    return {'projects':projects,'users':users,'documents':docs,'chunks':chunks,'onboarding_paths':paths,'events':events,'agent_traces':traces,'leaderboard':top}
