from __future__ import annotations
import json,uuid
from ..db import db

def create_project(org_id:str,name:str,description:str='',user_id:str='demo-spartan')->dict:
    pid=str(uuid.uuid4())
    with db() as conn:
        conn.execute('INSERT INTO projects(id,org_id,name,description) VALUES(?,?,?,?)',(pid,org_id,name,description));conn.execute('INSERT OR IGNORE INTO project_members(project_id,user_id,role) VALUES(?,?,?)',(pid,user_id,'manager'))
    return get_project(pid)

DEMO_PROJECT_NAME='Demo Workspace'

def get_or_create_demo_project(org_id:str,creator_id:str)->str:
    """Stable, idempotent demo workspace lookup by name — no hardcoded id. Repeated calls (server restarts,
    concurrent signups) never create a duplicate: name+org is looked up first, only missing triggers create."""
    with db() as conn:
        row=conn.execute('SELECT id FROM projects WHERE org_id=? AND name=?',(org_id,DEMO_PROJECT_NAME)).fetchone()
    if row:return row['id']
    return create_project(org_id,DEMO_PROJECT_NAME,'Shared workspace for demo employee signups',creator_id)['id']

def get_project(project_id:str)->dict:
    with db() as conn:
        r=conn.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
        if not r:raise KeyError(project_id)
        d=dict(r);d['metadata']=json.loads(d.pop('metadata_json') or '{}');d['members']=[dict(x) for x in conn.execute('''SELECT pm.*,u.display_name,u.role_title,u.avatar FROM project_members pm LEFT JOIN users u ON u.id=pm.user_id WHERE pm.project_id=?''',(project_id,)).fetchall()];return d

def list_projects(org_id:str)->list[dict]:
    with db() as conn:rows=conn.execute('SELECT * FROM projects WHERE org_id=? ORDER BY updated_at DESC',(org_id,)).fetchall()
    out=[]
    for r in rows:d=dict(r);d['metadata']=json.loads(d.pop('metadata_json') or '{}');out.append(d)
    return out
