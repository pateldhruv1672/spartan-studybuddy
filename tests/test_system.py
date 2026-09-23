from __future__ import annotations
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services.model_router import router

client=TestClient(app)

def test_health_and_metrics():
    with client:
        r=client.get('/api/health'); assert r.status_code==200; assert 'Spartan StudyBuddy' in r.json()['name']
        m=client.get('/metrics'); assert m.status_code==200; assert 'studybuddy_model_requests_total' in m.text

def test_project_index_hybrid_search():
    with client:
        p=client.post('/api/projects',json={'name':'Payments Test','description':'test','user_id':'demo-spartan','org_id':'demo-company'}).json(); pid=p['id']
        r=client.post('/api/index/text',json={'project_id':pid,'source_type':'vscode_code','source_name':'payment_service.py','content':'class PaymentService:\n    def commit(self, ledger):\n        return ledger.commit()\n','language':'python','metadata':{'document_id':f'test:{pid}:payment'}})
        assert r.status_code==200 and r.json()['chunks']>=1
        s=client.post('/api/search',json={'project_id':pid,'query':'PaymentService ledger commit','top_k':5}); assert s.status_code==200 and s.json()['results']
        mp=client.get(f'/api/projects/{pid}/map').json(); assert mp['documents']>=1; assert any(x['name']=='PaymentService' for x in mp['symbols'])

def test_direct_and_socratic_routes(monkeypatch):
    async def fake_generate(**kw):
        text='Direct grounded explanation [1].' if '[MODE:DIRECT]' in kw['system'] else 'Before changing it, what invariant should hold? [1]'
        return SimpleNamespace(text=text,latency_ms=120.0,ttft_ms=40.0,output_tokens=12,tokens_per_second=55.0)
    monkeypatch.setattr(router,'generate',fake_generate)
    with client:
        p=client.post('/api/projects',json={'name':'Tutor Test','user_id':'demo-spartan'}).json(); pid=p['id']
        client.post('/api/index/text',json={'project_id':pid,'source_type':'documentation','source_name':'README.md','content':'The worker uses idempotency keys to handle retries.','metadata':{}})
        a=client.post('/api/ask',json={'user_id':'demo-spartan','project_id':pid,'question':'What does the worker use for retries?','mode':'qa'}).json(); assert a['mode']=='qa' and 'Direct' in a['answer']
        b=client.post('/api/ask',json={'user_id':'demo-spartan','project_id':pid,'question':'Fix my retry code','mode':'socratic'}).json(); assert b['mode']=='socratic' and '?' in b['answer']

def test_gamified_path_progress():
    from app.db import db
    import json, uuid
    with client:
        p=client.post('/api/projects',json={'name':'Path Test','user_id':'demo-spartan'}).json(); pid=p['id']; path_id=str(uuid.uuid4())
        plan={'summary':'x','modules':[{'id':'m','title':'M','items':[{'id':'lesson-1','title':'L','xp':100}]}],'exercises':[]}
        with db() as conn:
            conn.execute('INSERT INTO onboarding_paths(id,project_id,creator_id,title,target_role,level,weeks,hours_per_week,is_public,invite_code,plan_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(path_id,pid,'demo-spartan','Path','Engineer','junior',2,5,1,'CODE',json.dumps(plan)))
            conn.execute('INSERT INTO onboarding_members(path_id,user_id) VALUES(?,?)',(path_id,'demo-spartan'))
        r=client.post(f'/api/onboarding/path/{path_id}/progress',json={'user_id':'demo-spartan','item_id':'lesson-1','status':'completed','progress':1,'score':1}); assert r.status_code==200; assert r.json()['xp_delta']==150

def test_resource_session_resume(monkeypatch):
    async def fake_json(**kw): return {'summary':'You learned consumer-group partition ownership and retries.','concepts':['consumer groups','retries'],'questions':['What does a rebalance change?','Why are retries possible?']}
    monkeypatch.setattr(router,'json',fake_json)
    with client:
        r=client.post('/api/resource/session',json={'user_id':'demo-spartan','project_id':None,'url':'https://youtube.com/watch?v=test','title':'Kafka tutorial','resource_type':'youtube','seconds_active':120,'progress':.4,'last_position':300,'duration':750,'visible_text':'Consumer groups divide partitions across consumers. Retries can redeliver messages.','concepts':['Kafka']})
        assert r.status_code==200 and 'consumer' in r.json()['summary'].lower() and len(r.json()['questions'])==2

def test_bridge_auth():
    with client:
        assert client.get('/agent-llm/v1/models').status_code==401
        r=client.get('/agent-llm/v1/models',headers={'Authorization':f'Bearer {settings.bridge_token}'}); assert r.status_code==200 and r.json()['data'][0]['id']==settings.browser_model_name
