import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { SubgraphEdge, SubgraphNode } from '../../api/types'
import { GraphCanvas, type GraphCanvasHandle } from './GraphCanvas'
import { SearchIcon } from '../../components/primitives/Icons'

/** Node fill by kind. Colors come from design tokens; the legend lists the same mapping. */
const KIND_COLOR: Record<string, string> = {
  repo: 'var(--ink)',
  dir: 'var(--ink-faint)',
  file: 'var(--primary)',
  doc: 'var(--teal)',
  section: 'var(--teal)',
  symbol: 'var(--warning)',
  tech: 'var(--coral)',
  concept: 'var(--success)',
  link: 'var(--primary-strong)',
}

interface EdgeStyle {
  color: string
  dash?: string
  width: number
  label: string
}

/** Edge look by type: the dash pattern carries the meaning so it survives without color vision. */
const EDGE_STYLE: Record<string, EdgeStyle> = {
  imports: { color: 'var(--teal)', width: 1.6, label: 'imports' },
  calls: { color: 'var(--primary)', dash: '6 3', width: 1.6, label: 'calls' },
  inherits: { color: 'var(--coral)', dash: '2 3', width: 1.8, label: 'inherits' },
  mentions: { color: 'var(--ink-faint)', dash: '1 4', width: 1.4, label: 'mentions' },
  links_to: { color: 'var(--ink-faint)', dash: '1 4', width: 1.4, label: 'links to' },
  contains: { color: 'var(--border)', width: 1, label: 'contains' },
  defines: { color: 'var(--border)', width: 1, label: 'defines' },
}
const FALLBACK_EDGE: EdgeStyle = { color: 'var(--ink-faint)', dash: '8 3 2 3', width: 1.2, label: 'related' }
const edgeStyle = (type: string): EdgeStyle => EDGE_STYLE[type] ?? { ...FALLBACK_EDGE, label: type }

const DEFAULT_NODE_LIMIT = 60
const NODE_LIMIT_STEP = 60
const MAX_RINGS = 4
// Minimum arc length (px, at each ring's radius) required between two always-on labels so text stops overlapping.
const MIN_LABEL_ARC = 30

interface Placed extends SubgraphNode {
  x: number
  y: number
  r: number
  ring: number
}

function nodeRadius(relevance: number) {
  const t = Math.max(0, Math.min(1, relevance))
  // A curved (not linear) response so mid-relevance nodes still read as visually distinct from the rest.
  return 5 + Math.pow(t, 0.7) * 12
}

function angularGap(a: number, b: number) {
  const d = Math.abs(a - b) % (2 * Math.PI)
  return d > Math.PI ? 2 * Math.PI - d : d
}

/**
 * Deterministic radial layout: the most relevant node sits at the center, then rings by graph distance
 * (breadth-first over undirected edges). Within a ring nodes are ordered by kind then name, so the same
 * pack always draws the same picture. Ring radius and label density both scale with how many (and how
 * large) the nodes sharing that ring are, instead of a fixed gap, so dense rings automatically get more room.
 */
function layout(nodes: SubgraphNode[], edges: SubgraphEdge[], maxNodes: number) {
  const sorted = [...nodes].sort((a, b) => b.relevance - a.relevance || a.id.localeCompare(b.id))
  const shown = sorted.slice(0, maxNodes)
  const ids = new Set(shown.map((n) => n.id))
  const kept = edges.filter((e) => ids.has(e.src) && ids.has(e.dst) && e.src !== e.dst)

  const adj = new Map<string, string[]>()
  for (const e of kept) {
    adj.set(e.src, [...(adj.get(e.src) || []), e.dst])
    adj.set(e.dst, [...(adj.get(e.dst) || []), e.src])
  }

  const ring = new Map<string, number>()
  const rootCandidates = shown.length ? [shown[0]] : []
  const queue: string[] = []
  for (const root of rootCandidates) {
    ring.set(root.id, 0)
    queue.push(root.id)
  }
  // Every connected component gets seeded by its most relevant node, so islands still land on an inner ring.
  const bfs = () => {
    while (queue.length) {
      const id = queue.shift()!
      for (const next of adj.get(id) || []) {
        if (!ring.has(next)) {
          ring.set(next, Math.min((ring.get(id) ?? 0) + 1, MAX_RINGS))
          queue.push(next)
        }
      }
    }
  }
  bfs()
  for (const n of shown) {
    if (!ring.has(n.id)) {
      ring.set(n.id, 1)
      queue.push(n.id)
      bfs()
    }
  }

  const byRing = new Map<number, SubgraphNode[]>()
  for (const n of shown) byRing.set(ring.get(n.id) ?? MAX_RINGS, [...(byRing.get(ring.get(n.id) ?? MAX_RINGS) || []), n])

  const placed: Placed[] = []
  let outer = 0
  const ringIds = Array.from(byRing.keys()).sort((a, b) => a - b)
  let prevRadius = 0
  const ringGroups: Placed[][] = []
  for (const rIdx of ringIds) {
    const members = (byRing.get(rIdx) || []).sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name))
    const avgR = members.reduce((s, n) => s + nodeRadius(n.relevance), 0) / Math.max(1, members.length)
    const gap = Math.max(40, avgR * 2.4 + 22)
    const minStep = Math.max(112, avgR * 7)
    const radius = rIdx === 0 && members.length === 1 ? 0 : Math.max(prevRadius + minStep, (members.length * gap) / (2 * Math.PI))
    prevRadius = radius
    outer = Math.max(outer, radius)
    const ringPlaced: Placed[] = []
    members.forEach((n, i) => {
      const angle = members.length === 1 && radius === 0 ? 0 : (2 * Math.PI * i) / members.length - Math.PI / 2 + rIdx * 0.35
      const p: Placed = { ...n, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, r: nodeRadius(n.relevance), ring: rIdx }
      placed.push(p)
      ringPlaced.push(p)
    })
    ringGroups.push(ringPlaced)
  }

  // Greedily choose always-on labels ring by ring, most relevant first, skipping a candidate once it
  // would land within MIN_LABEL_ARC px of an already-chosen label — the fix for overlapping label text.
  const labeled = new Set<string>()
  for (const members of ringGroups) {
    const radius = members.length ? Math.hypot(members[0].x, members[0].y) : 0
    const minAngle = radius > 1 ? MIN_LABEL_ARC / radius : 0
    const chosenAngles: number[] = []
    for (const n of [...members].sort((a, b) => b.relevance - a.relevance)) {
      const angle = Math.atan2(n.y, n.x)
      if (radius <= 1 || !chosenAngles.some((a) => angularGap(a, angle) < minAngle)) {
        labeled.add(n.id)
        chosenAngles.push(angle)
      }
    }
  }

  return { placed, edges: kept, outer, hidden: nodes.length - shown.length, labeled }
}

/** Gentle quadratic bow, perpendicular to the edge — keeps radial edges from stacking into straight lines through the center. */
function edgePath(a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const dist = Math.hypot(dx, dy) || 1
  const bow = Math.min(22, dist * 0.1)
  const nx = -dy / dist
  const ny = dx / dist
  const mx = (a.x + b.x) / 2 + nx * bow
  const my = (a.y + b.y) / 2 + ny * bow
  return `M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`
}

function clip(text: string, n = 22) {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text
}

function highlight(text: string, query: string) {
  if (!query) return text
  const i = text.toLowerCase().indexOf(query.toLowerCase())
  if (i < 0) return text
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + query.length)}</mark>
      {text.slice(i + query.length)}
    </>
  )
}

/**
 * Dependency-free SVG of the role subgraph. Nodes are keyboard focusable (Tab, then Enter or Space to select),
 * color encodes kind, size encodes relevance and the dash pattern encodes edge type. Zoom/pan is layered on
 * top by GraphCanvas; the node positions themselves stay deterministic.
 */
export function RoleSubgraph({
  nodes,
  edges,
  onOpenNode,
}: {
  nodes: SubgraphNode[]
  edges: SubgraphEdge[]
  onOpenNode?: (node: SubgraphNode) => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const [hiddenKinds, setHiddenKinds] = useState<Set<string>>(new Set())
  const [nodeLimit, setNodeLimit] = useState(DEFAULT_NODE_LIMIT)
  const [query, setQuery] = useState('')
  const canvasRef = useRef<GraphCanvasHandle>(null)

  const allKinds = useMemo(() => Array.from(new Set(nodes.map((n) => n.kind))).sort(), [nodes])
  const visibleNodes = useMemo(() => nodes.filter((n) => !hiddenKinds.has(n.kind)), [nodes, hiddenKinds])
  const graph = useMemo(() => layout(visibleNodes, edges, nodeLimit), [visibleNodes, edges, nodeLimit])
  const byId = useMemo(() => new Map(graph.placed.map((n) => [n.id, n])), [graph])

  const edgeTypes = useMemo(() => Array.from(new Set(graph.edges.map((e) => e.type))).sort(), [graph])

  const neighbors = useMemo(() => {
    if (!selected) return []
    return graph.edges
      .filter((e) => e.src === selected || e.dst === selected)
      .map((e) => ({ edge: e, other: byId.get(e.src === selected ? e.dst : e.src), out: e.src === selected }))
      .filter((x): x is { edge: SubgraphEdge; other: Placed; out: boolean } => !!x.other)
  }, [graph, selected, byId])
  const neighborIds = useMemo(() => new Set(neighbors.map((n) => n.other.id)), [neighbors])
  const sel = selected ? byId.get(selected) : undefined

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return graph.placed.filter((n) => n.name.toLowerCase().includes(q)).slice(0, 8)
  }, [graph, query])

  useEffect(() => {
    if (selected && !byId.has(selected)) setSelected(null)
  }, [selected, byId])

  if (nodes.length === 0) {
    return <p className="muted">No subgraph was returned for this role. Rebuild the knowledge graph or pick a different role.</p>
  }

  const pad = 90
  const half = graph.outer + pad
  const size = half * 2

  function pick(id: string, focus = false) {
    setSelected((cur) => (cur === id && !focus ? null : id))
    if (focus) {
      const n = byId.get(id)
      if (n) canvasRef.current?.panTo(n.x, n.y)
    }
  }
  function onKey(e: KeyboardEvent<SVGGElement>, id: string) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      pick(id)
    } else if (e.key === 'Escape') {
      setSelected(null)
    }
  }
  function toggleKind(k: string) {
    setHiddenKinds((cur) => {
      const next = new Set(cur)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
  }

  return (
    <div className="subgraph">
      <div className="subgraph-canvas">
        <div className="graph-filter-row">
          {allKinds.map((k) => (
            <button
              key={k}
              type="button"
              className="legend-toggle"
              aria-pressed={!hiddenKinds.has(k)}
              onClick={() => toggleKind(k)}
              title={hiddenKinds.has(k) ? `Show ${k} nodes` : `Hide ${k} nodes`}
            >
              <span className="legend-dot" style={{ background: KIND_COLOR[k] ?? 'var(--ink-muted)' }} aria-hidden="true" />
              {k}
            </button>
          ))}
        </div>
        <div className="graph-search">
          <SearchIcon size={14} />
          <input
            type="search"
            placeholder="Search nodes by name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search subgraph nodes"
          />
          {matches.length > 0 && (
            <div className="graph-search-results">
              {matches.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => {
                    pick(n.id, true)
                    setQuery('')
                  }}
                >
                  <b>{highlight(n.name, query.trim())}</b> <span className="muted">· {n.kind}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <GraphCanvas
          ref={canvasRef}
          viewBox={{ x: -half, y: -half, width: size, height: size }}
          ariaLabel={`Role subgraph with ${graph.placed.length} nodes and ${graph.edges.length} edges. Press Tab to move between nodes, Enter to select. Drag to pan, scroll to zoom.`}
          onReset={() => setSelected(null)}
        >
          <g aria-hidden="true">
            {[...new Set(graph.placed.map((n) => Math.round(Math.hypot(n.x, n.y))))]
              .filter((r) => r > 0)
              .map((r) => (
                <circle key={r} cx={0} cy={0} r={r} fill="none" stroke="var(--border)" strokeWidth={0.6} strokeDasharray="2 5" />
              ))}
            {graph.edges.map((e, i) => {
              const a = byId.get(e.src)
              const b = byId.get(e.dst)
              if (!a || !b) return null
              const st = edgeStyle(e.type)
              const active = !selected || e.src === selected || e.dst === selected
              return (
                <path
                  key={i}
                  d={edgePath(a, b)}
                  fill="none"
                  stroke={st.color}
                  strokeWidth={active && selected ? st.width + 1.2 : st.width}
                  strokeDasharray={st.dash}
                  strokeLinecap="round"
                  opacity={active ? (selected ? 0.95 : 0.42) : 0.06}
                />
              )
            })}
          </g>
          {graph.placed.map((n) => {
            const dim = selected && n.id !== selected && !neighborIds.has(n.id)
            const isSel = n.id === selected
            const showLabel = isSel || neighborIds.has(n.id) || (!selected && graph.labeled.has(n.id))
            return (
              <g
                key={n.id}
                className="subgraph-node"
                role="button"
                tabIndex={0}
                aria-pressed={isSel}
                aria-label={`${n.name}, ${n.kind}, relevance ${Math.round(n.relevance * 100)} percent`}
                onClick={() => pick(n.id)}
                onKeyDown={(e) => onKey(e, n.id)}
                opacity={dim ? 0.12 : 1}
              >
                <circle cx={n.x} cy={n.y} r={n.r + 5} fill="transparent" />
                {isSel && <circle cx={n.x} cy={n.y} r={n.r + 8} fill={KIND_COLOR[n.kind] ?? 'var(--ink-muted)'} opacity={0.16} />}
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={n.r}
                  fill={KIND_COLOR[n.kind] ?? 'var(--ink-muted)'}
                  stroke={isSel ? 'var(--ink)' : 'var(--surface)'}
                  strokeWidth={isSel ? 3 : 1.5}
                />
                {showLabel && (
                  <text
                    x={n.x}
                    y={n.y + n.r + 13}
                    textAnchor="middle"
                    fontSize={11}
                    fontFamily="var(--font-mono)"
                    fontWeight={isSel ? 700 : 400}
                    fill="var(--ink)"
                    stroke="var(--bg)"
                    strokeWidth={3}
                    paintOrder="stroke"
                  >
                    {clip(n.name)}
                  </text>
                )}
              </g>
            )
          })}
        </GraphCanvas>
        {graph.hidden > 0 && (
          <p className="muted" style={{ marginTop: 6 }}>
            Showing {graph.placed.length} of {nodes.length} nodes.{' '}
            <button type="button" className="btn-ghost" style={{ padding: 0 }} onClick={() => setNodeLimit((l) => l + NODE_LIMIT_STEP)}>
              Show {Math.min(NODE_LIMIT_STEP, graph.hidden)} more
            </button>
          </p>
        )}
      </div>

      <div className="subgraph-side">
        <div className="card-flat" aria-live="polite">
          {sel ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <div>
                <p className="eyebrow" style={{ margin: 0 }}>
                  {sel.kind}
                </p>
                <h3 style={{ fontSize: 17, wordBreak: 'break-word' }}>{sel.name}</h3>
                {sel.path && (
                  <p className="mono muted" style={{ fontSize: 11, wordBreak: 'break-all' }}>
                    {sel.path}
                  </p>
                )}
              </div>
              <p style={{ fontSize: 13 }}>
                Relevance to role: <b>{Math.round(sel.relevance * 100)}%</b>
              </p>
              <div>
                <p className="eyebrow">CONNECTIONS ({neighbors.length})</p>
                {neighbors.length === 0 ? (
                  <p className="muted">No connections among the nodes shown.</p>
                ) : (
                  <div className="row-list" style={{ maxHeight: 220, overflow: 'auto' }}>
                    {neighbors.map((nb, i) => (
                      <button key={i} type="button" className="row-btn" onClick={() => pick(nb.other.id, true)}>
                        <span style={{ minWidth: 0 }}>
                          <b style={{ fontSize: 13, wordBreak: 'break-word' }}>{nb.other.name}</b>
                          <span className="muted" style={{ display: 'block', fontSize: 11 }}>
                            {nb.out ? `${edgeStyle(nb.edge.type).label} →` : `← ${edgeStyle(nb.edge.type).label}`} · {nb.other.kind}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {onOpenNode && (
                <button type="button" className="btn btn-primary" onClick={() => onOpenNode(sel)}>
                  Open source
                </button>
              )}
            </div>
          ) : (
            <p className="muted">Select a node to see what it connects to and why it matters. Larger nodes matter more for this role.</p>
          )}
        </div>

        {edgeTypes.length > 0 && (
          <div className="card-flat subgraph-legend">
            <p className="eyebrow">EDGE TYPE</p>
            <ul>
              {edgeTypes.map((t) => {
                const st = edgeStyle(t)
                return (
                  <li key={t}>
                    <svg width="30" height="8" aria-hidden="true">
                      <line
                        x1="0"
                        y1="4"
                        x2="30"
                        y2="4"
                        stroke={st.color === 'var(--border)' ? 'var(--ink-faint)' : st.color}
                        strokeWidth={st.width + 0.6}
                        strokeDasharray={st.dash}
                      />
                    </svg>
                    {st.label}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
