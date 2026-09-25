"""HTTP surface for graph onboarding (contract: docs/GRAPH_ONBOARDING_API.md)."""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import settings
from ..db import db
from ..services import access
from . import catalog, quiz as quizmod
from .builder import build_graph, graph_status, list_communities
from .pack import build_pack
from .rag import graph_search
from .roles import resolve_role
from .view import GraphNotBuilt, load_view, require_view

router = APIRouter()


# identity and workspace authorization: services/access.py (token wins over user_id; learners only see assigned workspaces)


# ---------------------------------------------------------------------------------------------------------
# roles
@router.get('/api/role-profiles')
def role_profiles() -> dict[str, Any]:
    cs = catalog.concepts()
    out = []
    for r in catalog.roles().values():
        out.append({'id': r['id'], 'title': r['title'], 'description': r['description'], 'aliases': r['aliases'], 'first_contribution': r['first_contribution'],
                    'concepts': sorted(({'id': c, 'name': cs[c]['name'], 'weight': w} for c, w in r['concepts'].items()), key=lambda x: -x['weight'])})
    return {'roles': out}


@router.get('/api/roles/match')
def roles_match(title: str = '') -> dict[str, Any]:
    r, conf = catalog.match_role(title)
    return {'role_id': r['id'], 'title': r['title'], 'confidence': conf}


# ---------------------------------------------------------------------------------------------------------
# graph
@router.get('/api/projects/{project_id}/graph/status')
def graph_status_ep(project_id: str, request: Request) -> dict[str, Any]:
    access.check_project(request, project_id)
    return graph_status(project_id)


@router.post('/api/projects/{project_id}/graph/rebuild')
def graph_rebuild(project_id: str, request: Request) -> dict[str, Any]:
    access.check_project(request, project_id, manager=True)
    try:
        return build_graph(project_id)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.get('/api/projects/{project_id}/graph/communities')
def graph_communities(project_id: str, request: Request) -> list[dict[str, Any]]:
    access.check_project(request, project_id)
    return list_communities(project_id)


def _public_node(n: dict[str, Any]) -> dict[str, Any]:
    return {k: n.get(k) for k in ('id', 'kind', 'name', 'path', 'document_id', 'start_line', 'end_line', 'language', 'summary', 'community_id')} | {'meta': n.get('meta', {})}


@router.get('/api/projects/{project_id}/graph/node/{node_id}')
def graph_node(project_id: str, node_id: str, request: Request) -> dict[str, Any]:
    access.check_project(request, project_id)
    try:
        v = require_view(project_id)
    except GraphNotBuilt:
        raise HTTPException(409, 'graph not built')
    if node_id not in v.nodes:
        raise HTTPException(404, 'node not found')
    nbrs = sorted(({'node': _public_node(v.node(o)), 'type': t, 'weight': round(w, 3), 'direction': 'out' if fwd else 'in'} for o, t, w, fwd in v.neighbors(node_id)),
                  key=lambda x: (-x['weight'], x['node']['name']))[:80]
    cid = v.node(node_id)['community_id']
    return {'node': _public_node(v.node(node_id)), 'community': ({k: v.communities[cid].get(k) for k in ('id', 'name', 'summary', 'size', 'keywords', 'summary_source', 'meta')} if cid in v.communities else None),
            'neighbors': nbrs}


class GraphSearchRequest(BaseModel):
    project_id: str
    query: str
    role: str | None = None
    top_k: int = Field(default=10, ge=1, le=40)


@router.post('/api/graph/search')
def graph_search_ep(req: GraphSearchRequest, request: Request) -> dict[str, Any]:
    access.check_project(request, req.project_id)
    if load_view(req.project_id) is None:
        raise HTTPException(409, 'graph not built')
    out = graph_search(req.project_id, req.query, req.top_k, req.role)
    return {k: out[k] for k in ('results', 'structure', 'communities')} | {'debug': out.get('debug', {})}


@router.get('/api/projects/{project_id}/knowledge-pack')
def knowledge_pack(project_id: str, request: Request, role: str | None = None, user_id: str | None = None, scope: str | None = None, limit: int = 12) -> dict[str, Any]:
    user_id = access.check_project(request, project_id, user_id)
    if not role and user_id:
        with db() as conn:
            r = conn.execute('SELECT role_title FROM users WHERE id=?', (user_id,)).fetchone()
        role = r['role_title'] if r else None
    try:
        return build_pack(project_id, role, [s for s in (scope or '').split(',') if s.strip()] or None, max(3, min(limit, 30)))
    except GraphNotBuilt:
        raise HTTPException(409, 'graph not built')


def _external_source_url(conn, doc: Any, start_line: int | None, end_line: int | None) -> str | None:
    """Canonical external URL for a document, using stored source metadata only — never a guess.

    GitHub-cloned files store the *local* clone path in indexed_documents.source_uri (useless externally),
    so the real repo URL + resolved commit is looked up from the owning `sources` row instead. Web and
    Google Drive sources already store their real canonical URL directly on the document. Uploads and
    VS Code-local files have no public source at all, so this returns None for them (never a broken link).
    """
    if doc['source_id']:
        src = conn.execute('SELECT kind,uri,metadata_json FROM sources WHERE id=?', (doc['source_id'],)).fetchone()
        if src and src['kind'] == 'github' and src['uri']:
            meta = json.loads(src['metadata_json'] or '{}')
            ref = meta.get('commit') or meta.get('branch') or 'HEAD'
            base = src['uri'].rstrip('/')
            if base.endswith('.git'):
                base = base[:-4]
            path = (doc['source_name'] or '').lstrip('/')
            if not path:
                return None
            url = f'{base}/blob/{ref}/{path}'
            if start_line:
                url += f'#L{start_line}' + (f'-L{end_line}' if end_line and end_line != start_line else '')
            return url
    uri = doc['source_uri']
    if uri and uri.startswith(('http://', 'https://')):
        return uri
    return None


@router.get('/api/documents/{document_id}/content')
def document_content(document_id: str, request: Request, start_line: int | None = None, end_line: int | None = None) -> dict[str, Any]:
    access.check_document(request, document_id)
    with db() as conn:
        doc = conn.execute('SELECT id,source_id,source_name,source_uri,language FROM indexed_documents WHERE id=?', (document_id,)).fetchone()
        if not doc:
            raise HTTPException(404, 'document not found')
        rows = conn.execute('SELECT content,start_line,end_line FROM indexed_chunks WHERE document_id=? ORDER BY ordinal', (document_id,)).fetchall()
        lo, hi = (start_line or 1), (end_line or (start_line or 1) + 399)
        picked = [r for r in rows if (r['end_line'] or 0) >= lo and (r['start_line'] or 0) <= hi] or rows[:1]
        resolved_start = min((r['start_line'] or lo) for r in picked) if picked else lo
        resolved_end = max((r['end_line'] or hi) for r in picked) if picked else hi
        external_url = _external_source_url(conn, doc, resolved_start, resolved_end)
    text = '\n'.join(r['content'] for r in picked)
    lines = text.splitlines()
    truncated = len(lines) > 400
    return {'document_id': document_id, 'path': doc['source_name'], 'language': doc['language'], 'start_line': resolved_start,
            'end_line': resolved_end, 'content': '\n'.join(lines[:400]), 'truncated': truncated, 'external_url': external_url}


# ---------------------------------------------------------------------------------------------------------
# roadmap entry point for a new hire
class PathAssignment(BaseModel):
    user_id: str


@router.post('/api/onboarding/path/{path_id}/members')
def assign_path(path_id: str, req: PathAssignment, request: Request):
    from ..services.path_management import assign
    access.check_path(request,path_id,manager=True)
    try:return assign(path_id,req.user_id)
    except ValueError as exc:raise HTTPException(409,str(exc))


@router.post('/api/onboarding/path/{path_id}/resource-scout')
def rescout_path(path_id: str, request: Request):
    from ..services.path_management import scout
    uid=access.check_path(request,path_id,manager=True)
    try:return scout(path_id,uid)
    except ValueError as exc:raise HTTPException(409,str(exc))


class ForRoleRequest(BaseModel):
    user_id: str = 'demo-spartan'
    project_id: str
    role: str | None = None
    level: Literal['junior', 'mid', 'senior'] = 'junior'


@router.post('/api/onboarding/for-role')
async def onboarding_for_role(req: ForRoleRequest, request: Request) -> dict[str, Any]:
    from ..agents.onboarding import GraphNotReady, for_role
    uid = access.check_project(request, req.project_id, req.user_id)      # learners can only start onboarding in a workspace assigned to them
    try:
        return await for_role(uid, req.project_id, req.role, req.level)
    except GraphNotReady as exc:
        raise HTTPException(409, str(exc))


# ---------------------------------------------------------------------------------------------------------
# quizzes
class QuizStartRequest(BaseModel):
    user_id: str = 'demo-spartan'


class QuizSubmitRequest(BaseModel):
    user_id: str = 'demo-spartan'
    answers: dict[str, Any] = Field(default_factory=dict)


def _quiz_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, quizmod.LockedError):
        return HTTPException(423, str(exc))
    if isinstance(exc, quizmod.NotMemberError):
        return HTTPException(403, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(404, 'quiz not found')
    return HTTPException(409, str(exc))


@router.get('/api/onboarding/path/{path_id}/items/{item_id}/quiz')
def quiz_get(path_id: str, item_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    uid = access.check_path(request, path_id, user_id)
    try:
        return quizmod.quiz_info(path_id, item_id, uid)
    except Exception as exc:
        raise _quiz_errors(exc)


@router.post('/api/onboarding/path/{path_id}/items/{item_id}/quiz/start')
def quiz_start(path_id: str, item_id: str, req: QuizStartRequest, request: Request) -> dict[str, Any]:
    uid = access.check_path(request, path_id, req.user_id)
    try:
        return quizmod.start_attempt(path_id, item_id, uid)
    except Exception as exc:
        raise _quiz_errors(exc)


@router.post('/api/onboarding/quiz/attempts/{attempt_id}/submit')
async def quiz_submit(attempt_id: str, req: QuizSubmitRequest, request: Request) -> dict[str, Any]:
    uid, _ = access.identify(request, req.user_id)
    with db() as conn:
        row=conn.execute('SELECT q.path_id FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id WHERE a.id=?',(attempt_id,)).fetchone()
    if not row:raise HTTPException(404,'Attempt unavailable')
    access.check_path(request,row['path_id'],uid)
    try:
        return await quizmod.submit_attempt(attempt_id, uid, req.answers)
    except Exception as exc:
        raise _quiz_errors(exc)


@router.get('/api/onboarding/path/{path_id}/items/{item_id}/history')
def quiz_history(path_id: str, item_id: str, request: Request, user_id: str | None = None):
    from .quiz_history import history
    uid = access.check_path(request, path_id, user_id)
    return history(path_id, item_id, uid)


@router.post('/api/onboarding/quiz/attempts/{attempt_id}/questions/{question_id}/hint')
def quiz_hint(attempt_id: str, question_id: str, req: QuizStartRequest, request: Request):
    from .quiz_history import hint
    uid, _ = access.identify(request, req.user_id)
    with db() as conn:
        row = conn.execute('SELECT q.path_id FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id WHERE a.id=?', (attempt_id,)).fetchone()
    if not row:raise HTTPException(404, 'Attempt unavailable')
    access.check_path(request, row['path_id'], uid)
    try:return hint(attempt_id, question_id, uid)
    except Exception as exc:raise _quiz_errors(exc)


@router.get('/api/onboarding/path/{path_id}/quizzes')
def quiz_list(path_id: str, request: Request, user_id: str | None = None) -> list[dict[str, Any]]:
    uid = access.check_path(request, path_id, user_id)
    try:
        return quizmod.list_quizzes(path_id, uid)
    except Exception as exc:
        raise _quiz_errors(exc)


@router.post('/api/onboarding/path/{path_id}/quizzes/generate')
async def quiz_generate(path_id: str, request: Request, background: BackgroundTasks, llm: bool = False, force: bool = False) -> dict[str, Any]:
    """Manager: (re)create quiz banks (e.g. for a legacy path) and optionally append model-written, verified questions."""
    access.check_path(request, path_id, manager=True)
    try:
        made = await quizmod.generate_quizzes(path_id, use_llm=False, force=force)
    except KeyError:
        raise HTTPException(404, 'path not found')
    if llm:
        background.add_task(quizmod.augment_with_llm, path_id)
    return {'generated': made, 'llm_augmentation': 'scheduled' if llm else 'off'}


# ---------------------------------------------------------------------------------------------------------
# gamification + analytics (spec sections 20 and 22)
class LeaderboardPreference(BaseModel):
    visible: bool


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1,max_length=1024)
    new_password: str = Field(min_length=8,max_length=1024)


@router.post('/api/auth/password')
def change_password(req: PasswordChange, request: Request):
    from ..services import auth
    uid,_=access.identify(request)
    try:return auth.change_password(uid,req.current_password,req.new_password)
    except auth.AuthError as exc:raise HTTPException(400,str(exc))


@router.get('/api/account/leaderboard-preference')
def get_leaderboard_preference(request: Request):
    uid,_=access.identify(request)
    with db() as conn:
        row=conn.execute('SELECT leaderboard_visible FROM users WHERE id=?',(uid,)).fetchone()
    if not row:raise HTTPException(404,'Account unavailable')
    return {'visible':row['leaderboard_visible']}


@router.patch('/api/account/leaderboard-preference')
def set_leaderboard_preference(req: LeaderboardPreference, request: Request):
    uid,_=access.identify(request)
    with db() as conn:
        conn.execute('UPDATE users SET leaderboard_visible=? WHERE id=?',(req.visible,uid))
    return {'visible':req.visible}


@router.get('/api/projects/{project_id}/leaderboard')
def project_leaderboard(project_id: str, request: Request, path_id: str | None = None):
    from ..services.leaderboard import leaderboard
    access.check_project(request,project_id)
    if path_id:
        access.check_path(request,path_id)
        with db() as conn:
            if conn.execute('SELECT project_id FROM onboarding_paths WHERE id=?',(path_id,)).fetchone()['project_id'] != project_id:
                raise HTTPException(404,'Path unavailable')
    with db() as conn:
        org_id=conn.execute('SELECT org_id FROM projects WHERE id=?',(project_id,)).fetchone()['org_id']
    return {'leaderboard':leaderboard(org_id,project_id,path_id),'period':'all_time','tie_break':'completed_items_desc,user_id_asc'}


@router.get('/api/users/{user_id}/achievements')
def user_achievements(user_id: str, request: Request, project_id: str | None = None) -> list[dict[str, Any]]:
    return quizmod.list_achievements(access.check_user_project(request, user_id, project_id), project_id)


@router.get('/api/projects/{project_id}/achievements')
def project_achievements(project_id: str, request: Request) -> list[dict[str, Any]]:
    access.check_project(request, project_id)
    return quizmod.list_achievements(None, project_id)


@router.get('/api/projects/{project_id}/knowledge-gaps')
def knowledge_gaps(project_id: str, request: Request) -> dict[str, Any]:
    access.check_project(request, project_id, manager=True)
    return quizmod.knowledge_gaps(project_id)


@router.get('/api/projects/{project_id}/analytics')
def project_analytics(project_id: str, request: Request) -> dict[str, Any]:
    access.check_project(request, project_id, manager=True)
    return quizmod.analytics(project_id)
