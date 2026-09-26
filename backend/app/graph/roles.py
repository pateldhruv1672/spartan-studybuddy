"""Role -> relevant subgraph.

Relevance of a node for a role blends four explainable signals:
  seeds      direct evidence the node belongs to the role (code-location globs, role doc keywords, role tech/concepts)
  ppr        personalised PageRank from those seeds (what the role's areas depend on / are documented by / are tested by)
  fan_in     how many files depend on it (shared foundations every newcomer touches)
  entry      README / architecture docs / entry points (orientation for everyone)
Weights are constants below so they are easy to ablate (see docs/GRAPH_ONBOARDING_PLAN.md, experiment E4).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from . import catalog
from .algorithms import normalize, personalized_pagerank
from .view import View, glob_to_regex, matches_any, require_view

# seed mass per evidence group (renormalised if a group is empty)
GROUP_MASS = {'concept': 0.25, 'tech': 0.15, 'glob': 0.35, 'doc': 0.20, 'entry': 0.05}
BLEND = {'ppr': 0.55, 'seed': 0.25, 'fan_in': 0.15, 'entry': 0.05}
ALPHA = 0.2
TEST_PENALTY = 0.8
AVOID_PENALTY = 0.25           # cross-discipline code the role rarely needs first (e.g. UI files for a backend role)
RANKABLE = {'file', 'doc', 'symbol', 'section'}


@dataclass
class NodeScore:
    rel: float
    ppr: float = 0.0
    seed: float = 0.0
    fan_in: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class Ranking:
    role: dict[str, Any]
    confidence: float
    view: View
    scores: dict[str, NodeScore]
    ppr: dict[str, float]                       # all node kinds (tech/concept included)
    role_concepts: dict[str, float]
    signals: dict[str, Any]
    seed_ids: set[str]


def resolve_role(role: str | None) -> tuple[dict[str, Any], float]:
    rs = catalog.roles()
    if role and role in rs:
        return rs[role], 1.0
    return catalog.match_role(role)


def _doc_seed_rows(project_id: str, query: str) -> tuple[list[tuple[str, float]], bool]:
    """(document_id, weight) from sparse (+ dense when the embedding server is up) retrieval over the role's keywords."""
    from ..services.indexer import _dense, _fts
    rows: dict[str, float] = {}
    dense_ok = False
    try:
        for rank, r in enumerate(_fts(project_id, query, 40), 1):
            doc = r['id'].rsplit(':', 1)[0]
            rows[doc] = max(rows.get(doc, 0.0), 1.0 / (60 + rank))
    except Exception:
        pass
    try:                                    # read-time ranking may degrade to sparse-only; *indexing* still fails closed
        for rank, r in enumerate(_dense(project_id, query, 30), 1):
            doc = r['id'].rsplit(':', 1)[0]
            rows[doc] = rows.get(doc, 0.0) + 1.15 / (60 + rank)
        dense_ok = True
    except Exception:
        pass
    return sorted(rows.items(), key=lambda x: -x[1]), dense_ok


def rank_for_role(project_id: str, role: str | None, scope: list[str] | None = None, view: View | None = None) -> Ranking:
    v = view or require_view(project_id)
    profile, conf = resolve_role(role)
    cs = catalog.concepts()
    globs = [glob_to_regex(g) for g in profile['path_globs']]
    avoid = [glob_to_regex(g) for g in profile.get('avoid_globs', [])]
    scope_re = [glob_to_regex(g) for g in (scope or []) if g.strip()]
    role_concepts = {**{k: w * 0.5 for k, w in catalog.baseline_concepts().items()}, **profile['concepts']}
    reasons: dict[str, list[str]] = {}
    groups: dict[str, dict[str, float]] = {k: {} for k in GROUP_MASS}

    def in_scope(n: dict[str, Any]) -> bool:
        return not scope_re or (n['path'] is not None and matches_any(n['path'], scope_re) is not None)

    def add(group: str, nid: str, w: float, why: str | None = None) -> None:
        groups[group][nid] = groups[group].get(nid, 0.0) + w
        if why:
            r = reasons.setdefault(nid, [])
            if why not in r:
                r.append(why)

    # concept + tech seeds
    for cid, w in role_concepts.items():
        for nid in v.by_name.get(cs[cid]['name'].lower(), []):
            if v.node(nid)['kind'] == 'concept':
                add('concept', nid, w)
    for nid in v.by_kind.get('tech', []):
        n = v.node(nid)
        if n['meta'].get('category') in profile['tech_categories']:
            add('tech', nid, 1.0)
    # code-location seeds
    for nid in v.by_kind.get('file', []) + v.by_kind.get('doc', []):
        n = v.node(nid)
        if not n['path'] or not in_scope(n):
            continue
        gi = matches_any(n['path'], globs)
        if gi is not None:
            add('glob', nid, 1.0, f"Lives in an area typical for a {profile['title']} (`{profile['path_globs'][gi]}`)")
        if 'entry' in n['meta'].get('hints', []):
            add('entry', nid, 1.0, 'Orientation: README / entry point / build file')
    # keyword-search seeds (sparse + dense)
    query = ' '.join(profile['doc_keywords'])
    doc_rows, dense_ok = _doc_seed_rows(project_id, query)
    for doc_id, w in doc_rows:
        nid = v.doc_node.get(doc_id)
        if nid and in_scope(v.node(nid)):
            add('doc', nid, w, f"Matches what a {profile['title']} looks for ({', '.join(profile['doc_keywords'][:3])}…)")

    active = {g: sum(d.values()) for g, d in groups.items() if d}
    mass = sum(GROUP_MASS[g] for g in active) or 1.0
    seeds: dict[str, float] = {}
    for g, d in groups.items():
        if not d:
            continue
        total = sum(d.values())
        for nid, w in d.items():
            seeds[nid] = seeds.get(nid, 0.0) + (GROUP_MASS[g] / mass) * (w / total)

    ppr_arr = personalized_pagerank(v.graph, seeds, alpha=ALPHA)
    ppr_all = {v.graph.ids[i]: float(ppr_arr[i]) for i in range(v.graph.n)} if v.graph.n else {}
    rankable = [nid for k in RANKABLE for nid in v.by_kind.get(k, [])]
    ppr_norm = normalize({n: ppr_all.get(n, 0.0) for n in rankable})
    direct = {nid: sum(GROUP_MASS[g] * groups[g].get(nid, 0.0) / (sum(groups[g].values()) or 1) for g in ('glob', 'doc')) for nid in rankable}
    direct_norm = normalize(direct)
    fan = {nid: math.log1p(v.node(nid)['meta'].get('fan_in', 0)) for nid in rankable if v.node(nid)['kind'] in {'file', 'doc'}}
    fan_norm = normalize(fan)

    scores: dict[str, NodeScore] = {}
    for nid in rankable:
        n = v.node(nid)
        if scope_re and n['kind'] in {'file', 'doc'} and not in_scope(n):
            continue
        entry = 1.0 if 'entry' in n['meta'].get('hints', []) else 0.0
        rel = BLEND['ppr'] * ppr_norm.get(nid, 0.0) + BLEND['seed'] * direct_norm.get(nid, 0.0) + BLEND['fan_in'] * fan_norm.get(nid, 0.0) + BLEND['entry'] * entry
        if n['meta'].get('test'):
            rel *= TEST_PENALTY
        if n['path'] and matches_any(n['path'], avoid) is not None:
            rel *= AVOID_PENALTY
        scores[nid] = NodeScore(rel=rel, ppr=ppr_norm.get(nid, 0.0), seed=direct_norm.get(nid, 0.0), fan_in=fan_norm.get(nid, 0.0), reasons=list(reasons.get(nid, [])))
    top = max((s.rel for s in scores.values()), default=0.0)
    if top > 0:
        for s in scores.values():
            s.rel = min(1.0, s.rel / top)
    _add_graph_reasons(v, scores, role_concepts, profile)
    return Ranking(profile, conf, v, scores, ppr_all, role_concepts,
                   {'dense': dense_ok, 'seeds': len(seeds), 'seed_kinds': {g: len(d) for g, d in groups.items() if d}}, set(seeds))


def _add_graph_reasons(v: View, scores: dict[str, NodeScore], role_concepts: dict[str, float], profile: dict[str, Any]) -> None:
    """Explain relevance from graph neighbourhood: role technologies, dependants, docs, tests, concepts."""
    cats = set(profile['tech_categories'])
    concept_names = {catalog.concepts()[c]['name'].lower(): c for c in role_concepts}
    for nid, sc in scores.items():
        n = v.node(nid)
        if n['kind'] not in {'file', 'doc'}:
            continue
        techs, docs, tests, concepts, dependants = [], [], [], [], 0
        for other, etype, _w, fwd in v.neighbors(nid):
            o = v.node(other)
            if o['kind'] == 'tech' and o['meta'].get('category') in cats and etype in {'uses', 'depends_on'}:
                techs.append(o['name'])
            elif etype == 'documents' and o['kind'] in {'file', 'doc'} and o['path']:
                docs.append(o['path'])
            elif etype == 'tests' and not fwd and o['path']:
                tests.append(o['path'])
            elif o['kind'] == 'concept' and o['name'].lower() in concept_names and etype == 'mentions':
                concepts.append(o['name'])
            elif etype in {'imports', 'calls'} and not fwd:
                dependants += 1
        if techs:
            sc.reasons.append(f"Uses {', '.join(sorted(set(techs))[:3])} — core to a {profile['title']}")
        if dependants >= 2:
            sc.reasons.append(f'Depended on by {dependants} other files')
        if docs:
            sc.reasons.append(f"{'Documents' if n['kind'] == 'doc' else 'Documented in'} {', '.join(sorted(set(docs))[:2])}")
        if tests:
            sc.reasons.append(f'Covered by {tests[0]}')
        if concepts:
            sc.reasons.append(f"Relates to {', '.join(sorted(set(concepts))[:2])}")
        if not sc.reasons and sc.ppr > 0.2:
            sc.reasons.append('Closely connected to the areas above')
