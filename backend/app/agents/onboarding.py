from __future__ import annotations
import asyncio,copy,json,re,secrets,uuid
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

# Used instead of FALLBACK when no repository/document evidence is connected yet, so a failed or
# invalid model call never hands the learner a "trace the repository" plan for a repository that
# was never connected. Content here leans entirely on public resources (browser-use curates them),
# since there is no private codebase to walk through.
NO_REPO_FALLBACK={
 'summary':'A role-specific self-study curriculum built from public learning resources. Connect a repository later for codebase-grounded modules.',
 'prerequisites':[{'concept':'Core language and tooling fundamentals for the target role','priority':'essential','reason':'Needed before role-specific material makes sense.'}],
 'modules':[{'id':'m1','title':'Foundations','outcome':'Build the prerequisite mental models for this role','items':[{'id':'i1','type':'external_resource','title':'Curated public resource','minutes':30,'xp':60,'topic':'role fundamentals'},{'id':'i2','type':'checkpoint','title':'Summarize what you learned in your own words','minutes':10,'xp':80}]}],
 'exercises':[{'id':'e1','title':'Build a small project applying the core concepts for this role','difficulty':'beginner','acceptance':['Apply at least two core concepts','Explain one design decision you made'],'xp':180}],
 'resource_search_topics':['role fundamentals self-study roadmap']
}

class GraphNotReady(RuntimeError):
    pass


async def _llm_skeleton(user_id:str,project_id:str,target_role:str,level:str,weeks:int,hours_per_week:int,background:str,has_repo:bool,approx_modules:int,compact:dict|None,evidence:str,hits:list)->dict|None:
    """Stage 1: one small, holistic call that only decides curriculum SHAPE (summary, prerequisites,
    one final exercise, module id/title/outcome/topic) -- deliberately excludes items[], since deciding
    per-module content is a separate, narrower question handled by _llm_module_items(). Keeping this
    call's own output small and its schema unambiguous matters because of two failure modes measured
    directly against this model: (1) with thinking on, a large/loosely-scoped ask made it redraft the
    same content inside <think> repeatedly ("let me make these more specific") until the whole token
    budget was gone before it ever reached the JSON -- fixed by calling router.json() (enable_thinking
    defaults to False there); (2) even with thinking off, an earlier version of this prompt that didn't
    explicitly forbid nesting exercises under each module got misread that way, so it started writing
    2 exercises x N modules and ran out of budget mid-object -- fixed by being explicit below that
    exercises is a single top-level array with exactly one entry, not a per-module field."""
    if has_repo:
        prompt=f"""Design the SHAPE of a {weeks}-week gamified onboarding curriculum for a {level} {target_role}. Time budget: {hours_per_week} hours/week. Background: {background or 'unknown'}.
Repository map: {json.dumps(compact)}
Private evidence:\n{evidence}
Return JSON with exactly these top-level keys:
summary (string),
prerequisites (array of {{concept,priority,reason}}),
modules (array of {{id,title,outcome,topic}} only -- topic = one generic, non-private search phrase for public resources on this module's subject, never private function/file/company names. Modules must NOT contain an "exercises" or "items" key),
exercises (top-level array with EXACTLY ONE entry: a single final applied project, {{id,title,difficulty,description,repo_refs,acceptance,xp}}).
The sequence must teach generic prerequisites before internal code, then guided codebase walkthroughs, then role-specific material, ending in that one applied project."""
    else:
        prompt=f"""Design the SHAPE of a {weeks}-week gamified self-study curriculum for a {level} {target_role}. Time budget: {hours_per_week} hours/week. Learner background: {background or 'unknown'}.
No company repository or internal documents are connected yet -- do not reference any codebase, internal files, or company-specific systems. Build entirely from general, publicly-available engineering knowledge appropriate to this role, level and background.
Design roughly {approx_modules} modules that together span the full {weeks} weeks (each module ~{max(1,round(weeks/approx_modules))} week(s) of material at {hours_per_week}h/week), moving from foundational prerequisites to progressively more advanced, role-specific material and a final applied project.
Return JSON with exactly these top-level keys:
summary (string),
prerequisites (array of {{concept,priority,reason}}),
modules (array of {{id,title,outcome,topic}} only -- topic = a distinct, specific public-search phrase for this module's subject, concrete and varied, not generic, since it drives a browser research agent that finds real videos/docs/articles/papers for it. Modules must NOT contain an "exercises" or "items" key),
exercises (top-level array with EXACTLY ONE entry: a single final applied project, {{id,title,difficulty,description,acceptance,xp}})."""
    fb=FALLBACK if has_repo else NO_REPO_FALLBACK
    skeleton_fb={
        'summary':fb['summary'],'prerequisites':fb['prerequisites'],'exercises':fb['exercises'],
        'modules':[{'id':m['id'],'title':m['title'],'outcome':m['outcome'],'topic':(m['items'][0].get('topic') if m.get('items') else 'role fundamentals')} for m in fb['modules']],
    }
    skeleton_max_tokens=min(3200,1000+approx_modules*230)
    skeleton=await router.json(system='You are an elite engineering enablement architect. Decide the SHAPE of an evidence-grounded, role-specific curriculum that moves a new hire from prerequisites to safe contribution. Do not write module items yet.',user=prompt,tier='reasoning',fallback=skeleton_fb,max_tokens=skeleton_max_tokens,user_id=user_id,project_id=project_id,agent='onboarding_skeleton',retrieved=[{'citation':x.get('citation'),'source':x.get('source_name')} for x in hits])
    if skeleton is skeleton_fb or not isinstance(skeleton.get('modules'),list) or not skeleton['modules']:
        return None
    return skeleton


async def _llm_module_items(user_id:str,project_id:str,target_role:str,level:str,background:str,has_repo:bool,module:dict,target_minutes:int)->list[dict]:
    """Stage 2: one bounded call per module, scoped ONLY to that module's own title/outcome/topic.
    Run concurrently (asyncio.gather in _llm_plan) across all modules -- each call reasons about a
    narrow question, so its think+answer token cost stays roughly constant regardless of how many
    weeks/modules the overall curriculum has, unlike asking for every module's items in one call.
    Falls back to a 2-item stub for JUST this module on failure, instead of failing the whole plan.

    target_minutes is this module's fair share of the learner's stated hours_per_week -- previously
    the model picked each item's "minutes" with no connection to the time budget at all, so a
    4h/week learner and a 20h/week learner got the same generic ~30-minute items. This is also what
    later tells the browser-use resource scout roughly how long a resource for this topic should be."""
    mid=module.get('id') or 'm1'; topic=module.get('topic') or 'role fundamentals'
    stub=[{'id':f'{mid}-i1','type':'external_resource','title':'Curated public resource','minutes':max(10,round(target_minutes*.7)),'xp':60,'topic':topic},
          {'id':f'{mid}-i2','type':'checkpoint','title':'Summarize what you learned in your own words','minutes':max(5,round(target_minutes*.3)),'xp':80}]
    item_type_hint="'external_resource', 'checkpoint' or 'exercise'" if not has_repo else "'internal_walkthrough', 'checkpoint' or 'exercise'"
    repo_field=',"repo_refs":[str]' if has_repo else ''
    prompt=f"""For one module of a {level} {target_role}'s onboarding curriculum (background: {background or 'unknown'}):
Module: "{module.get('title')}" -- outcome: {module.get('outcome')} -- subject/topic: "{topic}"
List 2-4 concrete learning items for THIS module only. The learner has about {target_minutes} minutes total for this module -- set each item's "minutes" to a realistic estimate for that item specifically (not a generic default), and keep the sum across all items close to {target_minutes}.
Return JSON: {{"items":[{{"id":str,"type":{item_type_hint},"title":str,"minutes":int,"xp":int,"topic":"{topic}"{repo_field}}}]}}
Every item's "topic" must be exactly "{topic}"."""
    out=await router.json(system='You are an elite engineering enablement architect. Write concrete, specific learning items for ONE onboarding module, sized to the learner\'s actual available time.',user=prompt,tier='reasoning',fallback={'items':stub},max_tokens=1400,user_id=user_id,project_id=project_id,agent='onboarding_module_items',metadata={'module_id':mid,'topic':topic,'target_minutes':target_minutes})
    items=out.get('items')
    return items if isinstance(items,list) and items else stub


async def _llm_plan(user_id:str,project_id:str,target_role:str,level:str,weeks:int,hours_per_week:int,background:str)->tuple[dict,list]:
    pmap=project_map(project_id)
    hits=await retrieve(project_id,f'architecture setup entry point tests API pipeline data model dependencies {target_role}',top_k=14,rerank=True)
    evidence=format_context(hits,22000)
    has_repo=bool(hits) or bool(pmap.get('documents')) or bool(pmap.get('symbols'))
    approx_modules=max(2,round(weeks/2))
    compact={'documents':pmap['documents'],'languages':pmap['languages'],'symbols':[{'name':s['name'],'kind':s['kind'],'language':s['language']} for s in pmap['symbols'][:240]],'edges':pmap['edges'][:240]} if has_repo else None
    fb=copy.deepcopy(FALLBACK if has_repo else NO_REPO_FALLBACK)      # never hand out (or mutate) the shared module-level template

    skeleton=await _llm_skeleton(user_id,project_id,target_role,level,weeks,hours_per_week,background,has_repo,approx_modules,compact,evidence,hits)
    if skeleton is None:
        # Skeleton (curriculum shape) itself failed/invalid: no per-module calls to make, fall all the way back.
        plan=fb
        warning='The local model was unavailable or returned invalid output, so this is a generic placeholder roadmap' + ('.' if has_repo else ', not one generated for your role/background.') + ' Review or regenerate it before sharing.'
        plan['meta']={'provenance':'fallback','requires_review':True,'warning':warning,'has_repo':has_repo}
        return plan,hits

    # Each module's fair share of the learner's stated weekly time budget, spread over however many
    # weeks that module covers (weeks/approx_modules per module, hours_per_week hours each week).
    module_target_minutes=max(15,round((weeks/approx_modules)*hours_per_week*60))
    # Fan out: each module's items are an independent, narrow question, so generate them concurrently
    # rather than paying for N modules' worth of thinking-mode overhead serially in one call.
    item_lists=await asyncio.gather(*[_llm_module_items(user_id,project_id,target_role,level,background,has_repo,m,module_target_minutes) for m in skeleton['modules']])
    modules=[{'id':m.get('id') or f'm{i+1}','title':m.get('title','Module'),'outcome':m.get('outcome',''),'items':items} for i,(m,items) in enumerate(zip(skeleton['modules'],item_lists))]
    # Per-topic time target for the resource scout: the external_resource item's own "minutes"
    # (now sized to the learner's time budget above), keyed by the same topic string used to
    # dispatch the browser-use job -- so "find a resource for X" also carries "...that takes about
    # Y minutes", instead of the scout picking whatever length it happens to find.
    topic_target_minutes={it['topic']:it['minutes'] for m in modules for it in m['items'] if it.get('type')=='external_resource' and it.get('topic') and isinstance(it.get('minutes'),int)}
    plan={
        'summary':skeleton.get('summary') or fb['summary'],
        'prerequisites':skeleton.get('prerequisites') or fb['prerequisites'],
        'modules':modules,
        'exercises':skeleton.get('exercises') or fb['exercises'],
        'resource_search_topics':[m.get('topic') for m in skeleton['modules'] if m.get('topic')],
        'topic_target_minutes':topic_target_minutes,
        'meta':{'provenance':'generated','has_repo':has_repo},
    }
    return plan,hits

def _attach_quizzes(project_id:str,plan:dict)->dict:
    """Give a legacy (LLM-only) plan a quiz every other module (not every module -- appending one to
    every single module made short curricula feel dominated by quizzes rather than learning content,
    since most modules only have 2-4 items to begin with), seeded from the graph nodes its repo_refs
    point at when a repo is connected. A no-repo path has no graph to seed from (quiz_seed stays
    empty node_ids) -- this used to bail out entirely in that case, meaning no-repo paths never got
    a quiz item at all; generate_quizzes_no_repo() (writes questions from the module's own text
    instead of graph evidence) is what actually needs these items to exist."""
    from ..graph.view import load_view
    from ..graph.curriculum import PASS_THRESHOLD
    v=load_view(project_id)
    by_path={n['path']:i for i,n in v.nodes.items() if n['path'] and n['kind'] in ('file','doc')} if v is not None else {}
    for mi,m in enumerate(plan.get('modules',[])):
        m.setdefault('id',f'm{mi}')
        items=[it for it in m.get('items',[]) if it.get('type')!='quiz']
        for k,it in enumerate(items):it.setdefault('id',f"{m['id']}-i{k+1}")
        if mi%2==1:
            refs=[by_path[r] for it in items for r in it.get('repo_refs',[]) if r in by_path]
            items=items+[{'id':f"{m['id']}-quiz",'type':'quiz','title':'Section quiz','minutes':9,'xp':70,'topic':'Check your understanding','quiz':{'question_count':5,'pass_threshold':PASS_THRESHOLD}}]
            m['quiz_seed']={'node_ids':refs,'concept_ids':[],'kind':'subsystem'}
        m['items']=items
    plan['meta']={**plan.get('meta',{}),'engine':'llm','quiz_pass_threshold':PASS_THRESHOLD,'gating':False}
    return plan

async def _polish(plan:dict,user_id:str,project_id:str)->dict:
    """Optional wording polish by the local model. Structure, ids and refs are never touched; any failure keeps the template text."""
    import asyncio
    try:
        brief=[{'id':m['id'],'title':m['title'],'kind':m['kind'],'objectives':m.get('objectives',[])} for m in plan['modules']]
        out=await asyncio.wait_for(router.json(system='You are an engineering onboarding writer. Rewrite the summary and module outcomes to be concrete, motivating and accurate to the given titles/objectives. Do not invent facts. Return {"summary": str, "outcomes": {"<module id>": str}}.',user=json.dumps({'role':plan['meta'].get('role_title'),'modules':brief}),tier='instruct',fallback={'_fallback':True},agent='onboarding_polish',user_id=user_id,project_id=project_id),timeout=45)
    except Exception:return plan
    if '_fallback' in out:return plan
    if isinstance(out.get('summary'),str) and 20<len(out['summary'])<600:plan['summary']=out['summary']
    for m in plan['modules']:
        o=(out.get('outcomes') or {}).get(m['id'])
        if isinstance(o,str) and 10<len(o)<400:m['outcome']=o
    plan['meta']['polished']=True
    return plan

async def create_onboarding(user_id:str,project_id:str,target_role:str,level:str,weeks:int,hours_per_week:int,background:str='',is_public:bool=False,engine:str|None=None,role_id:str|None=None,quiz_questions:int=5,scope:list[str]|None=None)->dict:
    import hashlib
    from ..services.locks import workflow_lock
    config=[user_id,project_id,role_id or target_role.strip().lower(),level,weeks,hours_per_week,background,is_public,engine,quiz_questions,sorted(scope or [])]
    key=hashlib.sha256(json.dumps(config).encode()).hexdigest()
    async with workflow_lock(f'create-onboarding:{key}'):
        with db() as conn:
            existing=conn.execute('SELECT id FROM onboarding_paths WHERE configuration_key=?',(key,)).fetchone()
        if existing:
            path=get_path(existing['id'],user_id)
            if path['plan'].get('meta',{}).get('provenance') != 'fallback':return path
        result=await _create_onboarding(user_id,project_id,target_role,level,weeks,hours_per_week,background,is_public,engine,role_id,quiz_questions,scope)
        if result['plan'].get('meta',{}).get('provenance') != 'fallback':
            with db() as conn:conn.execute('UPDATE onboarding_paths SET configuration_key=? WHERE id=?',(key,result['id']))
        return result


async def _create_onboarding(user_id:str,project_id:str,target_role:str,level:str,weeks:int,hours_per_week:int,background:str='',is_public:bool=False,engine:str|None=None,role_id:str|None=None,quiz_questions:int=5,scope:list[str]|None=None)->dict:
    from ..graph.view import load_view
    from ..graph.curriculum import build_plan
    from ..graph import quiz as quizmod
    graph_ready=load_view(project_id) is not None
    engine=engine or ('graph' if graph_ready else 'llm')
    if engine=='graph' and not graph_ready:raise GraphNotReady('Build the knowledge graph first (POST /api/projects/{id}/graph/rebuild).')
    if engine=='graph':
        with db() as conn:
            mastery={r['topic']:r['score'] for r in conn.execute('SELECT topic,score FROM mastery WHERE user_id=? AND project_id=?',(user_id,project_id)).fetchall()}
        plan=build_plan(project_id,role_id or target_role,level,weeks,hours_per_week,background,scope,quiz_questions,mastery=mastery if not is_public else {})
        plan=await _polish(plan,user_id,project_id)
        plan['meta']['provenance']='graph'
        plan['meta']['polish']='applied' if plan['meta'].get('polished') else 'skipped'
        title=f"{plan['meta']['role_title']} · {weeks}-week onboarding"
    else:
        plan,_hits=await _llm_plan(user_id,project_id,target_role,level,weeks,hours_per_week,background)
        plan=_attach_quizzes(project_id,plan)
        plan.setdefault('meta',{}).setdefault('provenance','generated')
        if plan['meta'].get('requires_review'):is_public=False     # a placeholder is never shared automatically
        title=f'{target_role} · {weeks}-week onboarding'
    path_id=str(uuid.uuid4()); invite_code=secrets.token_urlsafe(6)
    with db() as conn:
        conn.execute('INSERT INTO onboarding_paths(id,project_id,creator_id,title,target_role,level,weeks,hours_per_week,is_public,invite_code,plan_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(path_id,project_id,user_id,title,target_role,level,weeks,hours_per_week,int(is_public),invite_code,json.dumps(plan)))
        conn.execute('INSERT OR IGNORE INTO onboarding_members(path_id,user_id) VALUES(?,?)',(path_id,user_id))
    if any(i.get('type')=='quiz' for m in plan.get('modules',[]) for i in m.get('items',[])):
        if graph_ready:
            await quizmod.generate_quizzes(path_id,use_llm=False)
        else:
            await quizmod.generate_quizzes_no_repo(path_id)
    from ..services.resources import approved_topics,sanitize_free_topics
    # approved_topics()'s catalog allowlist only makes sense for the graph engine, whose topics are
    # meant to correspond 1:1 to pre-vetted graph concepts. The LLM engine invents topics freely
    # (with or without a connected repo), so they were never guaranteed to be catalog members --
    # using the strict allowlist there silently dropped nearly every topic and meant the resource
    # scout / browser-use job almost never actually fired. Pattern-sanitize instead.
    raw_topics=plan.get('resource_search_topics') or []
    topics=approved_topics(raw_topics) if engine=='graph' else sanitize_free_topics(raw_topics)
    # Only the topics that survived sanitization get a time target -- keyed the same way the bridge
    # will look them up (exact topic string match). Computed here, not inside _llm_plan(), because the
    # graph engine (used whenever a project has an indexed repo -- i.e. most real paths) builds its
    # plan via build_plan() in graph/curriculum.py, a completely separate path whose items are never
    # type=='external_resource' and whose resource_search_topics comes from catalog.public_search_topics()
    # -- so anything computed only inside _llm_plan() silently never reached graph-engine paths at all
    # (this is why topic_target_minutes kept coming back {} for every graph-engine path tested).
    # Falls back to an even split of the learner's total time budget for any topic without a more
    # precise per-item minutes value (i.e. every graph-engine topic, and any LLM-engine gaps).
    all_target_minutes=plan.get('topic_target_minutes') or {}
    fallback_minutes=max(15,round((weeks*hours_per_week*60)/max(1,len(topics))))
    topic_target_minutes={t:all_target_minutes.get(t,fallback_minutes) for t in topics}
    # Balanced resource mix: one topic = one scouted resource (see run_topic_scout in mac_bridge.py --
    # deliberately kept that way to avoid overloading the 8B scout model's working memory), so the only
    # way to get a healthy video/article split across a whole course is to assign each TOPIC a type to
    # look for, not leave every topic's type up to whatever the scout happens to find. Round-robins
    # video/article across the final topic list (post-sanitization, so it applies identically to both
    # engines) in order, capped so a long course doesn't get pushed to all-video or all-article, and
    # leaves any topics beyond both caps unset (the scout's own judgment, as before) -- a 4-topic course
    # can't literally reach "4-5 videos AND 3-4 articles" (that needs 7-9 topics), so this approximates
    # the target ratio instead of forcing an unreachable exact count.
    topic_resource_type:dict[str,str]={}
    video_n=article_n=0
    for i,t in enumerate(topics):
        if i%2==0 and video_n<5:
            topic_resource_type[t]='video';video_n+=1
        elif article_n<4:
            topic_resource_type[t]='article';article_n+=1
        elif video_n<5:
            topic_resource_type[t]='video';video_n+=1
    job=create_job(user_id,'resource_scout',{'mode':'onboarding','path_id':path_id,'topics':topics,'topic_target_minutes':topic_target_minutes,'topic_resource_type':topic_resource_type,'instruction':'Find authoritative public resources for these SANITIZED generic concepts. Include YouTube, official docs, strong engineering blogs, books/catalog references, arXiv/research papers when appropriate. Return structured resources with topic mapping and estimated learning time. Never search private repository identifiers.'},project_id) if topics else None
    return get_path(path_id,user_id)|{'resource_job':job}

async def for_role(user_id:str,project_id:str,role:str|None,level:str='junior')->dict:
    from ..services.locks import workflow_lock
    async with workflow_lock(f'role-onboarding:{project_id}'):
        return await _for_role(user_id,project_id,role,level)


async def _for_role(user_id:str,project_id:str,role:str|None,level:str='junior')->dict:
    """Get-or-create the shared role path for this workspace's current graph, then enrol the user (new-hire entry point)."""
    from ..graph.view import load_view
    from ..graph.roles import resolve_role
    v=load_view(project_id)
    if v is None:
        # A new hire should never hit a dead end: if the workspace has indexed content, build the (sub-second to seconds) graph now.
        import asyncio
        from ..graph.builder import build_graph
        with db() as conn:docs=conn.execute('SELECT COUNT(*) FROM indexed_documents WHERE project_id=?',(project_id,)).fetchone()[0]
        if docs==0:raise GraphNotReady('This workspace has no indexed content yet. Ask your manager to connect a repository or documents.')
        await asyncio.to_thread(build_graph,project_id)
        v=load_view(project_id)
        if v is None:raise GraphNotReady('The knowledge graph could not be built for this workspace.')
    if not role:
        with db() as conn:r=conn.execute('SELECT role_title FROM users WHERE id=?',(user_id,)).fetchone()
        role=(r['role_title'] if r else None) or 'Software Engineer'
    profile,_=resolve_role(role)
    with db() as conn:
        row=conn.execute("SELECT id FROM onboarding_paths WHERE project_id=? AND level=? AND (plan_json::jsonb)->'meta'->>'role_profile_id'=? AND is_public=1 ORDER BY created_at ASC LIMIT 1",(project_id,level,profile['id'])).fetchone()
    if row:
        path_id=row['id']
        with db() as conn:conn.execute('INSERT INTO onboarding_members(path_id,user_id) VALUES(?,?) ON CONFLICT DO NOTHING',(path_id,user_id))
        return get_path(path_id,user_id)
    return await create_onboarding(user_id,project_id,profile['title'],level,4,8,'',True,'graph',profile['id'])

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
        from ..services.leaderboard import leaderboard
        org=conn.execute('SELECT org_id FROM projects WHERE id=?',(d['project_id'],)).fetchone()['org_id']
        scores={x['user_id']:x for x in leaderboard(org,d['project_id'],path_id)}
        for member in d['members']:
            score=scores.get(member['user_id'])
            if score:
                for key in ('xp','progress','streak','display_name'):member[key]=score[key]
        d['members'].sort(key=lambda x:(-x['xp'],x['user_id']))
        d['resources']=[]
        from ..services.jobs import get_job
        job=conn.execute("SELECT id FROM agent_jobs WHERE project_id=? AND kind='resource_scout' AND payload_json::jsonb->>'path_id'=? ORDER BY created_at DESC LIMIT 1",(d['project_id'],path_id)).fetchone()
        d['resource_job']=get_job(job['id']) if job else None
        for x in conn.execute('SELECT * FROM path_resources WHERE path_id=? ORDER BY module_id,created_at',(path_id,)).fetchall():
            z=dict(x);z['metadata']=json.loads(z.pop('metadata_json') or '{}');d['resources'].append(z)
        # Attach each resource to the module item it actually belongs to, so the UI can show a
        # section's video/article inline instead of only in the disconnected flat "curated
        # resources" list. resources.module_id is the SAME topic string dispatched to the scout
        # (see topics/topic_target_minutes in _create_onboarding) -- for the LLM engine that IS the
        # item's own "topic" field already, but the graph engine's items carry the concept's short
        # id (e.g. "git-workflow") while resources.module_id carries the catalog's long human-readable
        # search phrase (e.g. "git branching and pull request workflow tutorial") for that same
        # concept, so they never matched at all until this reverse lookup.
        if d['plan'].get('meta',{}).get('provenance')=='graph':
            from ..graph.catalog import concepts as _concepts
            topic_to_concept={c['search_topic']:cid for cid,c in _concepts().items() if c.get('search_topic')}
            for z in d['resources']:
                z['topic']=topic_to_concept.get(z.get('module_id'),z.get('module_id'))
        else:
            for z in d['resources']:
                z['topic']=z.get('module_id')
        d['progress_items']=[]
        if user_id:d['progress_items']=[dict(x) for x in conn.execute('SELECT * FROM path_progress WHERE path_id=? AND user_id=?',(path_id,user_id)).fetchall()]
    if user_id:
        from ..graph.quiz import path_quiz_state
        d.update(path_quiz_state(path_id,user_id,d['plan']))
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
            if len(url)>2000 or not re.match(r'^https?://[^\s<>"\']+$',url,re.I):continue      # only web links: no javascript:/file:/data: from an agent
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
    from ..graph.quiz import assert_progress_allowed
    assert_progress_allowed(path_id,user_id,item_id,status)   # raises QuizRequiredError / LockedError
    with db() as conn:
        p=conn.execute('SELECT plan_json FROM onboarding_paths WHERE id=?',(path_id,)).fetchone()
        if not p:raise KeyError(path_id)
        conn.execute('SELECT id FROM users WHERE id=? FOR UPDATE',(user_id,))
        plan=json.loads(p['plan_json']);valid=set(_progress_item_ids(plan));
        if valid and item_id not in valid:raise KeyError(item_id)
        old=conn.execute('SELECT status FROM path_progress WHERE path_id=? AND user_id=? AND item_id=?',(path_id,user_id,item_id)).fetchone()
        if old and old['status']=='completed':
            status,progress='completed',1.0
        conn.execute('''INSERT INTO path_progress(path_id,user_id,item_id,status,progress,score) VALUES(?,?,?,?,?,?) ON CONFLICT(path_id,user_id,item_id) DO UPDATE SET status=excluded.status,progress=excluded.progress,score=COALESCE(excluded.score,path_progress.score),updated_at=CURRENT_TIMESTAMP''',(path_id,user_id,item_id,status,progress,score))
        done=conn.execute("SELECT COUNT(*) FROM path_progress WHERE path_id=? AND user_id=? AND status='completed'",(path_id,user_id)).fetchone()[0]
        total=max(len(valid),1);overall=min(1,done/total)
        xp_gain=0
        if status=='completed' and (not old or old['status']!='completed'):
            base=next((int(it.get('xp') or 100) for m in plan.get('modules',[]) for it in m.get('items',[]) if it.get('id')==item_id),None)
            if base is None:base=next((int(e.get('xp') or 100) for e in plan.get('exercises',[]) if e.get('id')==item_id),100)
            xp_gain=base
        conn.execute('INSERT OR IGNORE INTO onboarding_members(path_id,user_id) VALUES(?,?)',(path_id,user_id));conn.execute('UPDATE onboarding_members SET progress=?,xp=xp+? WHERE path_id=? AND user_id=?',(overall,xp_gain,path_id,user_id))
        member=conn.execute('SELECT xp,progress,streak FROM onboarding_members WHERE path_id=? AND user_id=?',(path_id,user_id)).fetchone()
    return {'path_id':path_id,'item_id':item_id,'status':status,'progress':progress,'overall':overall,'xp_delta':xp_gain,'xp':member['xp'],'streak':member['streak']}
