"""Shared trust-boundary validation for network and bridge operations."""
from __future__ import annotations

import hmac
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from ..config import settings


class SecurityError(ValueError):
    pass


def require_bridge(request: Request) -> None:
    expected = settings.bridge_token
    supplied = request.headers.get('authorization', '')
    wanted = f'Bearer {expected}'
    if not expected or not hmac.compare_digest(supplied.encode(), wanted.encode()):
        raise HTTPException(401, 'Invalid bridge credential')


def _public_address(host: str, port: int) -> None:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SecurityError('Host could not be resolved') from exc
    if not answers:
        raise SecurityError('Host could not be resolved')
    for answer in answers:
        ip = ipaddress.ip_address(answer[4][0])
        if not ip.is_global:
            raise SecurityError('Private, local, reserved, or special-use addresses are not allowed')


def public_https_url(raw: str, *, resolve: bool = True, hosts: set[str] | None = None) -> str:
    """Validate a public HTTPS URL before each outbound request or browser open."""
    try:
        parsed = urlparse((raw or '').strip())
        port = parsed.port
    except ValueError as exc:
        raise SecurityError('Malformed URL') from exc
    host = (parsed.hostname or '').rstrip('.').lower()
    if parsed.scheme != 'https' or not host or parsed.username or parsed.password:
        raise SecurityError('Only credential-free HTTPS URLs are allowed')
    if port not in (None, 443):
        raise SecurityError('Only the standard HTTPS port is allowed')
    if hosts is not None and host not in hosts:
        raise SecurityError('Host is not allowed')
    try:
        literal=ipaddress.ip_address(host)
    except ValueError:
        if resolve:
            _public_address(host, 443)
    else:
        if not literal.is_global:
            raise SecurityError('Private, local, reserved, or special-use addresses are not allowed')
    return parsed.geturl()


def github_repository_url(raw: str) -> str:
    url = public_https_url(raw, resolve=False, hosts={'github.com'})
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) != 2 or not all(p and p not in {'.', '..'} for p in parts):
        raise SecurityError('Expected https://github.com/<owner>/<repository>')
    if parsed.query or parsed.fragment or any(p.startswith('-') for p in parts):
        raise SecurityError('GitHub repository URL contains unsupported components')
    return f'https://github.com/{parts[0]}/{parts[1].removesuffix(".git")}.git'
