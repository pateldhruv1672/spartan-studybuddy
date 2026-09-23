from __future__ import annotations
import json,uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Request,WebSocket,WebSocketDisconnect
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
from .services.team import create_invite,accept_invite,list_users
from .services.resource_sessions import upsert_session,resume_feed
from .services.telemetry import metrics_payload,recent_traces,ACTIVE_CONNECTIONS
from .services.observability import configure_otel
from .agents.assistant import ask
from .agents.onboarding import create_onboarding,get_path,list_paths,update_progress,join_path,add_resources
from .agents.research import start_research

@asynccontextmanager
async def lifespan(_:FastAPI):
    init_db();yield

app=FastAPI(title=settings.app_name,version='2.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['*'] if settings.cors_origins=='*' else settings.cors_origins.split(','),allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
configure_otel(app)

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
    if request.headers.get('authorization')!=f'Bearer {settings.bridge_token}':raise HTTPException(401,'Invalid bridge token')
    return {'object':'list','data':[{'id':settings.browser_model_name,'object':'model','owned_by':'spartan-studybuddy'}]}
@app.post('/agent-llm/v1/chat/completions')
async def bridge_chat(request:Request):
    if request.headers.get('authorization')!=f'Bearer {settings.bridge_token}':raise HTTPException(401,'Invalid bridge token')
    payload=await request.json();payload['model']=settings.browser_model_name;target=settings.browser_model_url.rstrip('/')+'/chat/completions';headers={'Content-Type':'application/json'}
    if settings.browser_llm_provider!='ollama':headers['Authorization']=f'Bearer {settings.vllm_api_key}'
    async with httpx.AsyncClient(timeout=settings.request_timeout_s*2) as c:
        r=await c.post(target,json=payload,headers=headers);return Response(content=r.content,status_code=r.status_code,media_type=r.headers.get('content-type','application/json'))

@app.post('/api/projects')
def projects_create(req:ProjectCreateRequest):return create_project(req.org_id,req.name,req.description,req.user_id)
@app.get('/api/projects')
def projects_list(org_id:str=settings.demo_org_id):return list_projects(org_id)
@app.get('/api/projects/{project_id}')
def projects_get(project_id:str):
    try:return get_project(project_id)
    except KeyError:raise HTTPException(404,'Project not found')
@app.get('/api/projects/{project_id}/map')
def projects_map(project_id:str):return project_map(project_id)

@app.post('/api/team/invite')
def invite(req:InviteRequest):return create_invite(req.org_id,req.invited_by,req.email,req.role_title)
@app.post('/api/team/accept')
def accept(req:InviteAcceptRequest):
    try:return accept_invite(req.token,req.display_name,req.email,req.role_title)
    except KeyError:raise HTTPException(404,'Invite not found or already used')
@app.get('/api/team')
def team(org_id:str=settings.demo_org_id):return list_users(org_id)

@app.post('/api/sources/ingest')
def source_ingest(req:SourceIngestRequest):
    try:return ingest_uri(req.project_id,req.uri,req.kind,req.branch,req.access_token)
    except Exception as exc:raise HTTPException(400,f'Ingestion failed: {exc}')
@app.get('/api/projects/{project_id}/sources')
def sources(project_id:str):return list_sources(project_id)
@app.post('/api/sources/upload')
async def upload_source(project_id:str=Form(...),file:UploadFile=File(...)):
    data=await file.read()
    if len(data)>settings.max_upload_mb*1024*1024:raise HTTPException(413,'File too large')
    dest=settings.uploads_dir/project_id;dest.mkdir(parents=True,exist_ok=True);path=dest/(file.filename or f'upload-{uuid.uuid4()}');path.write_bytes(data)
    try:return index_bytes(project_id=project_id,source_type='upload',source_name=path.name,data=data,source_uri=path.as_uri(),mime_type=file.content_type,metadata={'uploaded':True})
    except Exception as exc:raise HTTPException(400,f'Indexing failed: {exc}')
@app.post('/api/index/text')
def index_text_endpoint(req:TextIndexRequest):return index_text(project_id=req.project_id,source_type=req.source_type,source_name=req.source_name,content=req.content,source_uri=req.source_uri,mime_type=req.mime_type,language=req.language,metadata=req.metadata,document_id=req.metadata.get('document_id'))
@app.get('/api/projects/{project_id}/documents')
def docs(project_id:str):return list_documents(project_id)
@app.post('/api/search')
def search(req:SearchRequest):return {'results':hybrid_search(req.project_id,req.query,req.top_k)}

@app.post('/api/ask')
async def ask_endpoint(req:AskRequest):
    return await ask(user_id=req.user_id,project_id=req.project_id,question=req.question,thread_id=req.thread_id,mode=req.mode,current_code=req.current_code,file_path=req.file_path,hint_level=req.hint_level,allow_final_answer=req.allow_final_answer)
@app.post('/api/tutor')
async def tutor_compat(req:AskRequest):
    return await ask(user_id=req.user_id,project_id=req.project_id,question=req.question,thread_id=req.thread_id,mode='socratic',current_code=req.current_code,file_path=req.file_path,hint_level=req.hint_level,allow_final_answer=req.allow_final_answer)
@app.get('/api/chats/{user_id}')
def chat_threads(user_id:str,project_id:str|None=None):return threads(user_id,project_id)
@app.get('/api/chats/thread/{thread_id}')
def chat_messages(thread_id:str):return messages(thread_id)

@app.post('/api/onboarding')
async def onboarding(req:OnboardingRequest):
    result=await create_onboarding(req.user_id,req.project_id,req.target_role,req.level,req.weeks,req.hours_per_week,req.background,req.is_public);await hub.send(req.user_id,{'kind':'onboarding_created','path':result});return result
@app.get('/api/onboarding/{project_id}')
def onboarding_list(project_id:str,user_id:str=settings.demo_user_id):return list_paths(project_id,user_id)
@app.get('/api/onboarding/path/{path_id}')
def onboarding_get(path_id:str,user_id:str=settings.demo_user_id):
    try:return get_path(path_id,user_id)
    except KeyError:raise HTTPException(404,'Path not found')
@app.post('/api/onboarding/path/{path_id}/join')
def onboarding_join(path_id:str,req:JoinPathRequest):
    try:return join_path(path_id,req.user_id,req.invite_code)
    except PermissionError:raise HTTPException(403,'Invite code required')
    except KeyError:raise HTTPException(404,'Path not found')
@app.post('/api/onboarding/path/{path_id}/progress')
async def onboarding_progress(path_id:str,req:ProgressRequest):
    result=update_progress(path_id,req.user_id,req.item_id,req.status,req.progress,req.score);await hub.send(req.user_id,{'kind':'progress','progress':result});return result

@app.post('/api/resource/session')
async def resource_session(req:ResourceSessionIn):
    result=await upsert_session(req.user_id,req.project_id,req.url,req.title,req.resource_type,req.seconds_active,req.progress,req.last_position,req.duration,req.visible_text,req.concepts);await hub.send(req.user_id,{'kind':'resource_session','session':result});return result
@app.get('/api/resource/resume/{user_id}')
def resource_resume(user_id:str,project_id:str|None=None):return resume_feed(user_id,project_id)

@app.post('/api/events')
async def event(req:LearningEventIn):
    r=record_event(req);await hub.send(req.user_id,{'kind':'learning_event','event':req.model_dump()});return r
@app.get('/api/events/{user_id}')
def events(user_id:str,project_id:str|None=None,limit:int=50):return recent_events(user_id,project_id,min(limit,200))
@app.get('/api/learner/{user_id}/{project_id}')
def learner(user_id:str,project_id:str):return snapshot(user_id,project_id)
@app.post('/api/mastery/{user_id}/{project_id}/{topic}')
def mastery(user_id:str,project_id:str,topic:str,score:float):return update_mastery(user_id,project_id,topic,score)

@app.post('/api/research')
def research(req:ResearchRequest):return start_research(req.user_id,req.project_id,req.query)
@app.post('/api/agent/jobs')
def agent_create(req:AgentJobRequest):return create_job(req.user_id,req.kind,req.payload,req.project_id)
@app.get('/api/agent/jobs')
def agent_next(limit:int=10):return next_jobs(min(max(limit,1),50))
@app.post('/api/agent/jobs/claim')
def agent_claim(limit:int=5):return claim_jobs(min(max(limit,1),20))
@app.get('/api/agent/jobs/{job_id}')
def agent_get(job_id:str):
    try:return get_job(job_id)
    except KeyError:raise HTTPException(404,'Job not found')
@app.post('/api/agent/jobs/{job_id}/complete')
async def agent_complete(job_id:str,result:dict[str,Any]):
    try:job=get_job(job_id)
    except KeyError:raise HTTPException(404,'Job not found')
    if job['kind']=='resource_scout' and result.get('resources') and job['payload'].get('path_id'):
        add_resources(job['payload']['path_id'],result['resources'])
    if job['kind']=='web_research' and result.get('synthesis'):
        from .services.memory import add_memory
        add_memory(job['user_id'],job.get('project_id'),'research',job['payload'].get('query','Research'),str(result['synthesis'])[:6000],.6,{'sources':result.get('resources',[])[:12]})
    done=finish_job(job_id,result);await hub.send(job['user_id'],{'kind':'agent_job','job':done});return done

@app.get('/api/admin/stats')
def stats(org_id:str=settings.demo_org_id):return admin_stats(org_id)
@app.get('/api/admin/traces')
def traces(limit:int=100):return recent_traces(min(max(limit,1),500))
@app.get('/api/admin/competition')
def competition_results():
    path=ROOT/'experiments'/'results'/'comparison.json';return json.loads(path.read_text()) if path.exists() else {'available':False,'message':'Run make competition on the DGX Spark.'}

@app.websocket('/ws/{user_id}')
async def websocket(user_id:str,ws:WebSocket):
    await hub.connect(user_id,ws)
    try:
        while True:await ws.receive_text()
    except WebSocketDisconnect:hub.disconnect(user_id,ws)

WEB=ROOT/'apps'/'web'
app.mount('/assets',StaticFiles(directory=WEB),name='assets')
@app.get('/')
def root():return FileResponse(WEB/'index.html')
@app.get('/{path:path}')
def spa(path:str):
    if path.startswith('api/') or path.startswith('metrics') or path.startswith('agent-llm/'):raise HTTPException(404)
    return FileResponse(WEB/'index.html')
