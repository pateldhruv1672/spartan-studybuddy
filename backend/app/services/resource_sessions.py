from __future__ import annotations
import json,uuid
from ..db import db
from .model_router import router
from .memory import add_memory

async def upsert_session(user_id:str,project_id:str|None,url:str,title:str,resource_type:str,seconds_active:float,progress:float,last_position:float,duration:float|None,visible_text:str|None,concepts:list[str])->dict:
    sid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{user_id}:{project_id}:{url}'))
    with db() as conn:
        old=conn.execute('SELECT * FROM resource_sessions WHERE id=?',(sid,)).fetchone()
        total_seconds=max(float(old['seconds_active']) if old else 0,0)+max(seconds_active,0)
        summary=old['summary'] if old else None; checkpoint=json.loads(old['checkpoint_json']) if old else []
        merged=list(dict.fromkeys((json.loads(old['concepts_json']) if old else [])+concepts))[:20]
        conn.execute('''INSERT INTO resource_sessions(id,user_id,project_id,resource_url,resource_title,resource_type,seconds_active,progress,last_position,duration,summary,concepts_json,checkpoint_json,last_seen_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
          ON CONFLICT(id) DO UPDATE SET seconds_active=excluded.seconds_active,progress=GREATEST(resource_sessions.progress,excluded.progress),last_position=excluded.last_position,duration=COALESCE(excluded.duration,resource_sessions.duration),resource_title=excluded.resource_title,concepts_json=excluded.concepts_json,last_seen_at=CURRENT_TIMESTAMP''',
          (sid,user_id,project_id,url,title,resource_type,total_seconds,max(0,min(1,progress)),last_position,duration,summary,json.dumps(merged),json.dumps(checkpoint)))
    # Create a concise resume brief once a learner has meaningful progress. Visible text is intentionally truncated.
    if progress>.08 and (not summary or progress>.85):
        text=(visible_text or '')[:7000]
        prompt=f'Resource: {title}\nType: {resource_type}\nProgress: {progress:.0%}\nConcepts observed: {merged}\nVisible/transcript excerpt:\n{text}'
        result=await router.json(system='Create a private learning-resume card. Return JSON: summary (2-4 sentences), concepts (array), questions (2 short recall questions). Do not claim the learner mastered material merely because it was viewed.',user=prompt,tier='instruct',fallback={'summary':f'You were working through {title}.','concepts':merged,'questions':['What was the central idea you encountered?','What would you like clarified before continuing?']})
        summary=str(result.get('summary') or '')[:3000]; checkpoint=result.get('questions') or []
        merged=list(dict.fromkeys(merged+(result.get('concepts') or [])))[:20]
        with db() as conn: conn.execute('UPDATE resource_sessions SET summary=?,concepts_json=?,checkpoint_json=? WHERE id=?',(summary,json.dumps(merged),json.dumps(checkpoint[:4]),sid))
        add_memory(user_id,project_id,'resource_resume',title,summary,.55,{'url':url,'progress':progress,'last_position':last_position})
    return get_session(user_id,project_id,url)

def get_session(user_id:str,project_id:str|None,url:str)->dict:
    sid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{user_id}:{project_id}:{url}'))
    with db() as conn:r=conn.execute('SELECT * FROM resource_sessions WHERE id=?',(sid,)).fetchone()
    if not r:return {}
    d=dict(r); d['concepts']=json.loads(d.pop('concepts_json') or '[]'); d['questions']=json.loads(d.pop('checkpoint_json') or '[]'); return d

def resume_feed(user_id:str,project_id:str|None=None,limit:int=12)->list[dict]:
    q='SELECT * FROM resource_sessions WHERE user_id=?'; p=[user_id]
    if project_id:q+=' AND project_id=?';p.append(project_id)
    q+=' ORDER BY last_seen_at DESC LIMIT ?';p.append(limit)
    with db() as conn:rows=conn.execute(q,p).fetchall()
    out=[]
    for r in rows:
        d=dict(r); d['concepts']=json.loads(d.pop('concepts_json') or '[]');d['questions']=json.loads(d.pop('checkpoint_json') or '[]');out.append(d)
    return out
