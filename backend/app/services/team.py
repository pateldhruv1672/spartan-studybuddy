from __future__ import annotations
import secrets, uuid
from ..db import db

def create_invite(org_id:str,invited_by:str,email:str|None,role_title:str)->dict:
    iid=str(uuid.uuid4()); token=secrets.token_urlsafe(8)
    with db() as conn:
        conn.execute('INSERT INTO invites(id,org_id,email,role_title,token,invited_by) VALUES(?,?,?,?,?,?)',(iid,org_id,email,role_title,token,invited_by))
    return {'id':iid,'token':token,'email':email,'role_title':role_title,'join_url':f'/join/{token}'}

def accept_invite(token:str,display_name:str,email:str|None,role_title:str)->dict:
    uid=str(uuid.uuid4())
    with db() as conn:
        inv=conn.execute("SELECT * FROM invites WHERE token=? AND status='pending'",(token,)).fetchone()
        if not inv: raise KeyError('invite')
        conn.execute('INSERT INTO users(id,org_id,display_name,email,role_title,avatar) VALUES(?,?,?,?,?,?)',(uid,inv['org_id'],display_name,email or inv['email'],role_title or inv['role_title'],''.join(x[0] for x in display_name.split()[:2]).upper()))
        conn.execute("UPDATE invites SET status='accepted',accepted_at=CURRENT_TIMESTAMP WHERE token=?",(token,))
    return {'id':uid,'org_id':inv['org_id'],'display_name':display_name,'email':email or inv['email'],'role_title':role_title}

def list_users(org_id:str)->list[dict]:
    with db() as conn:return [dict(r) for r in conn.execute('SELECT id,display_name,email,role_title,avatar,created_at FROM users WHERE org_id=? ORDER BY display_name',(org_id,)).fetchall()]
