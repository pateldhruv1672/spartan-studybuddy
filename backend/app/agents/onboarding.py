from __future__ import annotations
import json,secrets,uuid
from ..db import db
from ..services.indexer import project_map
from ..services.retrieval import retrieve,format_context
from ..services.model_router import router
from ..services.jobs import create_job

FALLBACK={
 'summary':'A role-specific onboarding path grounded in the indexed codebase.',
 'prerequisites':[{'concept':'Programming language fundamentals','priority':'essential','reason':'Required to read the codebase.'}],
 'modules':[{'id':'m1','title':'Architecture orientation','outcome':'Trace one request through the system','items':[{'id':'i1','type':'internal_walkthrough','title':'Repository map','minutes':25,'xp':80},{'id':'i2','type':'checkpoint','title':'Explain the core request path','minutes':10,'xp':100}]}],
 'exercises':[{'id':'e1','title':'Trace and explain a real execution path','difficulty':'beginner','acceptance':['Identify entry point','Identify dependencies','Explain one failure mode'],'xp':180}],
 'resource_search_topics':['software architecture fundamentals']
}

async def create_onboarding(user_id:str,project_id:str,target_role:str,level:str,weeks:int,hours_per_week:int,background:str='',is_public:bool=False)->dict:
    pmap=project_map(project_id)
    hits=await retrieve(project_id,f'architecture setup entry point tests API pipeline data model dependencies {target_role}',top_k=14,rerank=True)
    evidence=format_context(hits,22000)
    compact={'documents':pmap['documents'],'languages':pmap['languages'],'symbols':[{'name':s['name'],'kind':s['kind'],'language':s['language']} for s in pmap['symbols'][:240]],'edges':pmap['edges'][:240]}
    prompt=f'''Create a {weeks}-week gamified onboarding curriculum for a {level} {target_role}. Time budget: {hours_per_week} hours/week. Background: {background or 'unknown'}.
Repository map: {json.dumps(compact)}
Private evidence:\n{evidence}
Return JSON with:
summary,
prerequisites[] (concept,priority,reason),
modules[] where each module has id,title,outcome,items[]; each item has id,type,title,minutes,xp,repo_refs[],topic,checkpoint_question,
exercises[] with id,title,difficulty,description,repo_refs[],acceptance[],xp,
resource_search_topics[].
The sequence must teach generic prerequisites before internal code, then guided codebase walkthroughs, then role-specific exercises and checkpoints. Use real repository evidence. External search topics MUST contain generic concepts only: never private function names, filenames, company names, source snippets, secrets or business logic.'''
    plan=await router.json(system='You are an elite engineering enablement architect. Build evidence-grounded, role-specific curricula that move a new hire from prerequisites to safe contribution.',user=prompt,tier='reasoning',fallback=FALLBACK,user_id=user_id,project_id=project_id,agent='onboarding_planner',retrieved=[{'citation':x.get('citation'),'source':x.get('source_name')} for x in hits])
    path_id=str(uuid.uuid4()); invite_code=secrets.token_urlsafe(6);title=f'{target_role} · {weeks}-week onboarding'
    with db() as conn:
        conn.execute('INSERT INTO onboarding_paths(id,project_id,creator_id,title,target_role,level,weeks,hours_per_week,is_public,invite_code,plan_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(path_id,project_id,user_id,title,target_role,level,weeks,hours_per_week,int(is_public),invite_code,json.dumps(plan)))
        conn.execute('INSERT OR IGNORE INTO onboarding_members(path_id,user_id) VALUES(?,?)',(path_id,user_id))
    topics=[str(x) for x in (plan.get('resource_search_topics') or [])[:12] if x]
    job=create_job(user_id,'resource_scout',{'mode':'onboarding','path_id':path_id,'topics':topics,'instruction':'Find authoritative public resources for these SANITIZED generic concepts. Include YouTube, official docs, strong engineering blogs, books/catalog references, arXiv/research papers when appropriate. Return structured resources with topic mapping and estimated learning time. Never search private repository identifiers.'},project_id) if topics else None
    return get_path(path_id,user_id)|{'resource_job':job}

def _progress_item_ids(plan:dict)->list[str]:
    ids=[]
    for m in plan.get('modules',[]):
        for x in m.get('items',[]):
            if x.get('id'):ids.append(x['id'])
    for x in plan.get('exercises',[]):
        if x.get('id'):ids.append(x['id'])
    return ids

def get_path(path_id:str,user_id:str|None=None)->dict:
    with db() as conn:
        r=conn.execute('SELECT * FROM onboarding_paths WHERE id=?',(path_id,)).fetchone()
        if not r:raise KeyError(path_id)
        d=dict(r);d['plan']=json.loads(d.pop('plan_json'));d['is_public']=bool(d['is_public'])
        d['members']=[dict(x) for x in conn.execute('''SELECT m.*,u.display_name,u.role_title,u.avatar FROM onboarding_members m LEFT JOIN users u ON u.id=m.user_id WHERE m.path_id=? ORDER BY m.xp DESC,m.progress DESC''',(path_id,)).fetchall()]
        d['resources']=[]
        for x in conn.execute('SELECT * FROM path_resources WHERE path_id=? ORDER BY module_id,created_at',(path_id,)).fetchall():
            z=dict(x);z['metadata']=json.loads(z.pop('metadata_json') or '{}');d['resources'].append(z)
        d['progress_items']=[]
        if user_id:d['progress_items']=[dict(x) for x in conn.execute('SELECT * FROM path_progress WHERE path_id=? AND user_id=?',(path_id,user_id)).fetchall()]
    return d

def list_paths(project_id:str,user_id:str)->list[dict]:
    with db() as conn:rows=conn.execute('''SELECT DISTINCT p.* FROM onboarding_paths p LEFT JOIN onboarding_members m ON m.path_id=p.id WHERE p.project_id=? AND (p.creator_id=? OR p.is_public=1 OR m.user_id=?) ORDER BY p.created_at DESC''',(project_id,user_id,user_id)).fetchall()
    out=[]
    for r in rows:
        d=dict(r);d['plan']=json.loads(d.pop('plan_json'));d['is_public']=bool(d['is_public']);out.append(d)
    return out

def join_path(path_id:str,user_id:str,invite_code:str|None=None)->dict:
    with db() as conn:
        p=conn.execute('SELECT invite_code,is_public FROM onboarding_paths WHERE id=?',(path_id,)).fetchone()
        if not p:raise KeyError(path_id)
        if not p['is_public'] and invite_code!=p['invite_code']:raise PermissionError('Invite code required')
        conn.execute('INSERT OR IGNORE INTO onboarding_members(path_id,user_id) VALUES(?,?)',(path_id,user_id))
    return get_path(path_id,user_id)

def add_resources(path_id:str,resources:list[dict])->int:
    count=0
    with db() as conn:
        for r in resources:
            url=str(r.get('url') or '').strip();title=str(r.get('title') or '').strip()
            if not url or not title:continue
            rid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{path_id}:{url}'))
            conn.execute('''INSERT INTO path_resources(id,path_id,module_id,title,url,resource_type,source,rationale,estimated_minutes,metadata_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET path_id=excluded.path_id,module_id=excluded.module_id,title=excluded.title,url=excluded.url,
                resource_type=excluded.resource_type,source=excluded.source,rationale=excluded.rationale,
                estimated_minutes=excluded.estimated_minutes,metadata_json=excluded.metadata_json''',
                (rid,path_id,r.get('module_id') or r.get('topic'),title,url,r.get('resource_type') or r.get('type'),r.get('source'),r.get('why') or r.get('rationale'),int(r.get('estimated_minutes') or 15),json.dumps({k:v for k,v in r.items() if k not in {'url','title'}})))
            count+=1
    return count

def update_progress(path_id:str,user_id:str,item_id:str,status:str,progress:float,score:float|None=None)->dict:
    with db() as conn:
        p=conn.execute('SELECT plan_json FROM onboarding_paths WHERE id=?',(path_id,)).fetchone()
        if not p:raise KeyError(path_id)
        plan=json.loads(p['plan_json']);valid=set(_progress_item_ids(plan));
        if valid and item_id not in valid:raise KeyError(item_id)
        old=conn.execute('SELECT status FROM path_progress WHERE path_id=? AND user_id=? AND item_id=?',(path_id,user_id,item_id)).fetchone()
        conn.execute('''INSERT INTO path_progress(path_id,user_id,item_id,status,progress,score) VALUES(?,?,?,?,?,?) ON CONFLICT(path_id,user_id,item_id) DO UPDATE SET status=excluded.status,progress=excluded.progress,score=COALESCE(excluded.score,path_progress.score),updated_at=CURRENT_TIMESTAMP''',(path_id,user_id,item_id,status,progress,score))
        done=conn.execute("SELECT COUNT(*) FROM path_progress WHERE path_id=? AND user_id=? AND status='completed'",(path_id,user_id)).fetchone()[0]
        total=max(len(valid),1);overall=min(1,done/total)
        xp_gain=0
        if status=='completed' and (not old or old['status']!='completed'):
            xp_gain=100 + (int(max(0,min(1,score))*50) if score is not None else 0)
        conn.execute('INSERT OR IGNORE INTO onboarding_members(path_id,user_id) VALUES(?,?)',(path_id,user_id));conn.execute('UPDATE onboarding_members SET progress=?,xp=xp+? WHERE path_id=? AND user_id=?',(overall,xp_gain,path_id,user_id))
        member=conn.execute('SELECT xp,progress,streak FROM onboarding_members WHERE path_id=? AND user_id=?',(path_id,user_id)).fetchone()
    return {'path_id':path_id,'item_id':item_id,'status':status,'progress':progress,'overall':overall,'xp_delta':xp_gain,'xp':member['xp'],'streak':member['streak']}
