"""Graph-augmented retrieval (GraphRAG) layered on the existing hybrid retriever.

Pipeline (spec section 9 stays intact: hybrid sparse+dense -> RRF -> optional rerank -> citations):

  1. hybrid candidates (tsvector/GIN + pgvector/HNSW, fused with RRF)      <- unchanged, done by the caller
  2. map candidate chunks to graph nodes; link identifiers in the query to nodes (entity linking)
  3. spread relevance through typed edges (imports/calls/tests/documents) with personalised PageRank
  4. pull in the best *neighbour* chunks that lexical/dense search missed, remember WHY (`via`)
  5. fuse base rank and graph rank with RRF; add community summaries for overview questions
  6. emit structure facts ("A imports B", "doc D documents X") with file:line evidence

If no graph exists the caller falls back to the previous symbol-LIKE expansion, so this is purely additive.
"""
from __future__ import annotations

import re
from typing import Any

from ..db import db
from .algorithms import personalized_pagerank
from .view import View, load_view

OVERVIEW = re.compile(r'\b(architecture|overview|big picture|high[- ]level|how is .* (organi[sz]ed|structured)|what does (this|the) (repo|repository|project|system|codebase)|main components|subsystems?|onboard)', re.I)
IDENT = re.compile(r'[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+|[A-Za-z_][\w]{3,}|[\w./-]+\.[A-Za-z0-9]{1,5}')
STOP = {'what', 'does', 'this', 'that', 'with', 'from', 'where', 'which', 'when', 'about', 'function', 'class', 'method', 'code', 'file', 'work', 'works', 'used', 'have', 'into', 'there', 'their', 'how', 'the', 'and'}
EXPAND_MAX = 6
EDGE_TYPES = {'imports', 'calls', 'tests', 'documents'}


def _chunk_node(v: View, cand: dict[str, Any]) -> str | None:
    doc_id = str(cand.get('id', '')).rsplit(':', 1)[0]
    sym = cand.get('symbol')
    if sym:
        nid = v.sym_by_doc_name.get((doc_id, sym)) or v.sym_by_doc_name.get((doc_id, str(sym).split('.')[-1]))
        if nid:
            return nid
    return v.doc_node.get(doc_id)


def link_entities(v: View, query: str, limit: int = 8) -> list[str]:
    """Identifiers/paths in the query -> graph nodes (exact, case-insensitive; ambiguous names are skipped)."""
    out: list[str] = []
    for tok in IDENT.findall(query):
        low = tok.lower().strip('.')
        if low in STOP or len(low) < 4:
            continue
        for key in {low, low.split('.')[-1]}:
            ids = [i for i in v.by_name.get(key, []) if v.node(i)['kind'] in {'symbol', 'file', 'doc'}]
            if not ids and '/' in low:
                ids = [i for i in v.by_kind.get('file', []) + v.by_kind.get('doc', []) if (v.node(i)['path'] or '').lower().endswith(low)]
            if 0 < len(ids) <= 3:
                out.extend(ids)
                break
    return list(dict.fromkeys(out))[:limit]


def _fetch_chunk(node: dict[str, Any]) -> dict[str, Any] | None:
    with db() as conn:
        if node['kind'] == 'symbol':
            short = node['name'].split('.')[0]          # class chunk carries its methods
            row = conn.execute('''SELECT c.id,c.content,c.kind,c.symbol,c.start_line,c.end_line,c.topic,d.source_name,d.source_uri,d.language
                                  FROM indexed_chunks c JOIN indexed_documents d ON d.id=c.document_id
                                  WHERE c.document_id=? AND c.symbol=? ORDER BY c.ordinal LIMIT 1''', (node['document_id'], short)).fetchone()
        else:
            row = conn.execute('''SELECT c.id,c.content,c.kind,c.symbol,c.start_line,c.end_line,c.topic,d.source_name,d.source_uri,d.language
                                  FROM indexed_chunks c JOIN indexed_documents d ON d.id=c.document_id
                                  WHERE c.document_id=? ORDER BY c.ordinal LIMIT 1''', (node['document_id'],)).fetchone()
    return dict(row) if row else None


def expand(project_id: str, query: str, candidates: list[dict[str, Any]], max_extra: int = EXPAND_MAX) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (candidates + graph neighbours, debug info). Candidate dicts are the hybrid-search rows."""
    v = load_view(project_id)
    info: dict[str, Any] = {'graph': False}
    if v is None or v.graph.n == 0:
        return candidates, info
    info['graph'] = True
    seeds: dict[str, float] = {}
    cand_node: dict[str, str] = {}
    for rank, c in enumerate(candidates, 1):
        nid = _chunk_node(v, c)
        if nid:
            cand_node[c['id']] = nid
            seeds[nid] = seeds.get(nid, 0.0) + 1.0 / (10 + rank)
    entities = link_entities(v, query)
    for nid in entities:
        seeds[nid] = seeds.get(nid, 0.0) + 0.25
    info.update({'seeds': len(seeds), 'entities': len(entities)})
    if not seeds:
        return candidates, info
    p = personalized_pagerank(v.graph, seeds, alpha=0.3, iters=30)
    have = {n for n in cand_node.values()}
    # graph rank over code/doc nodes
    ranked = sorted((i for i in range(v.graph.n) if v.graph.kinds[i] in {'symbol', 'file', 'doc', 'section'} and p[i] > 0), key=lambda i: -p[i])
    extras: list[dict[str, Any]] = []
    for i in ranked:
        nid = v.graph.ids[i]
        if nid in have or v.node(nid)['kind'] == 'section':
            continue
        n = v.node(nid)
        if not n['document_id']:
            continue
        if n['kind'] in {'file', 'doc'} and any(v.node(x)['document_id'] == n['document_id'] and v.node(x)['kind'] == 'symbol' for x in have):
            continue
        via = []
        for other, etype, _w, fwd in v.neighbors(nid, EDGE_TYPES):
            if other in seeds:
                via.append({'type': etype, 'from': v.node(other)['name'], 'direction': 'out' if fwd else 'in'})
        if not via and nid not in entities:
            continue                                   # only keep neighbours with a concrete explanation
        row = _fetch_chunk(n)
        if not row or any(row['id'] == c['id'] for c in candidates):
            continue
        row.update({'graph_score': float(p[i]), 'via': via[:3] or [{'type': 'entity', 'from': n['name'], 'direction': 'self'}]})
        extras.append(row)
        have.add(nid)
        if len(extras) >= max_extra:
            break
    # fuse: base RRF rank + graph rank
    graph_rank = {nid: r for r, nid in enumerate(sorted(seeds, key=lambda x: -p[v.graph.index[x]]), 1) if nid in v.graph.index}
    for rank, c in enumerate(candidates, 1):
        nid = cand_node.get(c['id'])
        gr = graph_rank.get(nid, len(graph_rank) + 20) if nid else len(graph_rank) + 20
        c['rrf'] = c.get('rrf', 0.0) + 0.8 / (60 + gr)
    for k, row in enumerate(extras, 1):
        row['rrf'] = 0.9 / (60 + len(candidates) + k) + 0.8 / (60 + k)
        row.setdefault('kind', 'code')
    merged = sorted(candidates + extras, key=lambda x: -x.get('rrf', 0.0))
    info['expanded'] = len(extras)
    return merged, info


def community_items(project_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
    """For overview questions ("how is this repo organised?"), community summaries answer better than any single chunk."""
    v = load_view(project_id)
    if v is None or not OVERVIEW.search(query):
        return []
    words = {w for w in re.findall(r'[a-z]{4,}', query.lower()) if w not in STOP}
    comms = sorted(v.communities.values(), key=lambda c: (-sum(1 for w in words if w in (c['name'] + ' ' + c['summary']).lower()), -c['size']))[:limit]
    return [{'id': f"community:{c['id']}", 'kind': 'community', 'content': f"Subsystem `{c['name']}`: {c['summary']}", 'source_name': f"community:{c['name']}",
             'symbol': None, 'start_line': None, 'end_line': None, 'citation': f"community:{c['name']}", 'rrf': 0.02} for c in comms]


def structure_facts(project_id: str, items: list[dict[str, Any]], limit: int = 14) -> list[str]:
    """Verifiable relations between the retrieved evidence, each with a file:line anchor."""
    v = load_view(project_id)
    if v is None:
        return []
    facts: list[str] = []
    seen: set[str] = set()
    nodes = [nid for nid in (_chunk_node(v, c) for c in items if not str(c.get('id', '')).startswith('community:')) if nid]
    for nid in nodes:
        n = v.node(nid)
        loc = f"{n['path']}:{n['start_line']}" if n['start_line'] else (n['path'] or n['name'])
        for other, etype, _w, fwd in v.neighbors(nid, EDGE_TYPES):
            o = v.node(other)
            oloc = o['path'] or o['name']
            if etype == 'imports' and fwd:
                f = f"{n['path'] or n['name']} imports {oloc}"
            elif etype == 'calls' and fwd:
                f = f"{n['name']} ({loc}) calls {o['name']} ({o['path']}:{o['start_line'] or '?'})"
            elif etype == 'tests' and not fwd:
                f = f"{oloc} tests {n['path'] or n['name']}"
            elif etype == 'documents':
                f = f"{oloc} documents {n['name']}" if not fwd else f"{n['path'] or n['name']} documents {o['name']}"
            else:
                continue
            if f not in seen:
                seen.add(f)
                facts.append(f)
            if len(facts) >= limit:
                return facts
    return facts


def graph_search(project_id: str, query: str, top_k: int = 10, role: str | None = None) -> dict[str, Any]:
    """Endpoint helper: hybrid search + graph expansion + structure facts + community context."""
    from ..services.indexer import _fts, hybrid_search
    try:
        base = hybrid_search(project_id, query, max(top_k, 8))
        dense = True
    except Exception:
        base = _fts(project_id, query, max(top_k, 8))
        for i, r in enumerate(base, 1):
            r['rrf'] = 1.0 / (60 + i)
        dense = False
    merged, info = expand(project_id, query, base)
    merged = merged[:top_k]
    for i, r in enumerate(merged, 1):
        line = f"{r.get('start_line') or '?'}-{r.get('end_line') or '?'}"
        r['citation'] = f"[{i}] {r.get('source_name')}:{line}"
        r['preview'] = (r.get('content') or '')[:700]
    comms = community_items(project_id, query)
    v = load_view(project_id)
    cids = [c['id'].split(':', 1)[1] for c in comms]
    full = [{k: v.communities[i].get(k) for k in ('id', 'name', 'summary', 'size', 'keywords', 'summary_source', 'meta')} for i in cids if v and i in v.communities]
    return {'results': merged, 'structure': structure_facts(project_id, merged), 'communities': full,
            'debug': {**info, 'dense': dense, 'graph_build': v.build_id if v else None}}
