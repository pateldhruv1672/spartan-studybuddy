"""Graph algorithms with no database or framework dependency (NumPy only).

Everything here is deterministic: same graph + same parameters => same output. That matters because
role packs and curricula are shown to managers and must be reproducible between rebuilds.
"""
from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

# Default influence of each edge type on "what should a newcomer read next".
# (forward, reverse): forward follows the edge direction (A imports B => reading A leads to B).
DEFAULT_EDGE_WEIGHTS: dict[str, tuple[float, float]] = {
    'imports': (1.0, 0.5),
    'calls': (0.9, 0.5),
    'tests': (0.4, 0.8),          # from a test you learn the subject; from the subject you find its tests
    'documents': (0.8, 0.9),      # doc <-> code are equally informative in both directions
    'mentions': (0.6, 0.6),
    'links_to': (0.5, 0.3),
    'depends_on': (0.6, 0.3),
    'uses': (0.5, 0.4),
    'teaches': (0.6, 0.6),
    'prerequisite_of': (0.9, 0.2),
    'contains': (0.35, 0.35),
    'defines': (0.5, 0.5),
}


@dataclass
class Graph:
    """Immutable in-memory view of a project graph."""
    ids: list[str] = field(default_factory=list)
    index: dict[str, int] = field(default_factory=dict)
    kinds: list[str] = field(default_factory=list)
    edges: list[tuple[int, int, str, float]] = field(default_factory=list)   # (src, dst, type, weight)
    _adj: dict[int, list[tuple[int, str, float, bool]]] | None = None       # node -> (nbr, type, weight, is_forward)

    @classmethod
    def build(cls, nodes: Iterable[tuple[str, str]], edges: Iterable[tuple[str, str, str, float]]) -> 'Graph':
        g = cls()
        for nid, kind in nodes:
            if nid not in g.index:
                g.index[nid] = len(g.ids)
                g.ids.append(nid)
                g.kinds.append(kind)
        for s, d, t, w in edges:
            if s in g.index and d in g.index and s != d:
                g.edges.append((g.index[s], g.index[d], t, float(w)))
        return g

    @property
    def n(self) -> int:
        return len(self.ids)

    def adjacency(self) -> dict[int, list[tuple[int, str, float, bool]]]:
        if self._adj is None:
            adj: dict[int, list[tuple[int, str, float, bool]]] = defaultdict(list)
            for s, d, t, w in self.edges:
                adj[s].append((d, t, w, True))
                adj[d].append((s, t, w, False))
            self._adj = adj
        return self._adj

    def neighbors(self, nid: str, types: set[str] | None = None) -> list[tuple[str, str, float, bool]]:
        i = self.index.get(nid)
        if i is None:
            return []
        return [(self.ids[j], t, w, fwd) for j, t, w, fwd in self.adjacency().get(i, []) if not types or t in types]


def personalized_pagerank(
    g: Graph,
    seeds: dict[str, float],
    alpha: float = 0.2,
    iters: int = 50,
    edge_weights: dict[str, tuple[float, float]] | None = None,
    tol: float = 1e-9,
) -> np.ndarray:
    """Personalised PageRank with type- and direction-dependent transition weights.

    p <- (1-alpha) * T^T p + alpha * s   with dangling mass returned to the seed distribution.
    `alpha` is the restart probability: higher keeps the result closer to the seeds.
    """
    n = g.n
    if n == 0:
        return np.zeros(0)
    ew = edge_weights or DEFAULT_EDGE_WEIGHTS
    s = np.zeros(n)
    for nid, w in seeds.items():
        i = g.index.get(nid)
        if i is not None and w > 0:
            s[i] += w
    if s.sum() <= 0:
        return np.zeros(n)
    s /= s.sum()

    src, dst, val = [], [], []
    for a, b, t, w in g.edges:
        fwd, rev = ew.get(t, (0.3, 0.3))
        if fwd * w > 0:
            src.append(a); dst.append(b); val.append(fwd * w)
        if rev * w > 0:
            src.append(b); dst.append(a); val.append(rev * w)
    if not src:
        return s
    src_a, dst_a, val_a = np.array(src), np.array(dst), np.array(val, dtype=float)
    out_w = np.bincount(src_a, weights=val_a, minlength=n)
    norm = val_a / out_w[src_a]
    dangling = out_w == 0
    p = s.copy()
    for _ in range(iters):
        spread = np.bincount(dst_a, weights=p[src_a] * norm, minlength=n)
        nxt = (1 - alpha) * (spread + p[dangling].sum() * s) + alpha * s
        if np.abs(nxt - p).sum() < tol:
            p = nxt
            break
        p = nxt
    return p


def label_propagation(
    n: int,
    edges: Sequence[tuple[int, int, float]],
    init_labels: Sequence[int],
    inertia: float = 0.6,
    max_iter: int = 25,
    min_size: int = 3,
) -> list[int]:
    """Deterministic weighted label propagation seeded with structural labels (e.g. directory).

    Each node adopts the label with the greatest incident weight; `inertia` keeps a node attached to its
    initial label unless neighbours pull harder, which keeps communities recognisable as modules.
    Communities smaller than `min_size` are merged into their most strongly connected neighbour.
    """
    nbrs: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for a, b, w in edges:
        if a != b and w > 0:
            nbrs[a][b] += w
            nbrs[b][a] += w
    labels = list(init_labels)
    for _ in range(max_iter):
        changed = False
        for v in range(n):
            score: dict[int, float] = defaultdict(float)
            for u, w in nbrs[v].items():
                score[labels[u]] += w
            if not score:
                continue
            total = sum(nbrs[v].values())
            score[init_labels[v]] += inertia * total / max(len(nbrs[v]), 1)
            best = min(score, key=lambda l: (-score[l], l))
            if best != labels[v]:
                labels[v] = best
                changed = True
        if not changed:
            break
    # merge tiny communities
    for _ in range(3):
        sizes: dict[int, int] = defaultdict(int)
        for l in labels:
            sizes[l] += 1
        small = {l for l, c in sizes.items() if c < min_size}
        if not small:
            break
        moved = False
        for v in range(n):
            if labels[v] in small:
                score = defaultdict(float)
                for u, w in nbrs[v].items():
                    if labels[u] not in small or labels[u] == labels[v]:
                        score[labels[u]] += w
                score.pop(labels[v], None)
                if score:
                    labels[v] = min(score, key=lambda l: (-score[l], l))
                    moved = True
        if not moved:
            break
    remap: dict[int, int] = {}
    return [remap.setdefault(l, len(remap)) for l in labels]


def modularity(edges: Sequence[tuple[int, int, float]], labels: Sequence[int]) -> float:
    """Newman modularity of an undirected weighted partition (used to compare community algorithms)."""
    m2 = 2.0 * sum(w for _, _, w in edges)
    if m2 == 0:
        return 0.0
    deg: dict[int, float] = defaultdict(float)
    inside: dict[int, float] = defaultdict(float)
    for a, b, w in edges:
        deg[labels[a]] += w
        deg[labels[b]] += w
        if labels[a] == labels[b]:
            inside[labels[a]] += 2 * w
    return sum(inside[c] / m2 - (deg[c] / m2) ** 2 for c in deg)


def topo_order(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str, float]],
    priority: dict[str, float] | None = None,
) -> list[str]:
    """Order nodes so prerequisites come first (edge a->b means "a before b").

    Among nodes that are ready, higher `priority` goes first. If a cycle blocks progress, the node with the
    smallest remaining incoming weight is released (cycles are broken at their weakest edge), so the result
    always contains every node exactly once.
    """
    prio = priority or {}
    node_set = set(nodes)
    incoming: dict[str, dict[str, float]] = {n: {} for n in nodes}
    outgoing: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b, w in edges:
        if a in node_set and b in node_set and a != b and a not in incoming[b]:
            incoming[b][a] = w
            outgoing[a].append(b)
    order_idx = {n: i for i, n in enumerate(nodes)}
    ready = [(-prio.get(n, 0.0), order_idx[n], n) for n in nodes if not incoming[n]]
    heapq.heapify(ready)
    done: set[str] = set()
    out: list[str] = []
    while len(out) < len(nodes):
        if not ready:
            rest = [n for n in nodes if n not in done]
            pick = min(rest, key=lambda n: (sum(w for a, w in incoming[n].items() if a not in done), -prio.get(n, 0.0), order_idx[n]))
            incoming[pick] = {a: w for a, w in incoming[pick].items() if a in done}
            heapq.heappush(ready, (-prio.get(pick, 0.0), order_idx[pick], pick))
        _, _, n = heapq.heappop(ready)
        if n in done:
            continue
        done.add(n)
        out.append(n)
        for m in outgoing[n]:
            if m in done:
                continue
            incoming[m].pop(n, None)
            if not incoming[m]:
                heapq.heappush(ready, (-prio.get(m, 0.0), order_idx[m], m))
    return out


def normalize(scores: dict[str, float]) -> dict[str, float]:
    """Scale to 0..1 by the maximum (0 if all zero)."""
    m = max(scores.values(), default=0.0)
    return {k: (v / m if m > 0 else 0.0) for k, v in scores.items()}
