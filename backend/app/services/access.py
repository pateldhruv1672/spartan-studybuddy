"""Who may touch which workspace.

Rules (enforced whenever the caller is identified by a login token):
  * a MANAGER can see and manage every workspace of their organisation
  * a LEARNER can only use workspaces a manager assigned to them (rows in `project_members`)
  * anything else answers 404 (inaccessible resources are indistinguishable from missing ones)
  * a token always wins over a client-supplied `user_id` (mismatch -> 403)

Anonymous callers are allowed only when an operator explicitly enables legacy/demo mode (`STUDYBUDDY_REQUIRE_AUTH=0`).
The shipped default requires authentication, and the Chrome and VS Code extensions now send user tokens.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from ..config import settings
from ..db import db
from . import auth


def identify(request: Request, claimed: str | None = None) -> tuple[str, bool]:
    """(user_id, authenticated)."""
    header = request.headers.get('authorization', '')
    if header.lower().startswith('bearer '):
        try:
            uid = auth.user_id_from_token(header[7:].strip())
        except auth.AuthError as exc:
            raise HTTPException(401, str(exc))
        if claimed and claimed != uid:
            raise HTTPException(403, 'user_id does not match the signed-in user')
        return uid, True
    if settings.require_auth:
        raise HTTPException(401, 'Not signed in')
    return claimed or settings.demo_user_id, False


def user_row(uid: str) -> dict[str, Any] | None:
    with db() as conn:
        r = conn.execute('SELECT id,org_id,app_role,role_title,display_name FROM users WHERE id=?', (uid,)).fetchone()
    return dict(r) if r else None


def project_row(project_id: str) -> dict[str, Any] | None:
    with db() as conn:
        r = conn.execute('SELECT id,org_id FROM projects WHERE id=?', (project_id,)).fetchone()
    return dict(r) if r else None


def is_member(project_id: str, uid: str) -> bool:
    with db() as conn:
        return conn.execute('SELECT 1 FROM project_members WHERE project_id=? AND user_id=?', (project_id, uid)).fetchone() is not None


def check_project(request: Request, project_id: str, claimed: str | None = None, manager: bool = False) -> str:
    """Authorize access to one workspace; returns the effective user id."""
    uid, authed = identify(request, claimed)
    if not authed:
        return uid
    u, p = user_row(uid), project_row(project_id)
    if not u or not p or u['org_id'] != p['org_id']:
        raise HTTPException(404, 'Workspace not found')
    if u['app_role'] == 'manager':
        return uid
    if manager:
        raise HTTPException(403, 'Managers only')
    if not is_member(project_id, uid):
        raise HTTPException(404, 'Workspace not found')
    return uid


def project_of_path(path_id: str) -> str:
    with db() as conn:
        r = conn.execute('SELECT project_id FROM onboarding_paths WHERE id=?', (path_id,)).fetchone()
    if not r:
        raise HTTPException(404, 'Path not found')
    return r['project_id']


def project_of_document(document_id: str) -> str:
    with db() as conn:
        r = conn.execute('SELECT project_id FROM indexed_documents WHERE id=?', (document_id,)).fetchone()
    if not r:
        raise HTTPException(404, 'Document not found')
    return r['project_id']


def check_path(request: Request, path_id: str, claimed: str | None = None, manager: bool = False) -> str:
    return check_project(request, project_of_path(path_id), claimed, manager)


def check_document(request: Request, document_id: str) -> str:
    return check_project(request, project_of_document(document_id))


def check_self(request: Request, user_id: str) -> str:
    """The caller must be `user_id` (a manager of the same organisation may act on a teammate's records)."""
    uid, authed = identify(request, None)
    if not authed or uid == user_id:
        return uid if authed else user_id
    caller, target = user_row(uid), user_row(user_id)
    if caller and target and caller['app_role'] == 'manager' and caller['org_id'] == target['org_id']:
        return user_id
    raise HTTPException(403, 'Not your data')


def check_user_project(request: Request, user_id: str, project_id: str | None) -> str:
    """Records of `user_id` inside a workspace: the caller needs access to the workspace AND must be that user (or their manager)."""
    uid, authed = identify(request, None)
    if not authed:
        return user_id
    if project_id:
        check_project(request, project_id)
    return check_self(request, user_id)


def check_thread(request: Request, thread_id: str) -> str:
    with db() as conn:
        r = conn.execute('SELECT user_id,project_id FROM chat_threads WHERE id=?', (thread_id,)).fetchone()
    if not r:
        raise HTTPException(404, 'Thread not found')
    uid, authed = identify(request, r['user_id'])
    if r['project_id']:check_project(request, r['project_id'],uid)
    return uid


def check_any_manager(request: Request) -> str:
    uid, authed = identify(request, None)
    if authed:
        u = user_row(uid)
        if not u or u['app_role'] != 'manager':
            raise HTTPException(403, 'Managers only')
    return uid


def check_org_manager(request: Request, org_id: str) -> str:
    uid, authed = identify(request, None)
    if not authed:
        return uid
    u = user_row(uid)
    if not u or u['org_id'] != org_id or u['app_role'] != 'manager':
        raise HTTPException(403, 'Managers only')
    return uid


def check_manager_of_user(request: Request, target_user_id: str) -> str:
    """Caller must be a manager in the same organisation as `target_user_id`."""
    t = user_row(target_user_id)
    if t is None:
        raise HTTPException(404, 'User not found')
    return check_org_manager(request, t['org_id'])


def accessible_projects(request: Request, org_id: str) -> list[dict[str, Any]] | None:
    """Projects visible to the caller, or None for anonymous legacy mode (caller falls back to the full org list)."""
    uid, authed = identify(request, None)
    if not authed:
        return None
    u = user_row(uid)
    if not u or u['org_id'] != org_id:
        return []
    with db() as conn:
        if u['app_role'] == 'manager':
            rows = conn.execute('SELECT * FROM projects WHERE org_id=? ORDER BY updated_at DESC', (org_id,)).fetchall()
        else:
            rows = conn.execute('''SELECT p.* FROM projects p JOIN project_members m ON m.project_id=p.id
                                   WHERE p.org_id=? AND m.user_id=? ORDER BY p.updated_at DESC''', (org_id, uid)).fetchall()
    import json
    out = []
    for r in rows:
        d = dict(r)
        d['metadata'] = json.loads(d.pop('metadata_json') or '{}')
        out.append(d)
    return out


def assign_member(project_id: str, user_id: str, role: str = 'learner') -> None:
    """Assign a workspace to a person (same organisation only)."""
    p, u = project_row(project_id), user_row(user_id)
    if not p:
        raise HTTPException(404, 'Workspace not found')
    if not u or u['org_id'] != p['org_id']:
        raise HTTPException(404, 'User not found in this organization')
    with db() as conn:
        conn.execute('INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?) ON CONFLICT DO NOTHING', (project_id, user_id, role))
