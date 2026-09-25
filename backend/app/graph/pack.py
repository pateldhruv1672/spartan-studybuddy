"""Assemble the role "knowledge pack": what a new hire should read/know first, with reasons and citations."""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter, defaultdict
from typing import Any

from . import catalog
from .algorithms import topo_order
from .roles import Ranking, rank_for_role
from .view import View, require_view

CODE_KINDS = {'file'}


def citation(n: dict[str, Any]) -> str:
    p = n.get('path') or n['name']
    if n.get('start_line'):
        return f"{p}:{n['start_line']}-{n.get('end_line') or n['start_line']}"
    loc = n['meta'].get('loc')
    return f'{p}:1-{loc}' if loc else p


def item(rk: Ranking, nid: str) -> dict[str, Any]:
    n = rk.view.node(nid)
    sc = rk.scores.get(nid)
    return {
        'node_id': nid, 'kind': n['kind'], 'name': n['name'], 'path': n['path'], 'language': n['language'],
        'document_id': n['document_id'], 'start_line': n['start_line'], 'end_line': n['end_line'],
        'relevance': round(sc.rel, 3) if sc else 0.0, 'reasons': (sc.reasons[:4] if sc else []), 'citation': citation(n),
    }


def _ranked(rk: Ranking, kinds: set[str], pred=None) -> list[str]:
    ids = [nid for nid, sc in rk.scores.items() if rk.view.node(nid)['kind'] in kinds and (pred is None or pred(rk.view.node(nid)))]
    return sorted(ids, key=lambda i: (-rk.scores[i].rel, rk.view.node(i)['path'] or rk.view.node(i)['name']))


def start_here(rk: Ranking, limit: int) -> list[str]:
    v = rk.view
    entry = [nid for nid in _ranked(rk, {'file', 'doc'}) if 'entry' in v.node(nid)['meta'].get('hints', [])]

    def order(nid: str) -> tuple[int, float]:
        n = v.node(nid)
        name = (n['path'] or n['name']).lower()
        base = name.rsplit('/', 1)[-1]
        if base.startswith('readme') and '/' not in name:
            return (0, -rk.scores[nid].rel)
        if 'architecture' in name or 'overview' in name or 'contributing' in name:
            return (1, -rk.scores[nid].rel)
        if n['kind'] == 'doc':
            return (2, -rk.scores[nid].rel)
        return (3, -rk.scores[nid].rel)

    docs = [nid for nid in _ranked(rk, {'doc'}) if any(k in (v.node(nid)['path'] or '').lower() for k in ('architecture', 'overview', 'getting', 'contributing', 'readme'))]
    merged = list(dict.fromkeys(sorted(entry + docs, key=order)))
    return merged[:limit]


def core_modules(rk: Ranking, limit: int) -> list[str]:
    v = rk.view
    def key(nid: str) -> float:
        return rk.scores[nid].rel * (1 + math.log1p(v.node(nid)['meta'].get('fan_in', 0)))
    files = [n for n in _ranked(rk, CODE_KINDS, lambda n: not n['meta'].get('test') and (n['language'] or set(n['meta'].get('hints', [])) & {'container', 'ci', 'iac', 'k8s'}))]
    return sorted(files, key=lambda n: -key(n))[:limit]


def subsystems(rk: Ranking, limit: int, per: int = 5) -> list[dict[str, Any]]:
    v = rk.view
    by_comm: dict[str, list[str]] = defaultdict(list)
    for nid in _ranked(rk, {'file', 'doc'}):
        cid = v.node(nid)['community_id']
        if cid:
            by_comm[cid].append(nid)
    out = []
    for cid, ids in by_comm.items():
        c = v.communities.get(cid)
        if not c:
            continue
        top = ids[:per]
        rel = sum(rk.scores[i].rel for i in top) / per
        out.append({
            'community': {'id': cid, 'name': c['name'], 'summary': c['summary'], 'size': c['size']},
            'relevance': round(rel, 3), 'items': [item(rk, i) for i in top],
            'depends_on': [v.communities[x]['name'] for x in sorted(c['meta'].get('deps_out', {}), key=lambda k: -c['meta']['deps_out'][k])[:3] if x in v.communities],
            'used_by': [v.communities[x]['name'] for x in sorted(c['meta'].get('deps_in', {}), key=lambda k: -c['meta']['deps_in'][k])[:3] if x in v.communities],
        })
    return sorted(out, key=lambda s: -s['relevance'])[:limit]


def concept_list(rk: Ranking) -> list[dict[str, Any]]:
    """Role concepts + language concepts + their prerequisites, prerequisite-first."""
    cs = catalog.concepts()
    v = rk.view
    wanted = dict(rk.role_concepts)
    for nid in v.by_kind.get('repo', []):
        for other, etype, _w, fwd in v.neighbors(nid, {'uses'}):
            o = v.node(other)
            if o['kind'] == 'concept':
                cid = next((k for k, c in cs.items() if c['name'] == o['name']), None)
                if cid:
                    wanted.setdefault(cid, 0.6)
    closure = catalog.concept_closure(list(wanted))
    prio = {c: wanted.get(c, 0.05) for c in closure}
    edges = [(p, c, 1.0) for c in closure for p in cs[c].get('prereqs', []) if p in closure]
    order = topo_order(closure, edges, prio)
    detected = defaultdict(list)
    for nid in v.by_kind.get('tech', []):
        n = v.node(nid)
        for c in n['meta'].get('concepts', []):
            detected[c].append(n['name'])
    dependants = defaultdict(list)
    for p, c, _ in edges:
        dependants[p].append(c)
    out = []
    for c in order:
        why = []
        if c in rk.role_concepts and c not in catalog.baseline_concepts():
            why.append(f"Core skill for a {rk.role['title']}")
        elif c in catalog.baseline_concepts():
            why.append('Baseline expectation for every engineer')
        needed_by = [cs[d]['name'] for d in dependants.get(c, []) if d in wanted][:2]
        if needed_by:
            why.append(f"Prerequisite for {', '.join(needed_by)}")
        if detected.get(c):
            why.append(f"Seen in this codebase via {', '.join(sorted(set(detected[c]))[:3])}")
        out.append({'id': c, 'name': cs[c]['name'], 'area': cs[c]['area'], 'weight': round(wanted.get(c, 0.0), 2), 'why': '; '.join(why) or 'Supporting prerequisite',
                    'prereqs': cs[c].get('prereqs', [])})
    return out


def glossary(rk: Ranking, limit: int = 12) -> list[dict[str, Any]]:
    v = rk.view
    ranked = _ranked(rk, {'symbol'}, lambda n: n['summary'] and not n['meta'].get('test') and n['meta'].get('symbol_kind') in {'class', 'function'})
    out = []
    for nid in ranked[:limit]:
        n = v.node(nid)
        out.append({'term': n['name'], 'definition': n['summary'], 'source': citation(n)})
    return out


def technologies(rk: Ranking, files: list[str]) -> list[dict[str, Any]]:
    v = rk.view
    cats = set(rk.role['tech_categories'])
    count: Counter[str] = Counter()
    for nid in files:
        for other, etype, _w, fwd in v.neighbors(nid, {'uses', 'depends_on'}):
            if v.node(other)['kind'] == 'tech':
                count[other] += 1
    rows = []
    for tid, k in count.items():
        t = v.node(tid)
        rows.append({'id': t['key'], 'name': t['name'], 'category': t['meta'].get('category'), 'public': bool(t['meta'].get('public')), 'files': k})
    return sorted(rows, key=lambda r: (r['category'] not in cats, -r['files'], r['name']))[:20]


def external_links(rk: Ranking, source_ids: list[str], limit: int = 20) -> list[dict[str, Any]]:
    v = rk.view
    found: dict[str, list[str]] = defaultdict(list)
    for nid in source_ids:
        for other, etype, _w, fwd in v.neighbors(nid, {'links_to'}):
            o = v.node(other)
            if o['kind'] == 'link' and fwd:
                found[other].append(v.node(nid)['path'] or v.node(nid)['name'])
    rows = [{'url': v.node(l)['meta'].get('url'), 'title': v.node(l)['name'], 'host': v.node(l)['meta'].get('host'), 'found_in': sorted(set(p))[:4]}
            for l, p in found.items()]
    return sorted(rows, key=lambda r: (-len(r['found_in']), r['title']))[:limit]


def subgraph(rk: Ranking, ids: list[str], max_nodes: int = 45) -> dict[str, Any]:
    v = rk.view
    role_concept_names = {catalog.concepts()[c]['name'] for c in rk.role_concepts}
    keep = list(dict.fromkeys(ids))[:max_nodes]
    extra_pool = sorted((n for n in v.by_kind.get('tech', []) if rk.ppr.get(n, 0) > 0), key=lambda n: -rk.ppr.get(n, 0))[:6]
    keep_set = set(keep) | set(extra_pool)
    nodes = [{'id': i, 'kind': v.node(i)['kind'], 'name': v.node(i)['name'], 'path': v.node(i)['path'],
              'relevance': round(rk.scores[i].rel if i in rk.scores else min(1.0, rk.ppr.get(i, 0) * 50), 3)} for i in keep_set]
    edges = []
    allowed = {'imports', 'tests', 'documents', 'uses', 'depends_on', 'calls'}
    for i in keep_set:
        for other, etype, w, fwd in v.neighbors(i, allowed):
            if fwd and other in keep_set:
                edges.append({'src': i, 'dst': other, 'type': etype, 'weight': round(w, 2)})
    return {'nodes': nodes, 'edges': edges}


def build_pack(project_id: str, role: str | None, scope: list[str] | None = None, limit: int = 12) -> dict[str, Any]:
    v = require_view(project_id)
    rk = rank_for_role(project_id, role, scope, view=v)
    sh = start_here(rk, min(limit, 8))
    core = core_modules(rk, limit)
    subs = subsystems(rk, 6)
    docs = _ranked(rk, {'doc'})[:limit]
    focus = list(dict.fromkeys(sh + core + [i['node_id'] for s in subs for i in s['items']] + docs))
    sub_ids = focus + [nid for nid in _ranked(rk, {'symbol'})[:8]]
    return {
        'role': {'id': rk.role['id'], 'title': rk.role['title'], 'description': rk.role['description'], 'confidence': rk.confidence,
                 'first_contribution': rk.role.get('first_contribution')},
        'build_id': v.build_id, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'start_here': [item(rk, i) for i in sh], 'core_modules': [item(rk, i) for i in core], 'subsystems': subs,
        'docs': [item(rk, i) for i in docs], 'external_links': external_links(rk, focus), 'technologies': technologies(rk, focus),
        'concepts': concept_list(rk), 'glossary': glossary(rk), 'subgraph': subgraph(rk, sub_ids),
        'signals': rk.signals,
        'stats': {'files_ranked': sum(1 for i in rk.scores if v.node(i)['kind'] == 'file'), 'docs_ranked': sum(1 for i in rk.scores if v.node(i)['kind'] == 'doc')},
    }
