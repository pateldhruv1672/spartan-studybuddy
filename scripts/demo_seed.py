#!/usr/bin/env python3
"""Seed a polished enterprise onboarding demo without requiring a running model."""
from __future__ import annotations
import json, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'backend'))
from app.config import settings
from app.db import init_db,db
from app.services.projects import create_project,list_projects
from app.services.indexer import index_text
from app.models import LearningEventIn
from app.services.event_store import record_event
from app.services.memory import update_mastery,add_memory

init_db(); uid=settings.demo_user_id; org=settings.demo_org_id
existing=list_projects(org)
project=next((p for p in existing if p['name']=='Fraud Intelligence Platform'),None) or create_project(org,'Fraud Intelligence Platform','Private streaming fraud detection stack used for the enterprise onboarding demo.',uid)
pid=project['id']
index_text(project_id=pid,source_type='github_code',source_name='services/inference.py',source_uri='demo://repo/services/inference.py',language='python',content='''from fastapi import APIRouter\nfrom models.fraud import FraudModel\nfrom features.pipeline import FeaturePipeline\n\nrouter = APIRouter()\n\nclass InferenceService:\n    def __init__(self, model: FraudModel, features: FeaturePipeline):\n        self.model = model\n        self.features = features\n\n    async def predict(self, transaction):\n        vector = await self.features.transform(transaction)\n        score = self.model.predict_proba(vector)\n        return {"fraud_score": score}\n''',metadata={'demo':True})
index_text(project_id=pid,source_type='github_code',source_name='pipelines/kafka_consumer.py',source_uri='demo://repo/pipelines/kafka_consumer.py',language='python',content='''class TransactionConsumer:\n    """Consumes transaction events with at-least-once delivery."""\n    def __init__(self, processor, idempotency_store):\n        self.processor = processor\n        self.idempotency_store = idempotency_store\n\n    async def handle(self, event):\n        if await self.idempotency_store.seen(event.id):\n            return\n        await self.processor.process(event)\n        await self.idempotency_store.mark_seen(event.id)\n''',metadata={'demo':True})
index_text(project_id=pid,source_type='documentation',source_name='docs/architecture.md',source_uri='demo://repo/docs/architecture.md',content='''# Fraud Intelligence Platform\nTransactions enter through Kafka, pass through an idempotent consumer, are transformed by the feature pipeline, scored by the FraudModel, and exposed through a FastAPI inference service. The platform uses PostgreSQL for durable state, Redis for low-latency feature caching, and Prometheus for service metrics. New ML engineers should understand classification metrics, feature leakage, Kafka consumer groups, idempotency, FastAPI, Docker, and production model monitoring before making changes.''',metadata={'demo':True})

# Team members and a seeded gamified onboarding path.
with db() as conn:
    for user_id,name,role,av in [('maya','Maya Chen','Senior ML Engineer','MC'),('jordan','Jordan Lee','Data Engineer','JL'),('sam','Sam Rivera','New ML Engineer','SR')]:
        conn.execute('INSERT OR IGNORE INTO users(id,org_id,display_name,email,role_title,avatar) VALUES(?,?,?,?,?,?)',(user_id,org,name,f'{user_id}@aperture.local',role,av))
        conn.execute('INSERT OR IGNORE INTO project_members(project_id,user_id,role) VALUES(?,?,?)',(pid,user_id,'learner'))
    path_id='demo-ml-onboarding'
    plan={
      'summary':'Learn the production concepts first, then trace a transaction through the private fraud platform and finish with a repo-grounded contribution exercise.',
      'prerequisites':[{'concept':'Classification metrics','priority':'essential','reason':'Interpret fraud model tradeoffs.'},{'concept':'Kafka consumer groups','priority':'essential','reason':'Understand event processing and retries.'},{'concept':'Idempotency','priority':'essential','reason':'Prevent duplicate side effects.'}],
      'modules':[
        {'id':'m1','title':'Foundations that matter here','outcome':'Explain the runtime concepts before reading private code','items':[{'id':'m1-i1','type':'video','title':'Precision, recall, and thresholds','minutes':22,'xp':80,'topic':'classification metrics','checkpoint_question':'When would recall matter more than precision?'},{'id':'m1-i2','type':'reading','title':'Kafka consumer groups + delivery semantics','minutes':30,'xp':100,'topic':'Kafka consumer groups','checkpoint_question':'Why must our handler tolerate retries?'}]},
        {'id':'m2','title':'Trace the production path','outcome':'Follow one transaction from Kafka to fraud score','items':[{'id':'m2-i1','type':'internal_walkthrough','title':'TransactionConsumer → FeaturePipeline','minutes':25,'xp':120,'repo_refs':['pipelines/kafka_consumer.py']},{'id':'m2-i2','type':'internal_walkthrough','title':'Feature vector → InferenceService','minutes':25,'xp':120,'repo_refs':['services/inference.py']},{'id':'m2-i3','type':'checkpoint','title':'Explain duplicate-event protection','minutes':10,'xp':150,'checkpoint_question':'What failure window still deserves scrutiny in mark_seen ordering?'}]},
        {'id':'m3','title':'Contribute safely','outcome':'Make a small tested improvement without breaking platform guarantees','items':[{'id':'m3-i1','type':'exercise','title':'Add observability around duplicate events','minutes':45,'xp':200,'repo_refs':['pipelines/kafka_consumer.py']}]}
      ],
      'exercises':[{'id':'e1','title':'Design a safer idempotency boundary','difficulty':'intermediate','description':'Propose and test a change that reduces the process/mark failure window.','repo_refs':['pipelines/kafka_consumer.py'],'acceptance':['Explain failure mode','Preserve public API','Add tests'],'xp':250}],
      'resource_search_topics':['Kafka consumer groups','idempotent event processing','precision recall classification thresholds']
    }
    conn.execute('''INSERT OR IGNORE INTO onboarding_paths(id,project_id,creator_id,title,target_role,level,weeks,hours_per_week,is_public,invite_code,plan_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(path_id,pid,uid,'ML Engineer · Fraud Platform','ML Engineer','junior',4,8,1,'SPARTAN-DEMO',json.dumps(plan)))
    for user,xp,prog in [(uid,540,.38),('sam',760,.52),('jordan',430,.29),('maya',980,.72)]:
        conn.execute('''INSERT INTO onboarding_members(path_id,user_id,xp,progress,streak) VALUES(?,?,?,?,?)
            ON CONFLICT(path_id,user_id) DO UPDATE SET xp=excluded.xp,progress=excluded.progress,streak=excluded.streak''',
            (path_id,user,xp,prog,3 if prog>.3 else 1))

for topic,score in [('Classification metrics',.72),('Kafka consumer groups',.48),('Idempotency',.55),('FastAPI',.78)]: update_mastery(uid,pid,topic,score)
add_memory(uid,pid,'onboarding','Current learning focus','Alex is onboarding to the fraud platform as an ML engineer. Kafka retry semantics and idempotency need reinforcement.',.7,{'demo':True})
for ev in [
  LearningEventIn(user_id=uid,project_id=pid,source='browser',type='video.progress',resource_id='https://youtube.com/watch?v=demo',context={'title':'Kafka Consumer Groups','progress':.58,'current_time':742,'duration':1280}),
  LearningEventIn(user_id=uid,project_id=pid,source='vscode',type='code.file_opened',resource_id='pipelines/kafka_consumer.py',context={'title':'kafka_consumer.py'}),
  LearningEventIn(user_id=uid,project_id=pid,source='webapp',type='checkpoint.completed',context={'title':'Classification metrics checkpoint','score':.82}),
]: record_event(ev)
print(json.dumps({'project_id':pid,'path_id':'demo-ml-onboarding'},indent=2))
