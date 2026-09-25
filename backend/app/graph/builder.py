"""Build / load the project knowledge graph from what the indexer already stored in PostgreSQL.

Nothing here re-reads repositories from disk or calls a model: the graph is derived from
indexed_documents / indexed_chunks / code_symbols / code_edges (+ kg_facts), so it works identically for
GitHub clones, uploads, Google Drive, web pages and VS Code-indexed files, and it is cheap to rebuild.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from ..db import db
from .algorithms import Graph
from .assemble import DocIn, GraphData, SecIn, SourceIn, SymIn, assemble
from .facts import extract_facts

_CACHE: dict[str, tuple[str, Graph]] = {}


def _load_inputs(conn, project_id: str) -> tuple[list[SourceIn], list[DocIn], list[SymIn], list[SecIn], list[tuple[str, str, str]]]:
    sources = [SourceIn(r['id'], r['kind'], r['name'], r['uri']) for r in conn.execute(
        'SELECT id,kind,name,uri FROM sources WHERE project_id=?', (project_id,)).fetchall()]
    facts_rows = {r['document_id']: (json.loads(r['facts_json'] or '{}'), bool(r['partial'])) for r in conn.execute(
        'SELECT document_id,facts_json,partial FROM kg_facts WHERE project_id=?', (project_id,)).fetchall()}
    size = {r['document_id']: (r['loc'] or 0, r['chars'] or 0) for r in conn.execute(
        'SELECT document_id, MAX(end_line) AS loc, SUM(length(content)) AS chars FROM indexed_chunks WHERE project_id=? GROUP BY document_id',
        (project_id,)).fetchall()}
    docs: list[DocIn] = []
    for r in conn.execute('SELECT id,source_id,source_type,source_name,source_uri,language FROM indexed_documents WHERE project_id=? ORDER BY source_name',
                          (project_id,)).fetchall():
        facts, partial = facts_rows.get(r['id'], (None, False))
        if facts is None:
            # Legacy document indexed before facts existed: derive from stored chunks (complete for docs and
            # Python; non-Python code may miss header imports, so it is flagged partial).
            text = '\n'.join(c['content'] for c in conn.execute(
                'SELECT content FROM indexed_chunks WHERE document_id=? ORDER BY ordinal', (r['id'],)).fetchall())
            facts = extract_facts(text, r['source_name'], r['language'])
            partial = bool(facts['imports']) and (r['language'] or '').lower() not in {'py', 'python'}
            conn.execute('INSERT INTO kg_facts(document_id,project_id,facts_json,partial) VALUES(?,?,?,?) ON CONFLICT(document_id) DO NOTHING',
                         (r['id'], project_id, json.dumps(facts), int(partial)))
        loc, chars = size.get(r['id'], (0, 0))
        docs.append(DocIn(r['id'], r['source_id'], r['source_type'], r['source_name'], r['source_uri'], r['language'], facts, int(loc), int(chars), partial))
    symbols = [SymIn(r['id'], r['document_id'], r['name'], r['qualified_name'], r['kind'], r['language'], r['start_line'], r['end_line'], r['signature'], r['docstring'])
               for r in conn.execute('SELECT id,document_id,name,qualified_name,kind,language,start_line,end_line,signature,docstring FROM code_symbols WHERE project_id=?',
                                     (project_id,)).fetchall()]
    sections: list[SecIn] = []          # sections are derived from parsed headings in assemble()
    calls = [(r['document_id'], r['source_symbol'], r['target_symbol']) for r in conn.execute(
        "SELECT document_id,source_symbol,target_symbol FROM code_edges WHERE project_id=? AND edge_type='calls' AND document_id IS NOT NULL",
        (project_id,)).fetchall()]
    return sources, docs, symbols, sections, calls


def _persist(conn, project_id: str, data: GraphData) -> None:
    conn.execute('DELETE FROM kg_edges WHERE project_id=?', (project_id,))
    conn.execute('DELETE FROM kg_nodes WHERE project_id=?', (project_id,))
    conn.execute('DELETE FROM kg_communities WHERE project_id=?', (project_id,))
    cid_by_index = {c.index: c.id for c in data.communities}
    conn.executemany(
        'INSERT INTO kg_communities(id,project_id,name,summary,size,keywords_json,metadata_json) VALUES(?,?,?,?,?,?,?)',
        [(c.id, project_id, c.name, c.summary, c.size, json.dumps(c.keywords), json.dumps(c.meta)) for c in data.communities])
    conn.executemany(
        'INSERT INTO kg_nodes(id,project_id,kind,key,name,path,document_id,chunk_id,start_line,end_line,language,summary,community_id,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        [(n.id, project_id, n.kind, n.key, n.name, n.path, n.document_id, n.chunk_id, n.start_line, n.end_line, n.language, n.summary,
          cid_by_index.get(n.community) if n.community is not None else None, json.dumps(n.meta)) for n in data.nodes.values()])
    conn.executemany(
        'INSERT INTO kg_edges(id,project_id,src,dst,type,weight,evidence_json) VALUES(?,?,?,?,?,?,?)',
        [(str(uuid.uuid5(uuid.NAMESPACE_URL, f'{project_id}|{s}|{d}|{t}')), project_id, s, d, t, e.weight, json.dumps(e.evidence))
         for (s, d, t), e in data.edges.items()])


def build_graph(project_id: str) -> dict[str, Any]:
    """Rebuild the project graph. Idempotent; concurrent builds for one project are serialised by an advisory lock."""
    started = time.perf_counter()
    build_id = str(uuid.uuid4())
    with db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(?))', (f'kg:{project_id}',))
        conn.execute("INSERT INTO kg_builds(id,project_id,status) VALUES(?,?,'running')", (build_id, project_id))
        try:
            data = assemble(project_id, *_load_inputs(conn, project_id))
            _persist(conn, project_id, data)
            stats = {**data.stats, 'communities': len(data.communities), 'seconds': round(time.perf_counter() - started, 2)}
            conn.execute("UPDATE kg_builds SET status='ready',stats_json=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(stats), build_id))
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f'graph build failed: {type(exc).__name__}: {exc}') from exc
    _CACHE.pop(project_id, None)
    return {'build_id': build_id, 'status': 'ready', **stats}


def latest_build(project_id: str) -> dict[str, Any] | None:
    with db() as conn:
        r = conn.execute("SELECT id,status,stats_json,error,started_at,finished_at FROM kg_builds WHERE project_id=? AND status='ready' ORDER BY started_at DESC LIMIT 1",
                         (project_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d['stats'] = json.loads(d.pop('stats_json') or '{}')
    return d


def graph_status(project_id: str) -> dict[str, Any]:
    build = latest_build(project_id)
    with db() as conn:
        docs = conn.execute('SELECT COUNT(*) FROM indexed_documents WHERE project_id=?', (project_id,)).fetchone()[0]
        newest = conn.execute('SELECT MAX(indexed_at) FROM indexed_documents WHERE project_id=?', (project_id,)).fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM kg_builds WHERE project_id=? AND status='running' AND started_at > now() - interval '15 minutes'", (project_id,)).fetchone()[0]
    stale = bool(build and newest and build['finished_at'] and newest > build['finished_at'])
    return {'ready': build is not None, 'stale': stale or (build is None and docs > 0), 'building': bool(running), 'documents': docs, 'build': build}


def load_graph(project_id: str) -> Graph | None:
    """In-memory graph for the latest build (cached per build id)."""
    build = latest_build(project_id)
    if not build:
        return None
    hit = _CACHE.get(project_id)
    if hit and hit[0] == build['id']:
        return hit[1]
    with db() as conn:
        nodes = [(r['id'], r['kind']) for r in conn.execute('SELECT id,kind FROM kg_nodes WHERE project_id=? ORDER BY id', (project_id,)).fetchall()]
        edges = [(r['src'], r['dst'], r['type'], r['weight']) for r in conn.execute('SELECT src,dst,type,weight FROM kg_edges WHERE project_id=?', (project_id,)).fetchall()]
    g = Graph.build(nodes, edges)
    _CACHE[project_id] = (build['id'], g)
    return g


def fetch_nodes(project_id: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    with db() as conn:
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            marks = ','.join('?' * len(part))
            for r in conn.execute(f'SELECT * FROM kg_nodes WHERE project_id=? AND id IN ({marks})', (project_id, *part)).fetchall():
                d = dict(r)
                d['meta'] = json.loads(d.pop('metadata_json') or '{}')
                out[d['id']] = d
    return out


def list_communities(project_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute('SELECT * FROM kg_communities WHERE project_id=? ORDER BY size DESC,name', (project_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d['keywords'] = json.loads(d.pop('keywords_json') or '[]')
        d['meta'] = json.loads(d.pop('metadata_json') or '{}')
        out.append(d)
    return out
