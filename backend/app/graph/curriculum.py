"""Deterministic, graph-grounded roadmap generation (an LLM may polish wording afterwards, never structure).

Structure of every generated path (spec section 19: order by prerequisite relationships, not only relevance):

  m0  Orientation      README / architecture / how to build-test-run           (orientation)
  m1+ Foundations      generic concepts the role needs, prerequisite-ordered    (foundations)
  ... Subsystems       code communities ranked for the role, ordered so that
                       what others depend on is learned first                   (subsystem)
  mN  First contribution  plan a first change + comprehensive review quiz       (handson)

INVARIANT (validated by `validate_plan`): the last item of every module is a quiz with id `<module>-quiz`.
Exercises (spec section 21) are generated from real call paths / untested code and live in `plan.exercises`.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

from . import catalog
from .algorithms import topo_order
from .pack import concept_list, item as pack_item, start_here, subsystems
from .roles import Ranking, rank_for_role
from .view import View, require_view

PASS_THRESHOLD = 0.7
UTILIZATION = 0.8                # share of the weekly hours assumed to be effective study time
MAX_FOUNDATION_SECTIONS = 3
SUBSYSTEM_FLOOR = 0.45            # keep subsystems whose relevance is at least this fraction of the best one
FOUNDATION_MIN_WEIGHT = 0.5
XP = {'internal_walkthrough': 40, 'doc_reading': 30, 'concept': 30, 'checkpoint': 60, 'quiz': 70, 'exercise': 150}


class PlanError(ValueError):
    pass


def _ref(rk: Ranking, nid: str) -> dict[str, Any]:
    it = pack_item(rk, nid)
    return {k: it[k] for k in ('node_id', 'kind', 'name', 'path', 'start_line', 'end_line', 'reasons', 'citation')}


def _minutes_for_files(v: View, ids: list[str]) -> int:
    total = 0.0
    for i in ids:
        n = v.node(i)
        loc = n['meta'].get('loc') or 60
        total += min(14.0, 6.0 + loc / 40.0) if n['kind'] == 'file' else 3.0 + (n['meta'].get('chars') or 4000) / 1200.0
    return max(8, int(round(total)))


def _entry_targets(v: View) -> list[str]:
    out: list[str] = []
    for nid in v.by_kind.get('file', []):
        out += v.node(nid)['meta'].get('targets', [])[:6]
    return list(dict.fromkeys(out))[:8]


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def module(self) -> str:
        m = f'm{self.n}'
        self.n += 1
        return m


def _quiz_item(mid: str, count: int, minutes: int | None = None) -> dict[str, Any]:
    return {'id': f'{mid}-quiz', 'type': 'quiz', 'title': 'Section quiz', 'minutes': minutes or max(4, int(count * 1.5) + 2), 'xp': XP['quiz'],
            'topic': 'Check your understanding', 'quiz': {'question_count': count, 'pass_threshold': PASS_THRESHOLD}}


def _concept_evidence(rk: Ranking, concept_id: str, limit: int = 3) -> list[str]:
    """Files in this codebase that use technologies teaching the concept (so foundations link back to real code)."""
    v = rk.view
    techs = {n for n in v.by_kind.get('tech', []) if concept_id in v.node(n)['meta'].get('concepts', [])}
    scored: dict[str, float] = {}
    for t in techs:
        for other, etype, _w, fwd in v.neighbors(t, {'uses', 'depends_on'}):
            o = v.node(other)
            if o['kind'] == 'file' and not fwd and other in rk.scores:
                scored[other] = rk.scores[other].rel
    return sorted(scored, key=lambda i: -scored[i])[:limit]


# ---------------------------------------------------------------------------------------------------------
def build_plan(project_id: str, role: str | None, level: str = 'junior', weeks: int = 4, hours_per_week: int = 8,
               background: str = '', scope: list[str] | None = None, quiz_questions: int = 5, mastery: dict[str, float] | None = None) -> dict[str, Any]:
    v = require_view(project_id)
    rk = rank_for_role(project_id, role, scope, view=v)
    profile = rk.role
    mastery = mastery or {}
    emphasis = {
        'junior': 'Explain the fundamentals, trace inputs and outputs, and verify a small change with guidance.',
        'mid': 'Trace system flows, reproduce a failure, debug across boundaries, and own a tested change.',
        'senior': 'Evaluate architecture tradeoffs, security boundaries, reliability risks, and cross-system impact.',
    }[level]
    q_count = max(3, min(8, quiz_questions))
    budget = int(weeks * hours_per_week * 60 * UTILIZATION)
    ids = _Ids()
    modules: list[dict[str, Any]] = []

    # ---- orientation ---------------------------------------------------------------------------------
    sh = start_here(rk, 5)
    o_id = ids.module()
    o_items: list[dict[str, Any]] = []
    docs_first = [n for n in sh if v.node(n)['kind'] == 'doc'] or sh[:1]
    if docs_first:
        o_items.append({'id': f'{o_id}-i1', 'type': 'doc_reading', 'title': 'Read the project overview and architecture', 'minutes': _minutes_for_files(v, docs_first),
                        'xp': XP['doc_reading'], 'topic': 'Project overview', 'repo_refs': [v.node(n)['path'] for n in docs_first if v.node(n)['path']],
                        'node_refs': [_ref(rk, n) for n in docs_first]})
    entry_files = [n for n in sh if n not in docs_first]
    targets = _entry_targets(v)
    o_items.append({'id': f'{o_id}-i{len(o_items) + 1}', 'type': 'internal_walkthrough', 'title': 'Build, test and run the project', 'minutes': 20, 'xp': XP['internal_walkthrough'],
                    'topic': 'Build, test and run', 'repo_refs': [v.node(n)['path'] for n in entry_files if v.node(n)['path']],
                    'node_refs': [_ref(rk, n) for n in entry_files],
                    'checkpoint_question': 'Which commands build, test and run this project, and where did you find them?' + (f" (Hint: look for {', '.join(targets[:4])}.)" if targets else '')})
    o_items.append(_quiz_item(o_id, q_count))
    modules.append({'id': o_id, 'title': 'Orientation: how this project is organised', 'kind': 'orientation',
                    'outcome': 'You can navigate the repository, find the docs and run the project locally.',
                    'objectives': ['Find the architecture documentation', 'Identify the entry points', 'Build, test and run locally'],
                    'concept_ids': [], 'quiz_seed': {'node_ids': sh, 'concept_ids': [], 'kind': 'orientation'}, 'items': o_items})

    # ---- foundations -----------------------------------------------------------------------------------
    concepts = concept_list(rk)
    keep = [c for c in concepts if c['weight'] >= FOUNDATION_MIN_WEIGHT or any(c['id'] in d['prereqs'] and d['weight'] >= FOUNDATION_MIN_WEIGHT for d in concepts)]
    # Verified mastery changes study time; free-text background never proves mastery.
    known = {c['id'] for c in keep if mastery.get(c['name'], mastery.get(c['id'], 0)) >= 0.8}
    per = max(2, math.ceil(len(keep) / MAX_FOUNDATION_SECTIONS)) if keep else 0
    cs = catalog.concepts()
    for k in range(0, len(keep), per or 1):
        chunk = keep[k:k + per]
        if not chunk:
            break
        mid = ids.module()
        items = []
        for c in chunk:
            ev = _concept_evidence(rk, c['id'])
            items.append({'id': f'{mid}-i{len(items) + 1}', 'type': 'concept', 'title': c['name'], 'minutes': 15 + 10 * cs[c['id']]['difficulty'], 'xp': XP['concept'],
                          'topic': c['id'], 'concept_id': c['id'], 'repo_refs': [v.node(n)['path'] for n in ev if v.node(n)['path']], 'node_refs': [_ref(rk, n) for n in ev],
                          'why': c['why'], 'description': cs[c['id']]['description']})
            if c['id'] in known:
                items[-1]['minutes'] = 10
                items[-1]['description'] += ' Verified mastery: use this as a brief review before the checkpoint.'
            elif level != 'junior':
                items[-1]['minutes'] = max(15, items[-1]['minutes'] - 10)
        items.append(_quiz_item(mid, q_count))
        area = chunk[0]['area'].replace('-', ' ')
        modules.append({'id': mid, 'title': f"Foundations {len(modules)}: {', '.join(c['name'] for c in chunk[:2])}{'…' if len(chunk) > 2 else ''}", 'kind': 'foundations',
                        'outcome': f"You can explain the {area} concepts the codebase relies on: " + ', '.join(c['name'] for c in chunk) + '.',
                        'objectives': [f"Explain {c['name']} in your own words" for c in chunk], 'concept_ids': [c['id'] for c in chunk],
                        'quiz_seed': {'node_ids': [r['node_id'] for i in items for r in i.get('node_refs', [])], 'concept_ids': [c['id'] for c in chunk], 'kind': 'foundations'},
                        'items': items})

    # ---- subsystem sections (dependency-ordered) --------------------------------------------------------
    subs = subsystems(rk, 8, per=5)
    if subs:
        subs = [s for s in subs if s['relevance'] >= SUBSYSTEM_FLOOR * subs[0]['relevance']]      # skip areas that barely matter for this role
    order_edges = []
    sub_by_id = {s['community']['id']: s for s in subs}
    for s in subs:
        deps_out = v.communities[s['community']['id']]['meta'].get('deps_out', {})
        for other in deps_out:
            if other in sub_by_id:
                order_edges.append((other, s['community']['id'], deps_out[other]))       # learn what others depend on first
    sub_order = topo_order([s['community']['id'] for s in subs], order_edges, {s['community']['id']: s['relevance'] for s in subs})
    sub_modules: list[dict[str, Any]] = []
    for cid in sub_order:
        s = sub_by_id[cid]
        comm = v.communities[cid]
        mid = ids.module()
        refs = [i['node_id'] for i in s['items']]
        walk = [n for n in refs if v.node(n)['kind'] == 'file'][:4]
        docs = [n for n in refs if v.node(n)['kind'] == 'doc'][:2]
        rel_docs = _related_docs(rk, walk) if not docs else docs
        items: list[dict[str, Any]] = []
        for group in (walk[:2], walk[2:4]):
            if group:
                items.append({'id': f'{mid}-i{len(items) + 1}', 'type': 'internal_walkthrough', 'title': 'Walk through ' + ', '.join(f"`{v.node(n)['name']}`" for n in group),
                              'minutes': _minutes_for_files(v, group), 'xp': XP['internal_walkthrough'], 'topic': comm['name'],
                              'repo_refs': [v.node(n)['path'] for n in group], 'node_refs': [_ref(rk, n) for n in group]})
        if rel_docs:
            items.append({'id': f'{mid}-i{len(items) + 1}', 'type': 'doc_reading', 'title': 'Read the related documentation', 'minutes': _minutes_for_files(v, rel_docs), 'xp': XP['doc_reading'],
                          'topic': comm['name'], 'repo_refs': [v.node(n)['path'] for n in rel_docs], 'node_refs': [_ref(rk, n) for n in rel_docs]})
        names = [v.node(n)['name'] for n in walk[:2]] or [comm['name']]
        items.append({'id': f'{mid}-i{len(items) + 1}', 'type': 'checkpoint', 'title': 'Checkpoint: explain the flow', 'minutes': 10, 'xp': XP['checkpoint'], 'topic': comm['name'],
                      'repo_refs': [v.node(n)['path'] for n in walk[:3]], 'node_refs': [_ref(rk, n) for n in walk[:3]],
                      'checkpoint_question': f"In your own words: what is the responsibility of `{comm['name']}`, and how do {' and '.join(f'`{n}`' for n in names)} fit into it? Name at least one thing it depends on."})
        items.append(_quiz_item(mid, q_count))
        sub_modules.append({'id': mid, 'title': f"Understand {comm['name']}", 'kind': 'subsystem', 'community_id': cid, 'relevance': s['relevance'],
                            'outcome': comm['summary'][:280], 'objectives': [f"Explain what `{comm['name']}` is responsible for", 'Trace a call through its key files'] + ([f"Explain how it relates to {', '.join(s['depends_on'][:2])}"] if s['depends_on'] else []),
                            'concept_ids': [], 'quiz_seed': {'node_ids': refs + [n for n in rel_docs], 'concept_ids': [], 'community_id': cid, 'kind': 'subsystem'}, 'items': items})

    # ---- first contribution + review quiz ------------------------------------------------------------------
    def total_minutes(mods: list[dict[str, Any]]) -> int:
        return sum(i['minutes'] for m in mods for i in m['items'])

    exercises = build_exercises(rk, profile)
    ex_minutes = sum(e['minutes'] for e in exercises)
    dropped: list[str] = []
    while len(sub_modules) > 1 and total_minutes(modules + sub_modules) + ex_minutes + 60 > budget:
        weakest = min(sub_modules, key=lambda m: m.get('relevance', 0))
        sub_modules.remove(weakest)
        dropped.append(weakest['title'].replace('Understand ', ''))
    fmid = ids.module()
    all_nodes = [n for m in modules + sub_modules for n in m['quiz_seed']['node_ids']]
    modules += sub_modules
    modules.append({'id': fmid, 'title': 'First contribution and review', 'kind': 'handson',
                    'outcome': f"You have a concrete plan for your first change: {profile['first_contribution']}", 'objectives': [profile['first_contribution']], 'concept_ids': [],
                    'quiz_seed': {'node_ids': all_nodes, 'concept_ids': [c for m in modules for c in m['concept_ids']], 'kind': 'review'},
                    'items': [{'id': f'{fmid}-i1', 'type': 'checkpoint', 'title': 'Checkpoint: plan your first contribution', 'minutes': 15, 'xp': XP['checkpoint'], 'topic': 'First contribution',
                               'repo_refs': [v.node(n)['path'] for n in _top_core(rk, 3)],
                               'node_refs': [_ref(rk, n) for n in _top_core(rk, 3)],
                               'checkpoint_question': f"Which files would you touch first, why, and how would you verify the change? ({profile['first_contribution']})"},
                              _quiz_item(fmid, q_count + 2)]})

    for module in modules:
        module['objectives'].append(emphasis)
        module['outcome'] += ' ' + emphasis
        module['minutes'] = sum(i.get('minutes',0) for i in module['items'])
        for item in module['items']:
            if item.get('type') == 'checkpoint':
                item['checkpoint_question'] += ' ' + emphasis
    for exercise in exercises:
        exercise['difficulty'] = {'junior':'beginner','mid':'intermediate','senior':'advanced'}[level]
        exercise['acceptance'].append(emphasis)
    est = total_minutes(modules) + ex_minutes
    coverage = _coverage(rk, modules, exercises)
    foundation_ids = [c for m in modules if m['kind'] == 'foundations' for c in m['concept_ids']]
    plan = {
        'summary': f"A {level} {profile['title']} roadmap built from this codebase's own knowledge graph: {len(modules)} sections, each ending in a quiz you must pass to unlock the next.",
        'meta': {'engine': 'graph', 'role_profile_id': profile['id'], 'role_title': profile['title'], 'role_confidence': rk.confidence, 'graph_build_id': v.build_id,
                 'quiz_pass_threshold': PASS_THRESHOLD, 'gating': True, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                 'budget_minutes': budget, 'estimated_minutes': est, 'dropped_sections': dropped, 'level': level, 'background': background[:500], 'scope': scope or [],
                 'signals': rk.signals, 'coverage': coverage, 'warnings': coverage.get('warnings', [])},
        'prerequisites': [{'concept': c['name'], 'concept_id': c['id'], 'priority': 'essential' if c['weight'] >= 0.8 else 'recommended', 'reason': c['why']} for c in concepts[:8]],
        'modules': modules, 'exercises': exercises,
        'resource_search_topics': catalog.public_search_topics(foundation_ids or [c['id'] for c in concepts], 12),
    }
    validate_plan(plan)
    plan['meta']['learning_emphasis'] = emphasis
    plan['meta']['mastered_concepts'] = sorted(known)
    plan['meta']['requires_review'] = bool(coverage.get('warnings'))
    return plan


def _coverage(rk: Ranking, modules: list[dict[str, Any]], exercises: list[dict[str, Any]], top_n: int = 20) -> dict[str, Any]:
    """How much of what matters for this role the roadmap actually points at (published with the plan so gaps are visible)."""
    v = rk.view
    refs = {r['node_id'] for m in modules for i in m['items'] for r in i.get('node_refs', [])} | {r['node_id'] for e in exercises for r in e.get('node_refs', [])}
    top = sorted((n for n in rk.scores if v.node(n)['kind'] == 'file' and v.node(n)['language'] and not v.node(n)['meta'].get('test')), key=lambda n: -rk.scores[n].rel)[:top_n]
    covered = len(set(top) & refs)
    with_ev = sum(1 for m in modules if any(i.get('node_refs') for i in m['items']))
    out: dict[str, Any] = {'sections': len(modules), 'sections_with_evidence': with_ev, 'top_files': len(top), 'top_files_covered': covered,
                           'ratio': round(covered / len(top), 3) if top else None, 'warnings': []}
    if top and covered / len(top) < 0.5:
        out['warnings'].append(f'Only {covered} of the {len(top)} most role-relevant files appear in this roadmap; review before sharing.')
    if len(top) < 3:
        out['warnings'].append('Very little role-relevant code was found in this workspace; the roadmap is mostly generic. Connect more repositories or documents.')
    return out


def _top_core(rk: Ranking, n: int) -> list[str]:
    from .pack import core_modules
    return core_modules(rk, n)


def _related_docs(rk: Ranking, files: list[str], limit: int = 2) -> list[str]:
    v = rk.view
    seen: dict[str, float] = {}
    for f in files:
        for other, etype, _w, fwd in v.neighbors(f, {'documents'}):
            if v.node(other)['kind'] == 'doc' and other in rk.scores:
                seen[other] = max(seen.get(other, 0.0), rk.scores[other].rel)
    return sorted(seen, key=lambda i: -seen[i])[:limit]


# ---------------------------------------------------------------------------------------------------------
def build_exercises(rk: Ranking, profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Exercises generated from the real graph (spec section 21): trace a call path, add a missing test, first contribution."""
    v = rk.view
    out: list[dict[str, Any]] = []
    # 1) trace a request/call path: follow `imports` from an entry file through the most relevant dependency at each hop
    entry = next((n for n in start_here(rk, 10) if v.node(n)['kind'] == 'file' and v.node(n)['language']), None)
    if entry is None:
        cands = [n for n in rk.scores if v.node(n)['kind'] == 'file' and v.node(n)['language'] and not v.node(n)['meta'].get('test')]
        entry = max(cands, key=lambda i: rk.scores[i].rel, default=None)
    if entry:
        chain, cur, seen = [entry], entry, {entry}
        for _ in range(3):
            nxt = [(other, rk.scores[other].rel) for other, etype, _w, fwd in v.neighbors(cur, {'imports'}) if fwd and other not in seen and other in rk.scores and not v.node(other)['meta'].get('test')]
            if not nxt:
                break
            cur = max(nxt, key=lambda x: x[1])[0]
            chain.append(cur)
            seen.add(cur)
        if len(chain) >= 2:
            out.append({'id': 'ex-trace', 'title': f"Trace the path from `{v.node(chain[0])['name']}` to `{v.node(chain[-1])['name']}`", 'difficulty': 'beginner', 'xp': XP['exercise'], 'minutes': 40,
                        'description': 'Follow the real dependency chain through the code and describe what each hop is responsible for. Do the work in your own editor; StudyBuddy will not edit your code.',
                        'acceptance': [f"Explain why `{v.node(a)['name']}` depends on `{v.node(b)['name']}`" for a, b in zip(chain, chain[1:])] + ['Name one failure mode at the deepest hop'],
                        'repo_refs': [v.node(n)['path'] for n in chain], 'node_refs': [_ref(rk, n) for n in chain]})
    # 2) add a missing test: a relevant, non-test file with functions and no incoming `tests` edge
    def untested(nid: str) -> bool:
        return not any(etype == 'tests' for _o, etype, _w, fwd in v.neighbors(nid, {'tests'}))
    cands = [n for n in rk.scores if v.node(n)['kind'] == 'file' and v.node(n)['language'] and not v.node(n)['meta'].get('test') and untested(n)
             and any(o[3] for o in v.neighbors(n, {'contains'}))]
    cands.sort(key=lambda i: -rk.scores[i].rel)
    for n in cands[:1]:
        syms = [o for o, et, _w, fwd in v.neighbors(n, {'contains'}) if fwd and v.node(o)['kind'] == 'symbol']
        def weight(sid: str) -> tuple[int, int]:
            kind_rank = 0 if v.node(sid)['meta'].get('symbol_kind') in {'function', 'method'} else 1     # behaviour beats bare data classes
            return (kind_rank, -sum(1 for o, et, _w, fwd in v.neighbors(sid, {'calls'}) if fwd))
        sym = sorted(syms, key=lambda s: (weight(s), v.node(s)['start_line'] or 0))[0] if syms else None
        target = v.node(sym)['name'] if sym else v.node(n)['name']
        out.append({'id': 'ex-test', 'title': f'Add a test for `{target}`', 'difficulty': 'beginner', 'xp': XP['exercise'], 'minutes': 45,
                    'description': f"`{v.node(n)['path']}` has no test coverage in the graph. Write a focused test for `{target}` following the conventions of the existing tests.",
                    'acceptance': ['The test fails when the behaviour is broken', 'It follows the repository test layout', 'It runs with the project test command'],
                    'repo_refs': [v.node(n)['path']], 'node_refs': [_ref(rk, n)] + ([_ref(rk, sym)] if sym else [])})
    out.append({'id': 'ex-first', 'title': 'Prepare your first contribution', 'difficulty': 'intermediate', 'xp': XP['exercise'] + 30, 'minutes': 60,
                'description': profile['first_contribution'], 'acceptance': ['Scope the change to specific files and symbols', 'Identify the tests that must pass', 'Describe how a reviewer can verify it'],
                'repo_refs': [v.node(n)['path'] for n in _top_core(rk, 3)], 'node_refs': [_ref(rk, n) for n in _top_core(rk, 3)]})
    return out


def validate_plan(plan: dict[str, Any]) -> None:
    """Hard structural guarantees; raises PlanError so a bad plan is never persisted."""
    ids: set[str] = set()
    if not plan.get('modules'):
        raise PlanError('plan has no modules')
    for m in plan['modules']:
        items = m.get('items') or []
        if not items or items[-1].get('type') != 'quiz' or items[-1].get('id') != f"{m['id']}-quiz":
            raise PlanError(f"module {m['id']} must end with a quiz item")
        if sum(1 for i in items if i.get('type') == 'quiz') != 1:
            raise PlanError(f"module {m['id']} must contain exactly one quiz")
        for i in items:
            if i['id'] in ids:
                raise PlanError(f"duplicate item id {i['id']}")
            ids.add(i['id'])
    for e in plan.get('exercises', []):
        if e['id'] in ids:
            raise PlanError(f"duplicate id {e['id']}")
        ids.add(e['id'])
