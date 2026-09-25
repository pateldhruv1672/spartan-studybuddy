from __future__ import annotations
import re,secrets,uuid
from typing import Any
from ..db import db

_EMAIL=re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _invite(row:Any)->dict:
    d=dict(row)
    d['expired']=bool(d.pop('is_expired',False))
    if d['expired'] and d.get('status')=='pending':d['status']='expired'
    d['join_url']=f"/join/{d['token']}"
    return d


def create_invite(org_id:str,invited_by:str,email:str|None,role_title:str,project_id:str|None=None)->dict:
    email=(email or '').strip().lower()
    if not _EMAIL.fullmatch(email):raise ValueError('A valid work email is required')
    with db() as conn:
        conn.execute('SELECT id FROM organizations WHERE id=? FOR UPDATE',(org_id,))
        existing=conn.execute("""SELECT i.*,o.name AS organization_name,p.name AS project_name,
          (i.expires_at IS NOT NULL AND i.expires_at<=CURRENT_TIMESTAMP) AS is_expired
          FROM invites i JOIN organizations o ON o.id=i.org_id LEFT JOIN projects p ON p.id=i.project_id
          WHERE i.org_id=? AND lower(i.email)=? AND i.project_id IS NOT DISTINCT FROM ? AND i.status='pending'
          AND (i.expires_at IS NULL OR i.expires_at>CURRENT_TIMESTAMP) ORDER BY i.created_at DESC LIMIT 1""",(org_id,email,project_id)).fetchone()
        if existing:return _invite(existing)
        iid=str(uuid.uuid4());token=secrets.token_urlsafe(32)
        conn.execute("INSERT INTO invites(id,org_id,email,role_title,token,invited_by,project_id,expires_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP + INTERVAL '7 days')",(iid,org_id,email,role_title,token,invited_by,project_id))
        row=conn.execute("""SELECT i.*,o.name AS organization_name,p.name AS project_name,false AS is_expired
          FROM invites i JOIN organizations o ON o.id=i.org_id LEFT JOIN projects p ON p.id=i.project_id WHERE i.id=?""",(iid,)).fetchone()
    return _invite(row)


def list_invites(org_id:str)->list[dict]:
    with db() as conn:
        rows=conn.execute("""SELECT i.*,o.name AS organization_name,p.name AS project_name,
          (i.expires_at IS NOT NULL AND i.expires_at<=CURRENT_TIMESTAMP) AS is_expired
          FROM invites i JOIN organizations o ON o.id=i.org_id LEFT JOIN projects p ON p.id=i.project_id
          WHERE i.org_id=? ORDER BY i.created_at DESC""",(org_id,)).fetchall()
    return [_invite(r) for r in rows]


def invitations_for_user(user_id:str)->list[dict]:
    with db() as conn:
        user=conn.execute('SELECT email FROM users WHERE id=?',(user_id,)).fetchone()
        if not user or not user['email']:return []
        rows=conn.execute("""SELECT i.*,o.name AS organization_name,p.name AS project_name,false AS is_expired
          FROM invites i JOIN organizations o ON o.id=i.org_id LEFT JOIN projects p ON p.id=i.project_id
          WHERE lower(i.email)=lower(?) AND i.status='pending' AND (i.expires_at IS NULL OR i.expires_at>CURRENT_TIMESTAMP)
          ORDER BY i.created_at DESC""",(user['email'],)).fetchall()
    return [_invite(r) for r in rows]


def revoke_invite(org_id:str,token:str)->bool:
    with db() as conn:
        row=conn.execute("UPDATE invites SET status='revoked' WHERE org_id=? AND token=? AND status='pending' RETURNING id",(org_id,token)).fetchone()
    return bool(row)


def _empty_personal_org(conn,user:Any)->bool:
    org=user['org_id']
    users=conn.execute('SELECT COUNT(*) FROM users WHERE org_id=?',(org,)).fetchone()[0]
    projects=conn.execute('SELECT COUNT(*) FROM projects WHERE org_id=?',(org,)).fetchone()[0]
    activity=conn.execute('''SELECT
      (SELECT COUNT(*) FROM chat_threads WHERE user_id=?) +
      (SELECT COUNT(*) FROM memory_items WHERE user_id=?) +
      (SELECT COUNT(*) FROM learning_events WHERE user_id=?) +
      (SELECT COUNT(*) FROM agent_traces WHERE user_id=?)''',(user['id'],user['id'],user['id'],user['id'])).fetchone()[0]
    for table,column in (('resource_sessions','user_id'),('mastery','user_id'),('agent_jobs','user_id'),('quiz_attempts','user_id'),('onboarding_members','user_id'),('roadmaps','owner_user_id'),('roadmap_members','user_id'),('progress','user_id'),('achievements','user_id'),('project_members','user_id'),('invites','invited_by')):
        if conn.execute(f'SELECT 1 FROM {table} WHERE {column}=? LIMIT 1',(user['id'],)).fetchone():
            return False
    return users==1 and projects==0 and activity==0


def accept_existing_invite(user_id:str,token:str)->dict:
    """Accept a pending email-bound invite without creating a duplicate identity."""
    with db() as conn:
        user=conn.execute('SELECT * FROM users WHERE id=? FOR UPDATE',(user_id,)).fetchone()
        if not user or not user['email']:raise ValueError('Signed-in account has no email address')
        inv=conn.execute("""UPDATE invites SET status='accepting' WHERE token=? AND lower(email)=lower(?)
          AND status='pending' AND (expires_at IS NULL OR expires_at>CURRENT_TIMESTAMP) RETURNING *""",(token,user['email'])).fetchone()
        if not inv:raise KeyError('invite')
        old_org=user['org_id']
        try:
            if old_org!=inv['org_id']:
                if not _empty_personal_org(conn,user):
                    raise ValueError('This account already belongs to an active organization. Use a separate invited email or ask an administrator to transfer it.')
                conn.execute("UPDATE users SET org_id=?,app_role='learner',role_title=? WHERE id=?",(inv['org_id'],inv['role_title'],user_id))
            else:
                conn.execute("UPDATE users SET role_title=? WHERE id=?",(inv['role_title'],user_id))
            if inv['project_id']:
                conn.execute("INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,'learner') ON CONFLICT DO NOTHING",(inv['project_id'],user_id))
            conn.execute("UPDATE invites SET status='accepted',accepted_at=CURRENT_TIMESTAMP WHERE id=? AND status='accepting'",(inv['id'],))
        except Exception:
            conn.execute("UPDATE invites SET status='pending' WHERE id=? AND status='accepting'",(inv['id'],))
            raise
        updated=conn.execute('SELECT id,org_id,display_name,email,role_title,avatar,app_role FROM users WHERE id=?',(user_id,)).fetchone()
    d=dict(updated);d['role']=d.pop('app_role')
    return d


def list_users(org_id:str)->list[dict]:
    with db() as conn:
        rows=[dict(r) for r in conn.execute('SELECT id,display_name,email,role_title,avatar,app_role,created_at FROM users WHERE org_id=? ORDER BY display_name',(org_id,)).fetchall()]
        ws={}
        for r in conn.execute('SELECT m.user_id,m.project_id FROM project_members m JOIN projects p ON p.id=m.project_id WHERE p.org_id=?',(org_id,)).fetchall():ws.setdefault(r['user_id'],[]).append(r['project_id'])
    for r in rows:r['workspace_ids']=ws.get(r['id'],[])
    return rows
