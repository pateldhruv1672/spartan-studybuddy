"""Curated, public-safe knowledge used to interpret a private codebase.

* concepts  – generic engineering concepts with prerequisite edges, keywords and a vetted question bank
* techs     – well-known public libraries/tools mapped to a category and to concepts
* roles     – role profiles (which concepts, tech categories and code locations matter for a role)

Privacy: only ids from this catalog may ever be used to build *public* search topics. Private names
(internal packages, symbols, repo names) never appear here, so `public_search_topics()` cannot leak them.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent / 'data'


class CatalogError(ValueError):
    pass


@lru_cache(maxsize=1)
def concepts() -> dict[str, dict[str, Any]]:
    items = json.loads((DATA / 'concepts.json').read_text())
    out = {c['id']: c for c in items}
    if len(out) != len(items):
        raise CatalogError('duplicate concept ids')
    for c in items:
        for p in c.get('prereqs', []):
            if p not in out:
                raise CatalogError(f"concept {c['id']} has unknown prerequisite {p}")
        for q in c.get('questions', []):
            if not (0 <= q['answer'] < len(q['choices'])) or len(set(q['choices'])) != len(q['choices']):
                raise CatalogError(f"bad question in {c['id']}: {q['q']}")
    _assert_acyclic(out)
    return out


def _assert_acyclic(cs: dict[str, dict[str, Any]]) -> None:
    state: dict[str, int] = {}

    def visit(n: str, stack: list[str]) -> None:
        if state.get(n) == 1:
            raise CatalogError('prerequisite cycle: ' + ' -> '.join(stack + [n]))
        if state.get(n) == 2:
            return
        state[n] = 1
        for p in cs[n].get('prereqs', []):
            visit(p, stack + [n])
        state[n] = 2

    for k in cs:
        visit(k, [])


@lru_cache(maxsize=1)
def techs() -> dict[str, dict[str, Any]]:
    items = json.loads((DATA / 'techs.json').read_text())
    known = concepts()
    out = {t['id']: t for t in items}
    for t in items:
        for c in t.get('concepts', []):
            if c not in known:
                raise CatalogError(f"tech {t['id']} references unknown concept {c}")
    return out


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for t in techs().values():
        for a in t.get('aliases', []) + [t['id']]:
            idx.setdefault(a.lower(), t['id'])
    return idx


def lookup_tech(name: str) -> str | None:
    """Resolve an import/package/image name to a catalog tech id, trying progressively shorter prefixes."""
    n = name.strip().lower()
    if not n:
        return None
    idx = _alias_index()
    if n in idx:
        return idx[n]
    parts = re.split(r'[./:]', n)
    for i in range(len(parts) - 1, 0, -1):
        for sep in ('.', '/'):
            cand = sep.join(parts[:i])
            if cand in idx:
                return idx[cand]
    return None


@lru_cache(maxsize=1)
def _roles_doc() -> dict[str, Any]:
    doc = json.loads((DATA / 'roles.json').read_text())
    known = concepts()
    for r in doc['roles']:
        for c in r['concepts']:
            if c not in known:
                raise CatalogError(f"role {r['id']} references unknown concept {c}")
    for c in doc['baseline_concepts']:
        if c not in known:
            raise CatalogError(f'baseline references unknown concept {c}')
    return doc


def roles() -> dict[str, dict[str, Any]]:
    return {r['id']: r for r in _roles_doc()['roles']}


def baseline_concepts() -> dict[str, float]:
    return dict(_roles_doc()['baseline_concepts'])


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r'[^a-z0-9]+', text.lower()) if t}


def match_role(title: str | None) -> tuple[dict[str, Any], float]:
    """Map a free-text job title to the closest role profile. Returns (profile, confidence 0..1)."""
    rs = roles()
    if not title or not title.strip():
        return rs['software-engineer'], 0.0
    t = title.strip().lower()
    for r in rs.values():
        if t == r['id'] or t == r['title'].lower() or t in [a.lower() for a in r['aliases']]:
            return r, 1.0
    tt = _tokens(t)
    best, score = rs['software-engineer'], 0.0
    for r in rs.values():
        if r['id'] == 'software-engineer':
            continue
        cands = [r['title']] + r['aliases']
        s = 0.0
        for c in cands:
            ct = _tokens(c)
            if ct and ct <= tt:            # every alias token is present in the title
                s = max(s, 0.6 + 0.4 * len(ct) / max(len(tt), 1))
            elif ct & tt:
                s = max(s, 0.5 * len(ct & tt) / len(ct | tt))
        if s > score:
            best, score = r, s
    return (best, round(score, 2)) if score >= 0.3 else (rs['software-engineer'], 0.0)


def concept_closure(ids: list[str]) -> list[str]:
    """All prerequisites of `ids` (transitively), including the ids themselves."""
    cs = concepts()
    seen: dict[str, None] = {}

    def add(c: str) -> None:
        if c in seen:
            return
        for p in cs[c].get('prereqs', []):
            add(p)
        seen[c] = None

    for i in ids:
        if i in cs:
            add(i)
    return list(seen)


def public_search_topics(concept_ids: list[str], limit: int = 12) -> list[str]:
    """Generic, catalog-vetted search phrases for the public-web resource scout. Never contains private names."""
    cs = concepts()
    out: list[str] = []
    for c in concept_ids:
        t = cs.get(c, {}).get('search_topic')
        if t and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


LANGUAGE_CONCEPTS = {
    'py': 'python-fundamentals', 'python': 'python-fundamentals',
    'js': 'javascript-fundamentals', 'jsx': 'javascript-fundamentals', 'mjs': 'javascript-fundamentals',
    'ts': 'typescript-fundamentals', 'tsx': 'typescript-fundamentals',
}
