"""Question generators for section quizzes (pure of persistence; read the graph view, return QSpec lists).

Two sources, both grounded:
  * graph      – facts read off the code graph (who defines X, what does f call, what imports Y, dependency order ...);
                 every question carries evidence (file:line) and distractors are *verified* not to be true.
  * catalog    – curated concept questions for the generic prerequisite ("foundations") sections.
Optionally an LLM adds questions from retrieved evidence; each is accepted only if an independent verification
pass re-derives the same answer from the evidence alone (see `llm_extra_questions`).
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any

from . import catalog
from .view import View

CATEGORY_LABEL = {
    'web-framework': 'serving HTTP / building the API', 'orm-db': 'talking to the database', 'database': 'data storage', 'cache': 'caching',
    'queue-stream': 'messaging / background work', 'auth-security': 'authentication or security', 'http-client': 'making HTTP requests',
    'testing': 'testing', 'frontend-framework': 'the user interface', 'css-ui': 'styling', 'build-tool': 'building the frontend',
    'data-processing': 'data processing', 'orchestration': 'orchestrating pipelines', 'ml-framework': 'machine learning',
    'llm-tooling': 'working with language models', 'observability': 'observability', 'container': 'containers', 'cloud': 'cloud services', 'iac': 'infrastructure as code',
    'ci-cd': 'CI/CD', 'container-orchestration': 'running containers at scale', 'vector-store': 'vector search', 'experiment-tracking': 'tracking experiments', 'visualization': 'charts and dashboards',
}


@dataclass
class QSpec:
    qtype: str                                   # mcq | multi | order | short
    prompt: str
    choices: list[dict[str, str]] = field(default_factory=list)
    answer: Any = None                           # list[str] of choice ids, or {'keywords': [...], 'min_ratio': x} for short
    explanation: str = ''
    evidence: list[dict[str, Any]] = field(default_factory=list)
    concept: str | None = None
    difficulty: int = 1
    source: str = 'graph'
    weight: float = 1.0
    gen: str = ''


def rng_for(seed: str) -> random.Random:
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))


def _cite(n: dict[str, Any]) -> dict[str, Any]:
    path = n.get('path') or n['name']
    a, b = n.get('start_line'), n.get('end_line')
    return {'citation': f'{path}:{a}-{b}' if a else path, 'path': n.get('path'), 'start_line': a, 'end_line': b}


def _choices(rng: random.Random, correct: list[str], distractors: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    texts = list(dict.fromkeys(correct + distractors))
    rng.shuffle(texts)
    cs = [{'id': f'c{i}', 'text': t} for i, t in enumerate(texts)]
    ids = [c['id'] for c in cs if c['text'] in correct]
    return cs, ids


class Ctx:
    """Everything a generator needs for one section."""

    def __init__(self, v: View, seed: str, node_ids: list[str], community_id: str | None, concept_ids: list[str], kind: str, doc_text):
        self.v, self.rng, self.kind, self.concept_ids = v, rng_for(seed), kind, concept_ids
        self.doc_text = doc_text                                     # callable(document_id) -> str
        pool = list(dict.fromkeys(node_ids))
        if community_id:
            pool += [i for i in v.nodes if v.nodes[i]['community_id'] == community_id and v.nodes[i]['kind'] in {'file', 'doc'}][:60]
        self.pool = list(dict.fromkeys(pool))
        self.files = [i for i in self.pool if v.node(i)['kind'] == 'file' and v.node(i)['language'] and not v.node(i)['meta'].get('test')]
        self.docs = [i for i in self.pool if v.node(i)['kind'] == 'doc']
        self.all_files = [i for i in v.by_kind.get('file', []) if v.node(i)['language'] and not v.node(i)['meta'].get('test')]
        self.symbols: list[str] = []
        self.set_files(self.files)

    def set_files(self, files: list[str]) -> None:
        """Change the focus files and recompute the symbols defined in them."""
        self.files = list(dict.fromkeys(files))
        self.symbols = [o for f in self.files for o, et, _w, fwd in self.v.neighbors(f, {'contains'}) if fwd and self.v.node(o)['kind'] == 'symbol']

    def sample(self, xs: list[str], k: int) -> list[str]:
        xs = list(xs)
        self.rng.shuffle(xs)
        return xs[:k]


def _stem(path: str) -> str:
    return path.rsplit('/', 1)[-1].rsplit('.', 1)[0]


# ---------- graph generators ------------------------------------------------------------------------------
def gen_locate(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    for sid in c.sample([s for s in c.symbols if '.' not in v.node(s)['name'] and v.node(s)['meta'].get('symbol_kind') in {'class', 'function'}], 8):
        n = v.node(sid)
        others = [v.node(f)['path'] for f in c.sample(c.all_files, 12) if v.node(f)['path'] != n['path']
                  and not any(v.node(x)['name'] == n['name'] and v.node(x)['document_id'] == v.node(f)['document_id'] for x in v.by_name.get(n['name'].lower(), []))]
        if len(others) < 3:
            continue
        cs, ans = _choices(c.rng, [n['path']], others[:3])
        out.append(QSpec('mcq', f"Which file defines `{n['name']}`?", cs, ans, f"`{n['name']}` is defined in `{n['path']}` (lines {n['start_line']}–{n['end_line']}).",
                         [_cite(n)], None, 1, 'graph', 1.0, 'locate'))
    return out


def _callees(v: View, sid: str) -> list[str]:
    return [o for o, et, _w, fwd in v.neighbors(sid, {'calls'}) if fwd and v.node(o)['kind'] == 'symbol']


def gen_calls(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    for sid in c.sample([s for s in c.symbols if _callees(v, s)], 10):
        n = v.node(sid)
        callees = _callees(v, sid)
        callee_names = {v.node(x)['name'].split('.')[-1] for x in callees}
        text = c.doc_text(n['document_id']) or ''
        same_pool = [s for s in c.symbols if s != sid and v.node(s)['name'].split('.')[-1] not in callee_names]
        distract = []
        for s in c.sample(same_pool, 10):
            short = v.node(s)['name'].split('.')[-1]
            if short not in text and short != n['name'].split('.')[-1]:
                distract.append(v.node(s)['name'])
        correct = v.node(c.rng.choice(callees))
        if len(set(distract)) < 3 or correct['name'] in distract:
            continue
        cs, ans = _choices(c.rng, [correct['name']], list(dict.fromkeys(distract))[:3])
        out.append(QSpec('mcq', f"Which of these does `{n['name']}` call directly?", cs, ans,
                         f"`{n['name']}` (`{n['path']}:{n['start_line']}`) calls `{correct['name']}` defined in `{correct['path']}`.", [_cite(n), _cite(correct)], None, 2, 'graph', 1.0, 'calls'))
    return out


def _imports(v: View, fid: str) -> list[str]:
    return [o for o, et, _w, fwd in v.neighbors(fid, {'imports'}) if fwd and v.node(o)['kind'] == 'file']


def _importers(v: View, fid: str) -> list[str]:
    return [o for o, et, _w, fwd in v.neighbors(fid, {'imports'}) if not fwd and v.node(o)['kind'] == 'file']


def gen_imports(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    for fid in c.sample([f for f in c.files if _imports(v, f)], 8):
        n = v.node(fid)
        imported = _imports(v, fid)
        text = (c.doc_text(n['document_id']) or '')
        distract = [v.node(o)['path'] for o in c.sample(c.all_files, 14) if o not in imported and o != fid and _stem(v.node(o)['path']) not in text]
        if len(distract) < 3:
            continue
        correct = v.node(c.rng.choice(imported))
        cs, ans = _choices(c.rng, [correct['path']], distract[:3])
        out.append(QSpec('mcq', f"Which of these project files does `{n['path']}` import?", cs, ans,
                         f"`{n['path']}` imports `{correct['path']}` — this dependency is why changes there can affect it.", [_cite(n), _cite(correct)], None, 2, 'graph', 1.0, 'imports'))
    return out


def gen_dependants(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    for fid in c.sample([f for f in c.files if _importers(v, f)], 8):
        n = v.node(fid)
        users = _importers(v, fid)
        distract = []
        for o in c.sample(c.all_files, 14):
            if o in users or o == fid:
                continue
            if _stem(n['path']) not in (c.doc_text(v.node(o)['document_id']) or ''):
                distract.append(v.node(o)['path'])
        if len(distract) < 3:
            continue
        correct = v.node(c.rng.choice(users))
        cs, ans = _choices(c.rng, [correct['path']], distract[:3])
        out.append(QSpec('mcq', f"Which file depends on (imports) `{n['path']}`?", cs, ans,
                         f"`{correct['path']}` imports `{n['path']}`; it is a dependant, so behaviour changes in `{n['path']}` ripple into it.", [_cite(correct), _cite(n)], None, 2, 'graph', 1.0, 'dependants'))
    return out


def _chain(c: Ctx, edge: str, start_pool: list[str], length: int = 3) -> list[str] | None:
    """Follow `edge` from a start node, always taking the alphabetically first unseen successor (deterministic)."""
    v = c.v
    for start in c.sample(start_pool, 12):
        chain, seen = [start], {start}
        while len(chain) < length + 1:
            nxt = [o for o, et, _w, fwd in v.neighbors(chain[-1], {edge}) if fwd and o not in seen and v.node(o)['kind'] in {'file', 'symbol'}]
            if not nxt:
                break
            chain.append(sorted(nxt, key=lambda x: v.node(x)['name'])[0])
            seen.add(chain[-1])
        if len(chain) >= length:
            return chain
    return None


def gen_order(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    for edge, pool, label in (('imports', c.files, 'files'), ('calls', c.symbols, 'functions')):
        chain = _chain(c, edge, pool, 3)
        if not chain or len(chain) < 3:
            continue
        names = [v.node(x)['path'] if edge == 'imports' else v.node(x)['name'] for x in chain]
        if len(set(names)) != len(names):
            continue
        shuffled = list(names)
        c.rng.shuffle(shuffled)
        if shuffled == names:
            shuffled.reverse()
        cs = [{'id': f'c{i}', 'text': t} for i, t in enumerate(shuffled)]
        ans = [next(x['id'] for x in cs if x['text'] == t) for t in names]
        verb = 'imports' if edge == 'imports' else 'calls'
        out.append(QSpec('order', f"Put these {label} in order, from the outermost caller to the deepest dependency (each one {verb} the next).", cs, ans,
                         ' → '.join(names), [_cite(v.node(x)) for x in chain], None, 3, 'graph', 1.0, 'order'))
    return out


def gen_tech(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    techs_all = catalog.techs()
    for fid in c.sample(c.files, 12):
        n = v.node(fid)
        used = [(o, v.node(o)) for o, et, _w, fwd in v.neighbors(fid, {'uses', 'depends_on'}) if fwd and v.node(o)['kind'] == 'tech' and v.node(o)['meta'].get('public')]
        used = [(o, t) for o, t in used if t['meta'].get('category') in CATEGORY_LABEL]
        if not used:
            continue
        oid, t = c.rng.choice(used)
        cat = t['meta']['category']
        used_names = {x[1]['name'] for x in used}
        distract = [x['name'] for x in techs_all.values() if x['category'] == cat and x['name'] != t['name'] and x['name'] not in used_names]
        if len(distract) < 3:
            distract += [x['name'] for x in techs_all.values() if x['category'] != cat and x['name'] not in used_names]
        distract = c.sample(distract, 3)
        if len(distract) < 3:
            continue
        cs, ans = _choices(c.rng, [t['name']], distract)
        out.append(QSpec('mcq', f"Which technology does `{n['path']}` use for {CATEGORY_LABEL[cat]}?", cs, ans,
                         f"`{n['path']}` uses {t['name']} for {CATEGORY_LABEL[cat]}.", [_cite(n)],
                         (t['meta'].get('concepts') or [None])[0], 1, 'graph', 1.0, 'tech'))
    return out


def gen_test_of(c: Ctx) -> list[QSpec]:
    v, out = c.v, []
    tests_all = [i for i in v.by_kind.get('file', []) if v.node(i)['meta'].get('test')]
    for fid in c.sample(c.files, 10):
        ts = [o for o, et, _w, fwd in v.neighbors(fid, {'tests'}) if not fwd]
        if not ts:
            continue
        correct = v.node(ts[0])
        distract = [v.node(o)['path'] for o in tests_all if o not in ts]
        distract += [v.node(o)['path'] for o in c.sample(c.all_files, 6) if o != fid]
        distract = list(dict.fromkeys(distract))[:3]
        if len(distract) < 3:
            continue
        n = v.node(fid)
        cs, ans = _choices(c.rng, [correct['path']], distract)
        out.append(QSpec('mcq', f"Which file contains the tests for `{n['path']}`?", cs, ans, f"`{correct['path']}` imports and exercises `{n['path']}`.",
                         [_cite(correct), _cite(n)], 'testing-fundamentals', 1, 'graph', 1.0, 'test_of'))
    return out


def gen_reflection(c: Ctx, title: str, extra_keywords: list[str] | None = None) -> list[QSpec]:
    v = c.v
    kws = list(extra_keywords or [])
    for f in c.files[:5]:
        kws.append(_stem(v.node(f)['path']))
        for o, et, _w, fwd in v.neighbors(f, {'uses'}):
            if fwd and v.node(o)['kind'] == 'tech' and v.node(o)['meta'].get('public'):
                kws.append(v.node(o)['name'])
    kws = [k for k in dict.fromkeys(k.lower() for k in kws if k and len(k) >= 3)][:10]
    if len(kws) < 3:
        return []
    ev = [_cite(v.node(f)) for f in c.files[:3]]
    return [QSpec('short', f"In two or three sentences: what is the responsibility of “{title}”, and which files or technologies does it rely on?", [], {'keywords': kws, 'min_ratio': 0.35},
                  'A good answer names the section\'s main files and the technologies or modules it depends on. Key terms we looked for: ' + ', '.join(kws[:6]) + '.',
                  ev, None, 2, 'graph', 0.5, 'reflection')]


# ---------- catalog generator ----------------------------------------------------------------------------
def gen_concepts(c: Ctx, per_concept: int = 2) -> list[QSpec]:
    cs_all = catalog.concepts()
    out = []
    for cid in c.concept_ids:
        concept = cs_all.get(cid)
        if not concept:
            continue
        for q in concept.get('questions', [])[:per_concept]:
            correct = q['choices'][q['answer']]
            others = [t for i, t in enumerate(q['choices']) if i != q['answer']]
            choices, ans = _choices(c.rng, [correct], others)
            out.append(QSpec('mcq', q['q'], choices, ans, q['why'], [{'citation':f"concept-catalog:{cid}"}], cid, concept['difficulty'], 'catalog', 1.0, 'concept'))
    return out


# ---------- selection --------------------------------------------------------------------------------------
def select_bank(candidates: list[QSpec], size: int, rng: random.Random, max_per_gen: int = 3) -> list[QSpec]:
    """Round-robin over generators, easier first inside each, dedupe by prompt; bank is ~2x the per-attempt draw."""
    by_gen: dict[str, list[QSpec]] = {}
    for q in candidates:
        by_gen.setdefault(q.gen, []).append(q)
    for lst in by_gen.values():
        lst.sort(key=lambda q: (q.difficulty, q.prompt))
    keys = sorted(by_gen)
    rng.shuffle(keys)
    out: list[QSpec] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}
    while len(out) < size:
        progress = False
        for g in keys:
            if len(out) >= size:
                break
            lst = by_gen[g]
            while lst and lst[0].prompt in seen:
                lst.pop(0)
            if not lst or (counts.get(g, 0) >= max_per_gen and g != 'concept'):
                continue
            q = lst.pop(0)
            out.append(q)
            seen.add(q.prompt)
            counts[g] = counts.get(g, 0) + 1
            progress = True
        if not progress:
            break
    return out
