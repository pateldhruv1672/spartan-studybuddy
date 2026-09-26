from __future__ import annotations
import json,re,uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks,FastAPI,HTTPException,UploadFile,File,Form,Request,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles

from .config import ROOT,settings
from .db import init_db,db,database_health
from .models import *
from .services.model_router import router
from .services.projects import create_project,get_project,list_projects
from .services.sources import ingest_uri,list_sources
from .services.indexer import index_bytes,index_text,hybrid_search,list_documents,project_map
from .services.event_store import record_event,recent_events,admin_stats
from .services.memory import snapshot,update_mastery,memories
from .services.chats import threads,messages
from .services.jobs import create_job,next_jobs,claim_jobs,get_job,finish_job
from .services.team import accept_existing_invite,create_invite,invitations_for_user,list_invites,list_users,revoke_invite
from .services import auth,access
from .services.resource_sessions import upsert_session,resume_feed
from .services.telemetry import metrics_payload,recent_traces,ACTIVE_CONNECTIONS
from .services.observability import configure_otel
from .services.engineering_data import competition_results as load_competition_results, serving_profile_results
from .services.live_traffic import snapshot as traffic_snapshot
from .services.security import public_https_url,require_bridge
from .agents.assistant import ask
from .agents.onboarding import create_onboarding,get_path,list_paths,update_progress,join_path,add_resources
from .agents.research import start_research
from .graph.api import router as graph_router
from .graph.builder import build_graph
from .graph import quiz as graph_quiz

@asynccontextmanager
async def lifespan(_:FastAPI):
    init_db();yield

app=FastAPI(title=settings.app_name,version='2.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['*'] if settings.cors_origins=='*' else settings.cors_origins.split(','),allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
configure_otel(app)
app.include_router(graph_router)

def _rebuild_graph(project_id:str)->None:
    try:build_graph(project_id)
    except Exception as exc:print(f'graph rebuild skipped for {project_id}: {exc}')

class Hub:
    def __init__(self):self.clients:dict[str,set[WebSocket]]={}
    async def connect(self,user_id:str,ws:WebSocket):
        await ws.accept();self.clients.setdefault(user_id,set()).add(ws);ACTIVE_CONNECTIONS.inc()
    def disconnect(self,user_id:str,ws:WebSocket):
        before=len(self.clients.get(user_id,set()));self.clients.get(user_id,set()).discard(ws)
        if before:ACTIVE_CONNECTIONS.dec()
    async def send(self,user_id:str,payload:dict):
        dead=[]
        for ws in self.clients.get(user_id,set()):
            try:await ws.send_json(payload)
            except Exception:dead.append(ws)
        for ws in dead:self.disconnect(user_id,ws)
hub=Hub()

@app.get('/api/health',response_model=HealthResponse)
async def health():
    db_state=database_health()
    return HealthResponse(ok=bool(db_state.get('ok')),name=settings.app_name,database=db_state,model_endpoints=await router.endpoint_health())

@app.get('/metrics')
def metrics():
    body,ctype=metrics_payload();return Response(content=body,media_type=ctype)

# Browser-Use gets only an authenticated OpenAI-compatible model proxy, never raw vLLM admin endpoints.
@app.get('/agent-llm/v1/models')
async def bridge_models(request:Request):
    require_bridge(request)
    return {'object':'list','data':[{'id':settings.browser_model_name,'object':'model','owned_by':'spartan-studybuddy'}]}
@app.post('/agent-llm/v1/chat/completions')
async def bridge_chat(request:Request):
    require_bridge(request)
    payload=await request.json();payload['model']=settings.browser_model_name;target=settings.browser_model_url.rstrip('/')+'/chat/completions';headers={'Content-Type':'application/json'}
    # The browser-use Python client (ChatOpenAI) never sends chat_template_kwargs -- it only sends
    # OpenAI's own reasoning_effort, and only for models on OpenAI's own reasoning-model allowlist,
    # which ours isn't. With nothing set, this qwen3_5 chat template defaults to thinking ON, so every
    # single tool-call/action decision paid full reasoning overhead -- measured causing repeated
    # "LLM call timed out after 75 seconds" failures mid-run. Action selection is a narrow, structured
    # decision (browser-use already runs it under guided/schema-constrained decoding), not open-ended
    # dialogue, so it gets the same enable_thinking=False treatment as backend JSON extraction calls.
    payload.setdefault('chat_template_kwargs',{})['enable_thinking']=False
    if settings.browser_llm_provider!='ollama':headers['Authorization']=f'Bearer {settings.vllm_api_key}'
    async with httpx.AsyncClient(timeout=settings.request_timeout_s*2) as c:
        r=await c.post(target,json=payload,headers=headers)
    body=r.content
    if r.status_code==200:
        # Same decoding-degeneracy failure mode as the main tutor model, but this proxy has no
        # model_router.py in front of it to strip/dedupe it -- measured directly: a navigate action's
        # url field degenerated into ".../overview/overview/overview/..." (35+ repeats) after a failed
        # navigation, a mid-string repeat with no sentence punctuation, so the existing
        # _dedupe_repetition() sentence splitter in model_router.py wouldn't catch it even if this
        # path ran through it. Collapse any short span repeated 3+ times back to one copy.
        try:
            data=json.loads(body)
            for choice in data.get('choices') or []:
                content=(choice.get('message') or {}).get('content')
                if isinstance(content,str):
                    choice['message']['content']=re.sub(r'(.{3,120}?)\1{2,}',r'\1',content)
            body=json.dumps(data).encode()
        except Exception:
            pass
    return Response(content=body,status_code=r.status_code,media_type=r.headers.get('content-type','application/json'))

def _bearer(request:Request)->str:
    header=request.headers.get('authorization','')
    if not header.lower().startswith('bearer '):raise HTTPException(401,'Not signed in')
    return header[7:].strip()

@app.post('/api/auth/register')
def auth_register(req:RegisterRequest):
    try:return auth.register(email=req.email,password=req.password,display_name=req.display_name,role=req.role,org_id=req.org_id,role_title=req.role_title)
    except auth.AuthError as exc:raise HTTPException(400,str(exc))
@app.post('/api/auth/login')
def auth_login(req:LoginRequest):
    try:return auth.login(email=req.email,password=req.password)
    except auth.AuthError as exc:raise HTTPException(401,str(exc))
@app.post('/api/auth/accept-invite')
def auth_accept_invite(req:InviteSignupRequest):
    try:return auth.accept_invite_with_password(token=req.token,display_name=req.display_name,password=req.password,email=req.email)
    except auth.AuthError as exc:raise HTTPException(400,str(exc))
@app.get('/api/auth/me')
def auth_me(request:Request):
    try:return auth.current_user(_bearer(request))
    except auth.AuthError as exc:raise HTTPException(401,str(exc))

@app.patch('/api/auth/me')
def auth_update_me(req:ProfileUpdateRequest,request:Request):
    try:return auth.update_profile(auth.user_id_from_token(_bearer(request)),req.display_name,req.role_title)
    except auth.AuthError as exc:raise HTTPException(400,str(exc))

@app.patch('/api/team/{user_id}')
def team_update_member(user_id:str,req:ProfileUpdateRequest,request:Request):
    """Manager assigns a teammate's role profile (drives their onboarding path)."""
    access.check_manager_of_user(request,user_id)
    try:return auth.update_profile(user_id,req.display_name,req.role_title)
    except auth.AuthError as exc:raise HTTPException(400,str(exc))

@app.post('/api/projects')
def projects_create(req:ProjectCreateRequest,request:Request):
    uid,authed=access.identify(request,req.user_id)
    if authed:access.check_org_manager(request,req.org_id)
    return create_project(req.org_id,req.name,req.description,uid)
@app.get('/api/projects')
def projects_list(request:Request,org_id:str=settings.demo_org_id):
    """Managers see every workspace of their organisation; learners only the ones a manager assigned to them."""
    visible=access.accessible_projects(request,org_id)
    return list_projects(org_id) if visible is None else visible
@app.get('/api/projects/{project_id}')
def projects_get(project_id:str,request:Request):
    access.check_project(request,project_id)
    try:return get_project(project_id)
    except KeyError:raise HTTPException(404,'Project not found')
@app.get('/api/projects/{project_id}/map')
def projects_map(project_id:str,request:Request):
    access.check_project(request,project_id)
    return project_map(project_id)

@app.post('/api/team/invite')
async def invite(req:InviteRequest,request:Request):
    uid,authed=access.identify(request,req.invited_by)
    if authed:access.check_org_manager(request,req.org_id)
    if req.project_id:
        p=access.project_row(req.project_id)
        if not p or p['org_id']!=req.org_id:raise HTTPException(404,'Workspace not found')
    try:result=create_invite(req.org_id,uid,req.email,req.role_title,req.project_id)
    except ValueError as exc:raise HTTPException(400,str(exc))
    with db() as conn:recipient=conn.execute('SELECT id FROM users WHERE lower(email)=lower(?)',(result['email'],)).fetchone()
    if recipient:
        from fastapi.encoders import jsonable_encoder
        await hub.send(recipient['id'],jsonable_encoder({'kind':'invitation','invitation':result}))
    return result
@app.get('/api/team/invites')
def team_invites(request:Request,org_id:str=settings.demo_org_id):
    access.check_org_manager(request,org_id)
    return list_invites(org_id)
@app.delete('/api/team/invites/{token}')
def team_revoke_invite(token:str,request:Request,org_id:str=settings.demo_org_id):
    access.check_org_manager(request,org_id)
    if not revoke_invite(org_id,token):raise HTTPException(404,'Pending invitation not found')
    return {'ok':True}
@app.get('/api/invitations')
def my_invitations(request:Request):
    uid,_=access.identify(request)
    return invitations_for_user(uid)
@app.post('/api/invitations/{token}/accept')
def accept_existing(token:str,request:Request):
    uid,_=access.identify(request)
    try:return accept_existing_invite(uid,token)
    except KeyError:raise HTTPException(404,'Invitation not found, expired, or addressed to another account')
    except ValueError as exc:raise HTTPException(409,str(exc))
@app.post('/api/team/accept')
def accept(req:InviteAcceptRequest):
    raise HTTPException(410,'Use /api/auth/accept-invite to create a secured learner account')
@app.get('/api/team')
def team(request:Request,org_id:str=settings.demo_org_id):
    access.check_org_manager(request,org_id)
    return list_users(org_id)

@app.post('/api/projects/{project_id}/members')
def project_assign_member(project_id:str,req:AssignMemberRequest,request:Request):
    """Manager assigns a workspace to a person (and optionally sets their role profile)."""
    access.check_project(request,project_id,manager=True)
    access.assign_member(project_id,req.user_id)
    if req.role_title:
        try:auth.update_profile(req.user_id,None,req.role_title)
        except auth.AuthError as exc:raise HTTPException(400,str(exc))
    return get_project(project_id)['members']

@app.delete('/api/projects/{project_id}/members/{user_id}')
def project_remove_member(project_id:str,user_id:str,request:Request):
    access.check_project(request,project_id,manager=True)
    with db() as conn:conn.execute('DELETE FROM project_members WHERE project_id=? AND user_id=?',(project_id,user_id))
    return get_project(project_id)['members']

@app.post('/api/sources/ingest')
def source_ingest(req:SourceIngestRequest,background:BackgroundTasks,request:Request):
    access.check_project(request,req.project_id,req.user_id,manager=True)
    try:result=ingest_uri(req.project_id,req.uri,req.kind,req.branch,req.access_token)
    except Exception as exc:raise HTTPException(400,f'Ingestion failed: {exc}')
    background.add_task(_rebuild_graph,req.project_id)   # keep the knowledge graph in step with the index
    return result
@app.get('/api/projects/{project_id}/sources')
def sources(project_id:str,request:Request):
    access.check_project(request,project_id)
    return list_sources(project_id)
@app.post('/api/sources/upload')
async def upload_source(background:BackgroundTasks,request:Request,project_id:str=Form(...),file:UploadFile=File(...)):
    access.check_project(request,project_id,manager=True)
    if not access.project_row(project_id):raise HTTPException(404,'Workspace not found')     # validate the workspace BEFORE touching the filesystem
    cap=settings.max_upload_mb*1024*1024;chunks=[];size=0
    while chunk:=await file.read(1024*1024):
        size+=len(chunk)
        if size>cap:raise HTTPException(413,'File too large')
        chunks.append(chunk)
    data=b''.join(chunks)
    dest=(settings.uploads_dir/project_id).resolve()
    if not dest.is_relative_to(settings.uploads_dir.resolve()):raise HTTPException(400,'Invalid workspace')
    dest.mkdir(parents=True,exist_ok=True)
    safe=re.sub(r'[^A-Za-z0-9._-]+','_',Path(file.filename or '').name)[:120].lstrip('.') or 'upload'
    path=dest/f'{uuid.uuid4().hex[:8]}-{safe}'                                              # server-chosen name: the client filename is only a label
    if not path.resolve().is_relative_to(dest):raise HTTPException(400,'Invalid file name')
    path.write_bytes(data)
    try:result=index_bytes(project_id=project_id,source_type='upload',source_name=path.name,data=data,source_uri=path.as_uri(),mime_type=file.content_type,metadata={'uploaded':True})
    except Exception as exc:raise HTTPException(400,f'Indexing failed: {exc}')
    background.add_task(_rebuild_graph,project_id)
    return result
@app.post('/api/index/text')
def index_text_endpoint(req:TextIndexRequest,request:Request):
    access.check_project(request,req.project_id)
    doc_id=req.metadata.get('document_id')
    if doc_id:      # a document id can never move between workspaces
        with db() as conn:owner=conn.execute('SELECT project_id FROM indexed_documents WHERE id=?',(doc_id,)).fetchone()
        if owner and owner['project_id']!=req.project_id:raise HTTPException(409,'document_id belongs to another workspace')
    return index_text(project_id=req.project_id,source_type=req.source_type,source_name=req.source_name,content=req.content,source_uri=req.source_uri,mime_type=req.mime_type,language=req.language,metadata=req.metadata,document_id=req.metadata.get('document_id'))
@app.get('/api/projects/{project_id}/documents')
def docs(project_id:str,request:Request):
    access.check_project(request,project_id)
    return list_documents(project_id)
@app.post('/api/search')
def search(req:SearchRequest,request:Request):
    access.check_project(request,req.project_id)
    return {'results':hybrid_search(req.project_id,req.query,req.top_k)}

@app.post('/api/ask')
async def ask_endpoint(req:AskRequest,request:Request):
    access.check_project(request,req.project_id,req.user_id)
    if req.thread_id:
        access.check_thread(request,req.thread_id)
        with db() as conn:
            if conn.execute('SELECT project_id FROM chat_threads WHERE id=?',(req.thread_id,)).fetchone()['project_id'] != req.project_id:raise HTTPException(404,'Conversation unavailable')
    return await ask(user_id=req.user_id,project_id=req.project_id,question=req.question,thread_id=req.thread_id,mode=req.mode,current_code=req.current_code,file_path=req.file_path,hint_level=req.hint_level,allow_final_answer=req.allow_final_answer)
@app.post('/api/tutor')
async def tutor_compat(req:AskRequest,request:Request):
    access.check_project(request,req.project_id,req.user_id)
    if req.thread_id:
        access.check_thread(request,req.thread_id)
        with db() as conn:
            if conn.execute('SELECT project_id FROM chat_threads WHERE id=?',(req.thread_id,)).fetchone()['project_id'] != req.project_id:raise HTTPException(404,'Conversation unavailable')
    return await ask(user_id=req.user_id,project_id=req.project_id,question=req.question,thread_id=req.thread_id,mode='socratic',current_code=req.current_code,file_path=req.file_path,hint_level=req.hint_level,allow_final_answer=req.allow_final_answer)
@app.get('/api/chats/{user_id}')
def chat_threads(user_id:str,request:Request,project_id:str|None=None):
    access.identify(request,user_id)
    if project_id:access.check_project(request,project_id,user_id)
    return threads(user_id,project_id)
@app.get('/api/chats/thread/{thread_id}')
def chat_messages(thread_id:str,request:Request):
    access.check_thread(request,thread_id)
    return messages(thread_id)

@app.post('/api/onboarding')
async def onboarding(req:OnboardingRequest,request:Request):
    from .agents.onboarding import GraphNotReady
    access.check_project(request,req.project_id,req.user_id,manager=True)
    try:result=await create_onboarding(req.user_id,req.project_id,req.target_role,req.level,req.weeks,req.hours_per_week,req.background,req.is_public,req.engine,req.role_id,req.quiz_questions,req.scope)
    except GraphNotReady as exc:raise HTTPException(409,str(exc))
    await hub.send(req.user_id,{'kind':'onboarding_created','path':result});return result
@app.get('/api/onboarding/{project_id}')
def onboarding_list(project_id:str,request:Request,user_id:str=settings.demo_user_id):
    user_id=access.check_project(request,project_id,user_id)
    return list_paths(project_id,user_id)
@app.get('/api/onboarding/path/{path_id}')
def onboarding_get(path_id:str,request:Request,user_id:str=settings.demo_user_id):
    user_id=access.check_path(request,path_id,user_id)
    try:return get_path(path_id,user_id)
    except KeyError:raise HTTPException(404,'Path not found')
@app.post('/api/onboarding/path/{path_id}/join')
def onboarding_join(path_id:str,req:JoinPathRequest,request:Request):
    access.check_path(request,path_id,req.user_id)
    try:return join_path(path_id,req.user_id,req.invite_code)
    except PermissionError:raise HTTPException(403,'Invite code required')
    except KeyError:raise HTTPException(404,'Path not found')
@app.post('/api/onboarding/path/{path_id}/progress')
async def onboarding_progress(path_id:str,req:ProgressRequest,request:Request):
    access.check_path(request,path_id,req.user_id)
    try:result=update_progress(path_id,req.user_id,req.item_id,req.status,req.progress,req.score)
    except graph_quiz.LockedError as exc:raise HTTPException(423,str(exc))
    except graph_quiz.QuizRequiredError as exc:raise HTTPException(409,str(exc))
    except KeyError:raise HTTPException(404,'Path or item not found')
    await hub.send(req.user_id,{'kind':'progress','progress':result});return result

@app.post('/api/resource/session')
async def resource_session(req:ResourceSessionIn,request:Request):
    access.check_user_project(request,req.user_id,req.project_id)
    result=await upsert_session(req.user_id,req.project_id,req.url,req.title,req.resource_type,req.seconds_active,req.progress,req.last_position,req.duration,req.visible_text,req.concepts);await hub.send(req.user_id,{'kind':'resource_session','session':result});return result
@app.get('/api/resource/resume/{user_id}')
def resource_resume(user_id:str,request:Request,project_id:str|None=None):
    access.check_user_project(request,user_id,project_id)
    return resume_feed(user_id,project_id)

@app.post('/api/events')
async def event(req:LearningEventIn,request:Request):
    access.check_user_project(request,req.user_id,req.project_id)
    r=record_event(req);await hub.send(req.user_id,{'kind':'learning_event','event':req.model_dump()});return r
@app.get('/api/events/{user_id}')
def events(user_id:str,request:Request,project_id:str|None=None,limit:int=50):
    access.check_user_project(request,user_id,project_id)
    return recent_events(user_id,project_id,min(limit,200))
@app.get('/api/learner/{user_id}/{project_id}')
def learner(user_id:str,project_id:str,request:Request):
    access.check_user_project(request,user_id,project_id)
    return snapshot(user_id,project_id)
@app.post('/api/mastery/{user_id}/{project_id}/{topic}')
def mastery(user_id:str,project_id:str,topic:str,score:float,request:Request):
    access.check_user_project(request,user_id,project_id)
    return update_mastery(user_id,project_id,topic,score)

@app.post('/api/research')
def research(req:ResearchRequest,request:Request):
    access.check_project(request,req.project_id,req.user_id)
    try:return start_research(req.user_id,req.project_id,req.query)
    except ValueError as exc:raise HTTPException(400,str(exc))
@app.post('/api/agent/jobs')
def agent_create(req:AgentJobRequest,request:Request):
    access.check_user_project(request,req.user_id,req.project_id)
    if req.kind!='open_resource':raise HTTPException(403,'This job type can only be created by a server workflow')
    payload={**req.payload}
    try:payload['url']=public_https_url(str(payload.get('url','')))
    except ValueError as exc:raise HTTPException(400,str(exc))
    return create_job(req.user_id,req.kind,payload,req.project_id)
@app.get('/api/agent/jobs')
def agent_next(request:Request,limit:int=10):
    require_bridge(request);return next_jobs(min(max(limit,1),50))
@app.post('/api/agent/jobs/claim')
def agent_claim(request:Request,limit:int=5):
    require_bridge(request);return claim_jobs(min(max(limit,1),20))
@app.get('/api/agent/jobs/{job_id}')
def agent_get(job_id:str,request:Request):
    try:job=get_job(job_id)
    except KeyError:raise HTTPException(404,'Job not found')
    access.check_self(request,job['user_id'])
    return job
@app.post('/api/agent/jobs/{job_id}/complete')
async def agent_complete(job_id:str,result:dict[str,Any],request:Request):
    require_bridge(request)
    try:job=get_job(job_id)
    except KeyError:raise HTTPException(404,'Job not found')
    if job['kind'] in {'resource_scout','web_research'}:
        from .services.resources import validate_resources
        # job['payload']['topics'] was already sanitized once at job-creation time (approved_topics()
        # for the graph engine's catalog concepts, sanitize_free_topics() for free-form LLM topics --
        # see onboarding.py), so it's already the trusted, correct allowlist for whichever engine
        # created this job. Re-deriving it here via approved_topics() applied its strict catalog
        # filter a second time to topics that were never meant to be catalog members in the first
        # place, so it returned an empty allowlist for any free-form topic and rejected every
        # resource regardless of quality -- e.g. "Infrastructure as Code with Terraform and AWS
        # deployment" is a real curriculum topic, not a graph concept, and was never going to be in
        # that catalog.
        resources,rejected=validate_resources(result.get('resources'),job['payload'].get('topics',[]))
        synthesis=str(result.get('synthesis') or '')[:6000]
        result={'ok':bool(resources),'resources':resources,'rejected_count':rejected,'synthesis':synthesis if resources else ''}
        if not resources:result['error']='No valid topic-matched resources were returned'
        if job['kind']=='resource_scout' and job['payload'].get('path_id'):
            add_resources(job['payload']['path_id'],resources)
    if job['kind']=='web_research' and result.get('synthesis'):
        from .services.memory import add_memory
        add_memory(job['user_id'],job.get('project_id'),'research',job['payload'].get('query','Research'),str(result['synthesis'])[:6000],.6,{'sources':result.get('resources',[])[:12]})
    from fastapi.encoders import jsonable_encoder
    done=finish_job(job_id,result,status='failed' if result.get('ok') is False else 'completed')
    await hub.send(job['user_id'],jsonable_encoder({'kind':'agent_job','job':done}));return done

@app.get('/api/admin/stats')
def stats(request:Request,org_id:str=settings.demo_org_id):
    access.check_org_manager(request,org_id)
    return admin_stats(org_id)
@app.get('/api/admin/traces')
def traces(request:Request,limit:int=100):
    uid=access.check_any_manager(request);user=access.user_row(uid)
    if not user:raise HTTPException(401,'Not signed in')
    return recent_traces(min(max(limit,1),500),user['org_id'])
@app.get('/api/admin/competition')
def competition_results():
    return load_competition_results(ROOT/'experiments'/'results')
@app.get('/api/admin/traffic')
def traffic(request: Request, limit: int = 200):
    uid = access.check_any_manager(request)
    user = access.user_row(uid)
    if not user:
        raise HTTPException(401, 'Not signed in')
    return traffic_snapshot(user['org_id'], limit)
@app.get('/api/admin/serving-profile')
def serving_profile():
    return serving_profile_results(ROOT/'experiments'/'results')

@app.websocket('/ws/{user_id}')
async def websocket(user_id:str,ws:WebSocket):
    token=ws.query_params.get('token','')
    try:uid=auth.user_id_from_token(token)
    except auth.AuthError:
        await ws.close(code=4401);return
    if uid!=user_id:
        await ws.close(code=4403);return
    await hub.connect(user_id,ws)
    try:
        while True:await ws.receive_text()
    except WebSocketDisconnect:hub.disconnect(user_id,ws)

WEB=ROOT/'apps'/'web'/'dist'
if (WEB/'assets').exists():
    app.mount('/assets',StaticFiles(directory=WEB/'assets'),name='assets')
@app.get('/')
def root():return FileResponse(WEB/'index.html')
@app.get('/{path:path}')
def spa(path:str):
    if path.startswith('api/') or path.startswith('metrics') or path.startswith('agent-llm/') or path.startswith('ws/'):raise HTTPException(404)
    candidate=WEB/path
    if path and candidate.is_file():return FileResponse(candidate)
    return FileResponse(WEB/'index.html')
