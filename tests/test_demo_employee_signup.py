"""Demo mode: direct (uninvited) Employee signup, workspace auto-join, team/leaderboard visibility."""
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.db import db
from app.services.auth import issue_token

client = TestClient(app)


def _uniq_email():
    return f'demo-test-{uuid.uuid4().hex[:10]}@example.com'


def test_direct_employee_signup_no_org_id_joins_demo_workspace_as_learner():
    email = _uniq_email()
    r = client.post('/api/auth/register', json={
        'email': email, 'password': 'password123', 'display_name': 'New Hire', 'role': 'learner',
    })
    assert r.status_code == 200, r.text
    user = r.json()['user']
    assert user['role'] == 'learner'  # Employee maps to learner internally
    assert user['org_id'] == settings.demo_org_id
    with db() as conn:
        project = conn.execute('SELECT id FROM projects WHERE org_id=? AND name=?', (settings.demo_org_id, 'Demo Workspace')).fetchone()
        assert project
        member = conn.execute('SELECT role FROM project_members WHERE project_id=? AND user_id=?', (project['id'], user['id'])).fetchone()
        assert member and member['role'] == 'learner'


def test_repeated_direct_employee_signups_reuse_one_demo_workspace():
    with db() as conn:
        before = conn.execute('SELECT COUNT(*) FROM projects WHERE org_id=? AND name=?', (settings.demo_org_id, 'Demo Workspace')).fetchone()[0]
    for _ in range(2):
        r = client.post('/api/auth/register', json={
            'email': _uniq_email(), 'password': 'password123', 'display_name': 'Another Hire', 'role': 'learner',
        })
        assert r.status_code == 200, r.text
    with db() as conn:
        after = conn.execute('SELECT COUNT(*) FROM projects WHERE org_id=? AND name=?', (settings.demo_org_id, 'Demo Workspace')).fetchone()[0]
    assert before == after  # idempotent: no duplicate workspace created


def test_employee_visible_in_manager_team_view():
    email = _uniq_email()
    r = client.post('/api/auth/register', json={
        'email': email, 'password': 'password123', 'display_name': 'Team Visible Hire', 'role': 'learner',
    })
    uid = r.json()['user']['id']
    with db() as conn:
        mgr = conn.execute("SELECT id FROM users WHERE org_id=? AND app_role='manager' LIMIT 1", (settings.demo_org_id,)).fetchone()
    headers = {'Authorization': 'Bearer ' + issue_token(mgr['id'])}
    team = client.get('/api/team', headers=headers, params={'org_id': settings.demo_org_id})
    assert team.status_code == 200, team.text
    assert any(u['id'] == uid for u in team.json())


def test_employee_leaderboard_eligible_manager_excluded():
    # Mirrors LearnerDashboardPage's real auto-assignment: a learner with no path gets one
    # on first workspace visit (POST /api/onboarding/for-role), which is what actually puts
    # them in onboarding_members -- project membership alone isn't enough to rank.
    with db() as conn:
        project = conn.execute('SELECT id FROM projects WHERE org_id=? AND name=?', (settings.demo_org_id, 'Demo Workspace')).fetchone()
        mgr = conn.execute("SELECT id FROM users WHERE org_id=? AND app_role='manager' LIMIT 1", (settings.demo_org_id,)).fetchone()
    r = client.post('/api/auth/register', json={
        'email': _uniq_email(), 'password': 'password123', 'display_name': 'Leaderboard Hire', 'role': 'learner',
    })
    uid = r.json()['user']['id']
    headers = {'Authorization': 'Bearer ' + issue_token(uid)}
    role_req = client.post('/api/onboarding/for-role', headers=headers, json={'user_id': uid, 'project_id': project['id']})
    assert role_req.status_code == 200, role_req.text
    lb = client.get(f"/api/projects/{project['id']}/leaderboard", headers=headers)
    assert lb.status_code == 200, lb.text
    rows = lb.json()['leaderboard']
    assert any(row['user_id'] == uid and row['xp'] == 0 for row in rows)  # fresh employee appears, 0 progress is fine
    assert not any(row['user_id'] == mgr['id'] for row in rows)  # manager never ranks as an employee


def test_manager_signup_still_creates_own_org():
    r = client.post('/api/auth/register', json={
        'email': _uniq_email(), 'password': 'password123', 'display_name': 'New Manager', 'role': 'manager',
    })
    assert r.status_code == 200, r.text
    user = r.json()['user']
    assert user['role'] == 'manager'
    assert user['org_id'] != settings.demo_org_id


def test_duplicate_email_signup_rejected():
    email = _uniq_email()
    first = client.post('/api/auth/register', json={
        'email': email, 'password': 'password123', 'display_name': 'First', 'role': 'learner',
    })
    assert first.status_code == 200
    second = client.post('/api/auth/register', json={
        'email': email, 'password': 'password123', 'display_name': 'Second', 'role': 'learner',
    })
    assert second.status_code == 400


def test_invited_employee_signup_still_works():
    with db() as conn:
        mgr = conn.execute("SELECT id FROM users WHERE org_id=? AND app_role='manager' LIMIT 1", (settings.demo_org_id,)).fetchone()
    headers = {'Authorization': 'Bearer ' + issue_token(mgr['id'])}
    email = _uniq_email()
    inv = client.post('/api/team/invite', headers=headers, json={
        'org_id': settings.demo_org_id, 'invited_by': mgr['id'], 'email': email,
    })
    assert inv.status_code == 200, inv.text
    token = inv.json()['token']
    accepted = client.post('/api/auth/accept-invite', json={
        'token': token, 'display_name': 'Invited Hire', 'password': 'password123', 'email': email,
    })
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['user']['role'] == 'learner'
