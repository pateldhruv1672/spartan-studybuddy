"""Manager path actions that preserve existing progress and quiz history."""
import json
from ..db import db
from .resources import approved_topics
from .jobs import create_job, get_job


def assign(path_id: str, user_id: str):
    with db() as conn:
        path=conn.execute('SELECT p.project_id,w.org_id FROM onboarding_paths p JOIN projects w ON w.id=p.project_id WHERE p.id=?',(path_id,)).fetchone()
        user=conn.execute('SELECT org_id FROM users WHERE id=?',(user_id,)).fetchone()
        if not path or not user or path['org_id']!=user['org_id']:raise ValueError('Learner must belong to this organization.')
        conn.execute("INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,'learner') ON CONFLICT DO NOTHING",(path['project_id'],user_id))
        conn.execute('INSERT INTO onboarding_members(path_id,user_id) VALUES(?,?) ON CONFLICT DO NOTHING',(path_id,user_id))
    return {'assigned':True}


def scout(path_id: str, user_id: str):
    with db() as conn:
        path=conn.execute('SELECT project_id,plan_json FROM onboarding_paths WHERE id=? FOR UPDATE',(path_id,)).fetchone()
        if not path:raise ValueError('Path unavailable')
        prior=conn.execute("""SELECT id FROM agent_jobs WHERE kind='resource_scout' AND status IN ('queued','running')
                              AND project_id=? AND payload_json::jsonb->>'path_id'=? ORDER BY created_at DESC LIMIT 1""",(path['project_id'],path_id)).fetchone()
        if prior:return get_job(prior['id'])
        topics=approved_topics(json.loads(path['plan_json']).get('resource_search_topics',[]))
        if not topics:raise ValueError('No approved public topics are available for this path.')
        return create_job(user_id,'resource_scout',{'path_id':path_id,'topics':topics},path['project_id'])
