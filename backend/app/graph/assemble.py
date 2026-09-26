"""Pure graph assembly: indexed-project facts in, nodes/edges/communities out (no database access).

Node kinds : repo, dir, file, doc, section, symbol, tech, concept, link
Edge types : contains, imports, tests, calls, documents, mentions, links_to, depends_on, uses, teaches, prerequisite_of

Ids are deterministic (uuid5 over project|kind|key) so rebuilding keeps ids stable for unchanged entities.
"""
from __future__ import annotations

import posixpath
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from . import catalog
from .algorithms import label_propagation, modularity
from .facts import CONFIG_EXTS, is_entry_path, is_test_path, language_of
from .resolve import FileRef, ImportResolver

STRUCTURED_SOURCES = {'repository_code', 'vscode_code'}
CONFIG_BASENAMES = {'makefile', 'dockerfile', 'gemfile', 'procfile', 'jenkinsfile', '.gitignore', '.env.example'}
COMMON_CALLS = {
    'get', 'set', 'add', 'append', 'extend', 'update', 'items', 'keys', 'values', 'join', 'split', 'strip', 'lower', 'upper',
    'format', 'print', 'len', 'str', 'int', 'float', 'list', 'dict', 'tuple', 'isinstance', 'open', 'read', 'write', 'close',
    'run', 'main', 'init', 'pop', 'remove', 'sorted', 'sum', 'min', 'max', 'range', 'enumerate', 'zip', 'map', 'filter',
    'execute', 'commit', 'rollback', 'fetchone', 'fetchall', 'encode', 'decode', 'dumps', 'loads', 'json', 'info', 'debug',
    'error', 'warning', 'send', 'start', 'stop', 'copy', 'replace', 'startswith', 'endswith', 'exists', 'mkdir', 'sleep',
}
SOURCE_LABEL = {'vscode_code': 'VS Code workspace', 'upload': 'Uploaded files', 'web': 'Web pages', 'gdrive': 'Google Drive', 'documentation': 'Documentation'}


@dataclass
class DocIn:
    id: str
    source_id: str | None
    source_type: str
    source_name: str
    source_uri: str | None
    language: str | None
    facts: dict[str, Any]
    loc: int = 0
    chars: int = 0
    partial: bool = False


@dataclass
class SymIn:
    id: str
    document_id: str
    name: str
    qualified_name: str | None
    kind: str | None
    language: str | None
    start_line: int | None
    end_line: int | None
    signature: str | None = None
    docstring: str | None = None


@dataclass
class SecIn:
    chunk_id: str
    document_id: str
    name: str
    start_line: int | None
    end_line: int | None


@dataclass
class SourceIn:
    id: str
    kind: str
    name: str
    uri: str | None = None


@dataclass
class NodeOut:
    id: str
    kind: str
    key: str
    name: str
    path: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    summary: str | None = None
    community: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeOut:
    src: str
    dst: str
    type: str
    weight: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommunityOut:
    index: int
    id: str
    name: str
    summary: str
    size: int
    keywords: list[str]
    meta: dict[str, Any]


@dataclass
class GraphData:
    nodes: dict[str, NodeOut]
    edges: dict[tuple[str, str, str], EdgeOut]
    communities: list[CommunityOut]
    stats: dict[str, Any]


class _Builder:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.nodes: dict[str, NodeOut] = {}
        self.edges: dict[tuple[str, str, str], EdgeOut] = {}

    def nid(self, kind: str, key: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'{self.project_id}|{kind}|{key}'))

    def node(self, kind: str, key: str, name: str, **kw: Any) -> NodeOut:
        i = self.nid(kind, key)
        n = self.nodes.get(i)
        if n is None:
            n = NodeOut(id=i, kind=kind, key=key, name=name, **kw)
            self.nodes[i] = n
        return n

    def edge(self, src: str, dst: str, type_: str, weight: float = 1.0, **evidence: Any) -> None:
        if src == dst:
            return
        k = (src, dst, type_)
        e = self.edges.get(k)
        if e is None:
            self.edges[k] = EdgeOut(src, dst, type_, weight, evidence)
        elif weight > e.weight:
            e.weight = weight


def _kind_for(doc: DocIn) -> str:
    base = doc.source_name.rsplit('/', 1)[-1]
    ext = posixpath.splitext(base)[1].lower()
    if language_of(base) or ext in CONFIG_EXTS or base.lower() in CONFIG_BASENAMES or base.lower().startswith(('dockerfile', 'docker-compose')):
        return 'file'
    if set(doc.facts.get('hints', [])) & {'manifest', 'container', 'ci', 'iac', 'k8s'}:
        return 'file'
    return 'doc'


def _pattern(kw: str) -> re.Pattern[str]:
    kw = kw.lower()
    return re.compile(r'\b' + re.escape(kw) + r'\b')


def assemble(
    project_id: str,
    sources: list[SourceIn],
    docs: list[DocIn],
    symbols: list[SymIn],
    sections: list[SecIn],
    calls: list[tuple[str, str, str]],          # (document_id, source_symbol, target_symbol)
) -> GraphData:
    b = _Builder(project_id)
    stats: dict[str, Any] = Counter()
    src_by_id = {s.id: s for s in sources}
    concepts = catalog.concepts()

    # ---- repos, dirs, files/docs ------------------------------------------------------------------------
    doc_node: dict[str, NodeOut] = {}
    file_refs: list[FileRef] = []
    doc_paths: dict[str, tuple[str, str]] = {}
    for d in docs:
        repo_key = d.source_id or f'src:{d.source_type}'
        src = src_by_id.get(d.source_id or '')
        repo = b.node('repo', repo_key, (src.name if src else SOURCE_LABEL.get(d.source_type, d.source_type)),
                      meta={'source_kind': src.kind if src else d.source_type, 'uri': src.uri if src else None})
        kind = _kind_for(d)
        structured = d.source_type in STRUCTURED_SOURCES
        path = d.source_name.replace('\\', '/').lstrip('/') if structured else d.source_name
        lang = language_of(path) or (d.language if d.language in {'python', 'javascript', 'typescript', 'go', 'java', 'rust', 'ruby'} else None)
        # path-derived hints are recomputed on every build so extractor improvements apply to already-indexed files
        hints = [h for h in d.facts.get('hints', []) if h not in {'test', 'entry'}] + (['test'] if is_test_path(path) else []) + (['entry'] if is_entry_path(path) else [])
        n = b.node(kind, f'{repo_key}:{d.id}', path.rsplit('/', 1)[-1] if structured else path, path=path, document_id=d.id, language=lang,
                   meta={'repo': repo_key, 'hints': hints, 'targets': d.facts.get('targets', []),
                         'loc': d.loc, 'chars': d.chars, 'partial_facts': d.partial, 'test': is_test_path(path)})
        doc_node[d.id] = n
        doc_paths[d.id] = (repo_key, path)
        if structured:
            file_refs.append(FileRef(repo_key, path, lang))
            parent = repo
            parts = path.split('/')[:-1]
            for i in range(len(parts)):
                dpath = '/'.join(parts[: i + 1])
                dn = b.node('dir', f'{repo_key}:{dpath}', parts[i], path=dpath, meta={'repo': repo_key})
                b.edge(parent.id, dn.id, 'contains')
                parent = dn
            b.edge(parent.id, n.id, 'contains')
        else:
            b.edge(repo.id, n.id, 'contains')
        stats['docs_partial' if d.partial else 'docs_full'] += 1

    resolver = ImportResolver(file_refs)
    path_to_doc = {v: k for k, v in doc_paths.items()}

    # ---- symbols -----------------------------------------------------------------------------------------
    sym_by_doc_name: dict[tuple[str, str], list[NodeOut]] = defaultdict(list)
    sym_by_name: dict[str, list[NodeOut]] = defaultdict(list)
    sym_by_qname: dict[str, list[NodeOut]] = defaultdict(list)
    for s in symbols:
        dn = doc_node.get(s.document_id)
        if dn is None:
            continue
        q = s.qualified_name or s.name
        sn = b.node('symbol', s.id, q, path=dn.path, document_id=s.document_id, start_line=s.start_line, end_line=s.end_line,
                    language=s.language or dn.language,
                    summary=((s.docstring or '').strip().splitlines() or [s.signature or ''])[0][:200] or None,
                    meta={'symbol_kind': s.kind, 'signature': s.signature})
        b.edge(dn.id, sn.id, 'contains')
        sym_by_doc_name[(s.document_id, s.name)].append(sn)
        if q != s.name:
            sym_by_doc_name[(s.document_id, q)].append(sn)
        sym_by_name[s.name].append(sn)
        sym_by_qname[q].append(sn)
        stats['symbols'] += 1

    # ---- sections (from parsed headings, so single-chunk documents still expose their structure) -------------
    section_nodes: list[NodeOut] = []
    for d in docs:
        dn = doc_node[d.id]
        heads = [h for h in d.facts.get('headings', []) if h.get('level', 9) <= 3]
        for i, h in enumerate(heads):
            end = (heads[i + 1]['line'] - 1) if i + 1 < len(heads) else max(d.loc, h['line'])
            sn = b.node('section', f"{d.id}:{h['line']}", h['text'], path=dn.path, document_id=d.id, start_line=h['line'], end_line=end, summary=h['text'],
                        meta={'level': h['level']})
            b.edge(dn.id, sn.id, 'contains')
            section_nodes.append(sn)

    # ---- tech nodes + import edges ----------------------------------------------------------------------
    unknown_tech_use: Counter[str] = Counter()
    tech_edges: list[tuple[NodeOut, str, str, str]] = []           # (file node, tech name, edge type, source repo)
    imported_docs: dict[str, set[str]] = defaultdict(set)

    def tech_node(name: str) -> NodeOut | None:
        tid = catalog.lookup_tech(name)
        if tid:
            t = catalog.techs()[tid]
            return b.node('tech', tid, t['name'], meta={'category': t['category'], 'public': True, 'concepts': t.get('concepts', [])})
        return None

    for d in docs:
        node = doc_node[d.id]
        if d.source_type not in STRUCTURED_SOURCES or node.kind != 'file':
            continue
        ref = FileRef(doc_paths[d.id][0], doc_paths[d.id][1], node.language)
        for spec in d.facts.get('imports', []):
            stats['imports_total'] += 1
            r = resolver.resolve(ref, spec)
            if r.kind in {'file', 'dir'}:
                stats['imports_local'] += 1
                if r.kind == 'file':
                    target_doc = path_to_doc.get((r.repo or ref.repo, r.target or ''))
                    if target_doc and target_doc != d.id:
                        tn = doc_node[target_doc]
                        etype = 'tests' if (node.meta.get('test') and not tn.meta.get('test')) else 'imports'
                        b.edge(node.id, tn.id, etype, 1.0, spec=spec)
                        imported_docs[d.id].add(target_doc)
                else:
                    dn = b.nodes.get(b.nid('dir', f'{r.repo}:{r.target}'))
                    if dn:
                        b.edge(node.id, dn.id, 'imports', 0.8, spec=spec)
            elif r.kind == 'external':
                stats['imports_external'] += 1
                tn = tech_node(r.target or '')
                if tn:
                    b.edge(node.id, tn.id, 'uses', 1.0, spec=spec)
                elif r.target:
                    unknown_tech_use[r.target] += 1
                    tech_edges.append((node, r.target, 'uses', ref.repo))
            elif r.kind == 'unresolved':
                stats['imports_unresolved'] += 1
        for hint, tid in (('container', 'docker'), ('k8s', 'kubernetes'), ('ci', 'github-actions' if '.github/' in (node.path or '') else 'gitlab-ci')):
            if hint in d.facts.get('hints', []):
                tn = tech_node(tid)
                if tn:
                    b.edge(node.id, tn.id, 'uses', 1.0, hint=hint)
        if (node.path or '').endswith('.tf'):
            tn = tech_node('terraform')
            if tn:
                b.edge(node.id, tn.id, 'uses', 1.0, hint='iac')
        for spec in d.facts.get('imports_sub', []):       # speculative `from pkg import submodule`: link only if it resolves
            r = resolver.resolve(ref, spec)
            if r.kind == 'file':
                target_doc = path_to_doc.get((r.repo or ref.repo, r.target or ''))
                if target_doc and target_doc != d.id:
                    tn = doc_node[target_doc]
                    b.edge(node.id, tn.id, 'tests' if (node.meta.get('test') and not tn.meta.get('test')) else 'imports', 1.0, spec=spec)
                    imported_docs[d.id].add(target_doc)
        for dep in d.facts.get('deps', []):
            tn = tech_node(dep['name'])
            repo_n = b.nodes.get(b.nid('repo', doc_paths[d.id][0]))
            if tn:
                b.edge(node.id, tn.id, 'depends_on', 1.0, dep=dep['name'])
                if repo_n:
                    b.edge(repo_n.id, tn.id, 'depends_on', 1.0)
            else:
                unknown_tech_use[dep['name']] += 2
                tech_edges.append((node, dep['name'], 'depends_on', doc_paths[d.id][0]))
    for node, name, etype, repo_key in tech_edges:       # private/unknown packages: keep only if used repeatedly
        if unknown_tech_use[name] >= 2:
            tn = b.node('tech', f'ext:{name.lower()}', name, meta={'category': 'unclassified', 'public': False, 'concepts': []})
            b.edge(node.id, tn.id, etype, 0.8)

    # ---- call edges (symbol -> symbol) ------------------------------------------------------------------
    file_call_weight: dict[tuple[str, str], float] = defaultdict(float)
    for doc_id, src_name, tgt_name in calls:
        srcs = sym_by_doc_name.get((doc_id, src_name))
        if not srcs:
            continue
        cands = [c for c in sym_by_doc_name.get((doc_id, tgt_name), []) if c.id != srcs[0].id]
        if not cands:
            for other in imported_docs.get(doc_id, ()):
                cands += sym_by_doc_name.get((other, tgt_name), [])
        if not cands and len(tgt_name) >= 5 and tgt_name.lower() not in COMMON_CALLS:
            g = sym_by_name.get(tgt_name, [])
            cands = g if len(g) <= 3 else []
        for c in cands:
            b.edge(srcs[0].id, c.id, 'calls', 1.0 / len(cands), via='name')
            if c.document_id and c.document_id != doc_id:
                file_call_weight[(doc_id, c.document_id)] += 1.0 / len(cands)
            stats['calls_resolved'] += 1
    for (a, c), w in file_call_weight.items():
        b.edge(doc_node[a].id, doc_node[c].id, 'calls', min(1.0, 0.3 + 0.1 * w))

    # ---- docs -> code / docs -> docs / links ------------------------------------------------------------
    link_nodes = 0
    for d in docs:
        node = doc_node[d.id]
        repo_key, path = doc_paths[d.id]
        ref = FileRef(repo_key, path, node.language)
        for tok in d.facts.get('mentions', []):
            stats['mentions_total'] += 1
            linked = False
            if '/' in tok or re.search(r'\.[A-Za-z0-9]{1,6}$', tok):
                hit = resolver._pick(resolver.sfx_ext.get(tok.lstrip('./'), []), ref)
                if hit:
                    td = path_to_doc.get((hit.repo, hit.path))
                    if td and td != d.id:
                        b.edge(node.id, doc_node[td].id, 'documents', 1.0, mention=tok)
                        linked = True
            if not linked:
                last = tok.split('.')[-1]
                cands = sym_by_qname.get(tok) or (sym_by_name.get(last, []) if len(last) >= 4 and last.lower() not in COMMON_CALLS else [])
                if cands and len(cands) <= 3:
                    for c in cands:
                        b.edge(node.id, c.id, 'documents', 0.8 / len(cands) + 0.2, mention=tok)
                    linked = True
            if not linked:
                tn = tech_node(tok.lower())
                if tn:
                    b.edge(node.id, tn.id, 'mentions', 0.6, mention=tok)
                    linked = True
            stats['mentions_linked'] += int(linked)
        for rel in d.facts.get('links', []):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel)) if path and '/' in path else rel
            td = path_to_doc.get((repo_key, base))
            if td and td != d.id:
                b.edge(node.id, doc_node[td].id, 'documents' if doc_node[td].kind == 'file' else 'links_to', 0.9, link=rel)
        for url in d.facts.get('urls', [])[:10 if node.kind == 'file' else 40]:
            u = urlparse(url)
            if not u.netloc:
                continue
            key = (u.netloc.lower() + u.path.rstrip('/'))[:300]
            ln = b.node('link', key, (u.netloc + u.path.rstrip('/'))[:120], meta={'url': url.split('#')[0], 'host': u.netloc.lower()})
            b.edge(node.id, ln.id, 'links_to', 0.5)
            link_nodes += 1

    # ---- concepts: catalog nodes, prerequisites, tech->concept, keyword mentions ------------------------
    concept_node = {cid: b.node('concept', cid, c['name'], summary=c['description'], meta={'area': c['area'], 'difficulty': c['difficulty']})
                    for cid, c in concepts.items()}
    for cid, c in concepts.items():
        for p in c.get('prereqs', []):
            b.edge(concept_node[p].id, concept_node[cid].id, 'prerequisite_of', 1.0)
    for n in list(b.nodes.values()):
        if n.kind == 'tech':
            for cid in n.meta.get('concepts', []):
                if cid in concept_node:
                    b.edge(n.id, concept_node[cid].id, 'teaches', 1.0)
    lang_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for n in doc_node.values():
        if n.kind == 'file' and n.language:
            lang_counter[n.meta['repo']][n.language] += 1
    for repo_key, cnt in lang_counter.items():
        rn = b.nodes.get(b.nid('repo', repo_key))
        for lang, k in cnt.items():
            cid = catalog.LANGUAGE_CONCEPTS.get(lang)
            if rn and cid and k >= 3:
                b.edge(rn.id, concept_node[cid].id, 'uses', 1.0)
    text_targets: list[tuple[NodeOut, str, float]] = [(s, s.name.lower(), 1.0) for s in section_nodes]
    text_targets += [(n, (n.path or n.name).lower(), 0.7) for n in b.nodes.values() if n.kind in {'doc', 'dir', 'file'}]
    for cid, c in concepts.items():
        pats = [_pattern(k) for k in c.get('keywords', [])]
        hits = [(pri, n, kw) for n, text, pri in text_targets for kw, p in zip(c['keywords'], pats) if p.search(text)]
        hits.sort(key=lambda h: (-h[0], h[1].id))
        seen: set[str] = set()
        for pri, n, kw in hits:
            if n.id in seen:
                continue
            seen.add(n.id)
            b.edge(n.id, concept_node[cid].id, 'mentions', 0.6 * pri, kw=kw)
            if len(seen) >= 40:
                break

    stats['test_files'] = sum(1 for n in doc_node.values() if n.meta.get('test'))
    communities = _communities(b, doc_node, calls_weight=file_call_weight, stats=stats)
    stats['nodes'] = len(b.nodes)
    stats['edges'] = len(b.edges)
    stats['link_nodes'] = link_nodes
    stats['node_kinds'] = dict(Counter(n.kind for n in b.nodes.values()))
    stats['edge_types'] = dict(Counter(e.type for e in b.edges.values()))
    tl = stats.get('imports_local', 0) + stats.get('imports_unresolved', 0)
    stats['import_resolution_rate'] = round(stats.get('imports_local', 0) / tl, 3) if tl else None
    stats['mention_link_rate'] = round(stats.get('mentions_linked', 0) / stats['mentions_total'], 3) if stats.get('mentions_total') else None
    return GraphData(b.nodes, b.edges, communities, dict(stats))


# ---------------------------------------------------------------------------------------------------------
def _communities(b: _Builder, doc_node: dict[str, NodeOut], calls_weight: dict[tuple[str, str], float], stats: dict[str, Any]) -> list[CommunityOut]:
    members = [n for n in doc_node.values()]
    if not members:
        return []
    idx = {n.id: i for i, n in enumerate(members)}
    W = {'imports': 1.0, 'tests': 0.7, 'documents': 0.8, 'links_to': 0.5, 'calls': 0.6}
    uedges: list[tuple[int, int, float]] = []
    for (s, d, t), e in b.edges.items():
        if t in W and s in idx and d in idx:
            uedges.append((idx[s], idx[d], W[t] * e.weight))
    # symbol -> owning file edges (calls between files are already represented at file level)
    def group(n: NodeOut, depth: int) -> str:
        repo = n.meta.get('repo', '')
        parts = (n.path or '').split('/')[:-1][:depth] if n.path and n.meta.get('repo') else []
        return repo + ':' + '/'.join(parts)

    count = len(members)
    depth = 1
    for dp in (3, 2, 1):
        if len({group(n, dp) for n in members}) <= max(6, count // 4):
            depth = dp
            break
    keys = sorted({group(n, depth) for n in members})
    init = [keys.index(group(n, depth)) for n in members]
    labels = label_propagation(count, uedges, init, inertia=0.6, min_size=3 if count >= 12 else 1)
    stats['community_modularity'] = round(modularity(uedges, labels), 4)

    groups: dict[int, list[NodeOut]] = defaultdict(list)
    for n, l in zip(members, labels):
        groups[l].append(n)
        n.community = l
    # propagate to symbols / sections
    for n in b.nodes.values():
        if n.kind in {'symbol', 'section'} and n.document_id in doc_node:
            n.community = doc_node[n.document_id].community

    fan_in: Counter[str] = Counter()
    degree: Counter[str] = Counter()
    for (s, d, t), e in b.edges.items():
        if t in {'imports', 'tests', 'calls'} and s in idx and d in idx:
            fan_in[d] += 1
        if s in idx:
            degree[s] += 1
        if d in idx:
            degree[d] += 1
    for n in members:
        n.meta['fan_in'] = fan_in.get(n.id, 0)

    tech_of: dict[str, Counter[str]] = defaultdict(Counter)
    for (s, d, t), e in b.edges.items():
        if t in {'uses', 'depends_on'} and s in idx and b.nodes[d].kind == 'tech':
            tech_of[str(labels[idx[s]])][b.nodes[d].name] += 1

    cross: dict[tuple[int, int], float] = defaultdict(float)
    for a, c, w in uedges:
        if labels[a] != labels[c]:
            cross[(labels[a], labels[c])] += w
    used_names: Counter[str] = Counter()
    out: list[CommunityOut] = []
    order = sorted(groups, key=lambda l: (-len(groups[l]), l))
    names: dict[int, str] = {}
    for l in order:
        mem = groups[l]
        dirs = Counter('/'.join((n.path or '').split('/')[:-1][:3]) for n in mem if n.kind == 'file' and n.path and n.meta.get('repo'))
        dominant = dirs.most_common(1)[0][0] if dirs else ''
        if not dominant:
            kinds = Counter(n.kind for n in mem)
            dominant = 'Documentation & references' if kinds.get('doc') else 'Project root & tooling'
        used_names[dominant] += 1
        names[l] = dominant if used_names[dominant] == 1 else f'{dominant} ({used_names[dominant]})'
    cid_of = {l: str(uuid.uuid5(uuid.NAMESPACE_URL, f'{b.project_id}|community|{names[l]}')) for l in order}
    for l in order:
        mem = groups[l]
        langs = Counter(n.language for n in mem if n.language)
        top = sorted(mem, key=lambda n: (-(n.meta.get('fan_in', 0) * 2 + degree.get(n.id, 0)), n.path or ''))[:5]
        deps_out = sorted(((names[c], w) for (a, c), w in cross.items() if a == l), key=lambda x: -x[1])[:3]
        deps_in = sorted(((names[a], w) for (a, c), w in cross.items() if c == l), key=lambda x: -x[1])[:3]
        techs = [t for t, _ in tech_of.get(str(l), Counter()).most_common(5)]
        nf = sum(1 for n in mem if n.kind == 'file')
        nd = sum(1 for n in mem if n.kind == 'doc')
        summary = f"{nf} code/config file(s) and {nd} document(s) around `{names[l]}`"
        if langs:
            summary += f" ({', '.join(k for k, _ in langs.most_common(3))})"
        summary += f". Key files: {', '.join(n.path or n.name for n in top[:3])}."
        if techs:
            summary += f" Uses {', '.join(techs)}."
        if deps_out:
            summary += f" Depends on {', '.join(n for n, _ in deps_out)}."
        if deps_in:
            summary += f" Used by {', '.join(n for n, _ in deps_in)}."
        out.append(CommunityOut(
            index=l, id=cid_of[l], name=names[l], summary=summary, size=len(mem),
            keywords=techs + [n.name for n in top[:3]],
            meta={'languages': dict(langs), 'top_nodes': [n.id for n in top],
                  'deps_out': {cid_of[c]: round(w, 2) for (a, c), w in cross.items() if a == l},
                  'deps_in': {cid_of[a]: round(w, 2) for (a, c), w in cross.items() if c == l}},
        ))
    return out
