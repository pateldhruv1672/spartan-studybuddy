"""Read-optimised, per-build cached view of a project graph (nodes + communities + lookups)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..db import db
from .algorithms import Graph
from .builder import latest_build, load_graph


class GraphNotBuilt(RuntimeError):
    pass


@dataclass
class View:
    project_id: str
    build_id: str
    graph: Graph
    nodes: dict[str, dict[str, Any]]
    communities: dict[str, dict[str, Any]]
    by_kind: dict[str, list[str]] = field(default_factory=dict)
    doc_node: dict[str, str] = field(default_factory=dict)                   # document_id -> file/doc node id
    sym_by_doc_name: dict[tuple[str, str], str] = field(default_factory=dict)
    by_name: dict[str, list[str]] = field(default_factory=dict)              # lower(name) -> node ids

    def node(self, nid: str) -> dict[str, Any]:
        return self.nodes[nid]

    def neighbors(self, nid: str, types: set[str] | None = None):
        return self.graph.neighbors(nid, types)


_VIEWS: dict[str, View] = {}


def load_view(project_id: str) -> View | None:
    build = latest_build(project_id)
    if not build:
        return None
    hit = _VIEWS.get(project_id)
    if hit and hit.build_id == build['id']:
        return hit
    g = load_graph(project_id)
    if g is None:
        return None
    with db() as conn:
        rows = conn.execute('SELECT id,kind,key,name,path,document_id,chunk_id,start_line,end_line,language,summary,community_id,metadata_json FROM kg_nodes WHERE project_id=?',
                            (project_id,)).fetchall()
        crows = conn.execute('SELECT * FROM kg_communities WHERE project_id=?', (project_id,)).fetchall()
    nodes: dict[str, dict[str, Any]] = {}
    v = View(project_id, build['id'], g, nodes, {})
    for r in rows:
        d = dict(r)
        d['meta'] = json.loads(d.pop('metadata_json') or '{}')
        nodes[d['id']] = d
        v.by_kind.setdefault(d['kind'], []).append(d['id'])
        v.by_name.setdefault(d['name'].lower(), []).append(d['id'])
        if d['kind'] in {'file', 'doc'} and d['document_id']:
            v.doc_node[d['document_id']] = d['id']
    for d in nodes.values():
        if d['kind'] == 'symbol' and d['document_id']:
            v.sym_by_doc_name[(d['document_id'], d['name'])] = d['id']
            short = d['name'].split('.')[-1]
            v.sym_by_doc_name.setdefault((d['document_id'], short), d['id'])
    for r in crows:
        c = dict(r)
        c['keywords'] = json.loads(c.pop('keywords_json') or '[]')
        c['meta'] = json.loads(c.pop('metadata_json') or '{}')
        v.communities[c['id']] = c
    _VIEWS[project_id] = v
    return v


def require_view(project_id: str) -> View:
    v = load_view(project_id)
    if v is None:
        raise GraphNotBuilt('graph not built')
    return v


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**` spans directories, `*` stays within one path segment; patterns without '/' match the basename."""
    p = pattern.strip()
    anchored = '/' in p
    out, i = '', 0
    while i < len(p):
        c = p[i]
        if p.startswith('**/', i):
            out += '(?:.*/)?'
            i += 3
        elif p.startswith('**', i):
            out += '.*'
            i += 2
        elif c == '*':
            out += '[^/]*'
            i += 1
        elif c == '?':
            out += '[^/]'
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(('^' if anchored else '(?:^|.*/)') + out + '$', re.I)


def matches_any(path: str, patterns: list[re.Pattern[str]]) -> int | None:
    for i, p in enumerate(patterns):
        if p.match(path):
            return i
    return None
