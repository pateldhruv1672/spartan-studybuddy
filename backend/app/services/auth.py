from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from ..config import DATA_DIR, settings
from ..db import db

PBKDF2_ITERATIONS = 310_000
ROLES = {'manager', 'learner'}


class AuthError(Exception):
    pass


def _secret() -> bytes:
    if settings.auth_secret:
        return settings.auth_secret.encode()
    # No secret configured: persist a random one so tokens survive restarts without a hardcoded default.
    path = DATA_DIR / 'auth_secret'
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip().encode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, iterations, salt, digest = stored.split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(candidate.hex(), digest)
    except ValueError:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))


def issue_token(user_id: str) -> str:
    with db() as conn:
        row=conn.execute('SELECT token_version FROM users WHERE id=?',(user_id,)).fetchone()
    if not row:raise AuthError('Account unavailable')
    payload = _b64(json.dumps({'sub': user_id, 'version':row['token_version'], 'exp': int(time.time()) + settings.auth_token_ttl_hours * 3600}).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f'{payload}.{sig}'


def user_id_from_token(token: str) -> str:
    try:
        payload, sig = token.split('.')
    except ValueError:
        raise AuthError('Malformed token')
    expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise AuthError('Invalid token')
    data = json.loads(_unb64(payload))
    if data.get('exp', 0) < time.time():
        raise AuthError('Session expired')
    with db() as conn:
        row=conn.execute('SELECT token_version FROM users WHERE id=?',(data.get('sub'),)).fetchone()
    if not row or data.get('version',0)!=row['token_version']:
        raise AuthError('Session revoked')
    return data['sub']


def change_password(user_id: str, current_password: str, new_password: str) -> dict:
    if not 8 <= len(new_password) <= 1024:raise AuthError('Password must contain 8–1024 characters')
    with db() as conn:
        row=conn.execute('SELECT * FROM users WHERE id=? FOR UPDATE',(user_id,)).fetchone()
        if not row or not verify_password(current_password,row['password_hash']):
            raise AuthError('Current password is incorrect')
        conn.execute('UPDATE users SET password_hash=?,token_version=token_version+1 WHERE id=?',(hash_password(new_password),user_id))
    return {'token':issue_token(user_id),'user':_public(row)}


def _public(row: dict) -> dict:
    return {
        'id': row['id'],
        'org_id': row['org_id'],
        'display_name': row['display_name'],
        'email': row['email'],
        'role_title': row['role_title'],
        'avatar': row['avatar'],
        'role': row['app_role'],
    }


def _validate(email: str, password: str) -> str:
    email = (email or '').strip().lower()
    if '@' not in email:
        raise AuthError('Enter a valid email address')
    if len(password or '') < 8:
        raise AuthError('Password must be at least 8 characters')
    return email


def _avatar(name: str) -> str:
    return ''.join(x[0] for x in name.split()[:2]).upper() or '?'


def register(*, email: str, password: str, display_name: str, role: str, org_id: str, role_title: str | None = None, invited: bool = False) -> dict:
    email = _validate(email, password)
    if not display_name.strip():
        raise AuthError('Display name is required')
    if role not in ROLES:
        raise AuthError('Role must be manager or learner')
    isolate_manager = role == 'manager' and not settings.open_manager_signup
    if role == 'learner' and not invited and not settings.open_manager_signup:
        raise AuthError('Learners must use a valid team invitation')
    with db() as conn:
        existing = conn.execute('SELECT * FROM users WHERE lower(email)=?', (email,)).fetchall()
        if any(r['password_hash'] for r in existing):
            raise AuthError('An account with this email already exists')
        if isolate_manager:
            if existing:
                raise AuthError('This email belongs to an invited or seeded identity; accept the invitation instead of registering as a manager')
            # A public manager sign-up owns a fresh organisation; it never joins (or takes over) someone else's.
            org_id = 'org-' + uuid.uuid4().hex[:12]
            conn.execute('INSERT INTO organizations(id,name) VALUES(?,?)', (org_id, f"{display_name.strip()}'s organization"))
        elif org_id and not conn.execute('SELECT 1 FROM organizations WHERE id=?', (org_id,)).fetchone():
            if invited and row['org_id']!=org_id:
                raise AuthError('An identity with this email belongs to another organization')
            raise AuthError('Unknown organization')
        if existing:
            # A seeded or invited user with this email and no password claims that identity, keeping their history.
            row = existing[0]
            conn.execute(
                'UPDATE users SET password_hash=?, app_role=?, display_name=? WHERE id=?',
                (hash_password(password), role, display_name.strip(), row['id']),
            )
            uid = row['id']
        else:
            uid = str(uuid.uuid4())
            conn.execute(
                'INSERT INTO users(id,org_id,display_name,email,role_title,avatar,password_hash,app_role) VALUES(?,?,?,?,?,?,?,?)',
                (uid, org_id, display_name.strip(), email, (role_title or '').strip() or None, _avatar(display_name), hash_password(password), role),
            )
        user = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    return {'token': issue_token(uid), 'user': _public(dict(user))}


def login(*, email: str, password: str) -> dict:
    email = (email or '').strip().lower()
    with db() as conn:
        row = conn.execute('SELECT * FROM users WHERE lower(email)=? AND password_hash IS NOT NULL', (email,)).fetchone()
    if not row or not verify_password(password or '', row['password_hash']):
        raise AuthError('Incorrect email or password')
    return {'token': issue_token(row['id']), 'user': _public(dict(row))}


def accept_invite_with_password(*, token: str, display_name: str, password: str, email: str | None) -> dict:
    with db() as conn:
        inv = conn.execute("UPDATE invites SET status='accepting' WHERE token=? AND status='pending' AND (expires_at IS NULL OR expires_at>CURRENT_TIMESTAMP) RETURNING *", (token,)).fetchone()
    if not inv:
        raise AuthError('Invite not found or already used')
    if inv['email'] and email and inv['email'].strip().lower()!=email.strip().lower():
        with db() as conn:conn.execute("UPDATE invites SET status='pending' WHERE token=? AND status='accepting'",(token,))
        raise AuthError('Invitation is bound to a different email address')
    try:
        result = register(
            email=email or inv['email'] or '',
            password=password,
            display_name=display_name,
            role='learner',
            org_id=inv['org_id'],
            role_title=inv['role_title'],
            invited=True,
        )
    except Exception:
        with db() as conn:conn.execute("UPDATE invites SET status='pending' WHERE token=? AND status='accepting'",(token,))
        raise
    with db() as conn:
        conn.execute("UPDATE invites SET status='accepted',accepted_at=CURRENT_TIMESTAMP WHERE token=? AND status='accepting'", (token,))
        if inv['project_id']:
            conn.execute('INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?) ON CONFLICT DO NOTHING', (inv['project_id'], result['user']['id'], 'learner'))
    return result


def update_profile(user_id: str, display_name: str | None = None, role_title: str | None = None) -> dict:
    """Change a user's name and/or role profile (the role drives which onboarding path they get)."""
    with db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            raise AuthError('User not found')
        name = (display_name if display_name is not None else row['display_name']).strip()
        if not name:
            raise AuthError('Display name is required')
        title = (role_title if role_title is not None else row['role_title'])
        conn.execute('UPDATE users SET display_name=?, role_title=?, avatar=? WHERE id=?',
                     (name, (title or '').strip() or None, _avatar(name), user_id))
        row = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    return _public(dict(row))


def current_user(token: str) -> dict:
    uid = user_id_from_token(token)
    with db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not row or not row['password_hash']:
        raise AuthError('Account no longer exists')
    return _public(dict(row))
