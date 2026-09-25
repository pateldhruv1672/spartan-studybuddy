import { useMemo, useRef, useState } from 'react'
import type { MapEdge } from '../../api/types'
import { GraphCanvas, type GraphCanvasHandle } from '../graph/GraphCanvas'
import { SearchIcon } from '../../components/primitives/Icons'

const EDGE_COLORS: Record<string, string> = {
  calls: 'var(--primary)',
  imports: 'var(--teal)',
  inherits: 'var(--coral)',
}

const DEFAULT_LIMIT = 40
const LIMIT_STEP = 60
const BARYCENTER_PASSES = 4
const ROW_H = 36

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

/** Mean position of a node's neighbors in the opposite column, falling back to its first-appearance slot when it has none yet. */
function avgNeighborPos(neighbors: string[], pos: Map<string, number>, fallback: number) {
  let sum = 0
  let count = 0
  for (const nb of neighbors) {
    const p = pos.get(nb)
    if (p !== undefined) {
      sum += p
      count += 1
    }
  }
  return count ? sum / count : fallback
}

/**
 * Orders each column by the barycenter (mean position) of its connections in the other column, alternating
 * columns for a few passes — the standard two-layer crossing-reduction heuristic. Deterministic: same edges
 * in, same order out, ties broken by first-appearance index so re-renders never jitter.
 */
function orderByBarycenter(edges: MapEdge[]) {
  const leftIdx = new Map<string, number>()
  const rightIdx = new Map<string, number>()
  for (const e of edges) {
    if (!leftIdx.has(e.source_symbol)) leftIdx.set(e.source_symbol, leftIdx.size)
    if (!rightIdx.has(e.target_symbol)) rightIdx.set(e.target_symbol, rightIdx.size)
  }
  const adjLeft = new Map<string, string[]>()
  const adjRight = new Map<string, string[]>()
  for (const e of edges) {
    adjLeft.set(e.source_symbol, [...(adjLeft.get(e.source_symbol) || []), e.target_symbol])
    adjRight.set(e.target_symbol, [...(adjRight.get(e.target_symbol) || []), e.source_symbol])
  }
  let left = Array.from(leftIdx.keys())
  let right = Array.from(rightIdx.keys())
  for (let pass = 0; pass < BARYCENTER_PASSES; pass++) {
    const leftPos = new Map(left.map((n, i) => [n, i]))
    right = [...right].sort(
      (a, b) =>
        avgNeighborPos(adjRight.get(a) || [], leftPos, rightIdx.get(a)!) - avgNeighborPos(adjRight.get(b) || [], leftPos, rightIdx.get(b)!) ||
        rightIdx.get(a)! - rightIdx.get(b)!,
    )
    const rightPos = new Map(right.map((n, i) => [n, i]))
    left = [...left].sort(
      (a, b) =>
        avgNeighborPos(adjLeft.get(a) || [], rightPos, leftIdx.get(a)!) - avgNeighborPos(adjLeft.get(b) || [], rightPos, leftIdx.get(b)!) ||
        leftIdx.get(a)! - leftIdx.get(b)!,
    )
  }
  return { left, right }
}

/**
 * Two-column layout: symbols defined in the repository on the left, what they reference on the right.
 * Deterministic and cheap — no physics simulation — so it stays readable and fast for hundreds of edges.
 * Column order is chosen to minimize edge crossings (see orderByBarycenter) instead of raw appearance order.
 * GraphCanvas layers zoom/pan/fit on top so a wide graph no longer relies on plain horizontal scrolling.
 */
export function DependencyGraph({
  edges,
  selected,
  onSelect,
}: {
  edges: MapEdge[]
  selected: string | null
  onSelect: (name: string) => void
}) {
  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const canvasRef = useRef<GraphCanvasHandle>(null)

  const allTypes = useMemo(() => Array.from(new Set(edges.map((e) => e.edge_type))), [edges])
  const filtered = useMemo(() => edges.filter((e) => !hiddenTypes.has(e.edge_type)), [edges, hiddenTypes])
  const shown = filtered.slice(0, limit)

  const { left, right } = useMemo(() => orderByBarycenter(shown), [shown])

  const positions = useMemo(() => {
    const p = new Map<string, { x: number; y: number }>()
    left.forEach((name, i) => p.set(`l:${name}`, { x: 190, y: 20 + i * ROW_H }))
    right.forEach((name, i) => p.set(`r:${name}`, { x: 760 - 190, y: 20 + i * ROW_H }))
    return p
  }, [left, right])

  const connected = useMemo(() => {
    if (!selected) return null
    const s = new Set<string>()
    for (const e of shown) {
      if (e.source_symbol === selected) s.add(e.target_symbol)
      if (e.target_symbol === selected) s.add(e.source_symbol)
    }
    return s
  }, [shown, selected])

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    const names = new Set([...left, ...right])
    return Array.from(names)
      .filter((n) => n.toLowerCase().includes(q))
      .slice(0, 8)
  }, [query, left, right])

  if (edges.length === 0) {
    return <p className="muted">No dependency edges were extracted yet. They appear after a code repository is indexed.</p>
  }

  const height = Math.max(left.length, right.length) * ROW_H + 20
  const width = 760
  const lx = 190
  const rx = width - 190
  const y = (i: number) => 20 + i * ROW_H
  const related = (e: MapEdge) => !selected || e.source_symbol === selected || e.target_symbol === selected
  const dimNode = (name: string) => !!selected && name !== selected && !connected?.has(name)

  function toggleType(t: string) {
    setHiddenTypes((cur) => {
      const next = new Set(cur)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }

  function focusSymbol(name: string) {
    onSelect(name)
    const pos = positions.get(`l:${name}`) ?? positions.get(`r:${name}`)
    if (pos) canvasRef.current?.panTo(pos.x, pos.y)
  }

  return (
    <div>
      <div className="graph-filter-row">
        {allTypes.map((t) => (
          <button
            key={t}
            type="button"
            className="legend-toggle"
            aria-pressed={!hiddenTypes.has(t)}
            onClick={() => toggleType(t)}
            title={hiddenTypes.has(t) ? `Show ${t} edges` : `Hide ${t} edges`}
          >
            <span style={{ width: 18, height: 3, background: EDGE_COLORS[t] || 'var(--ink-faint)', display: 'inline-block' }} />
            {t}
          </button>
        ))}
        <span className="muted">Click a symbol to highlight its connections.</span>
      </div>
      <div className="graph-search">
        <SearchIcon size={14} />
        <input type="search" placeholder="Search symbols…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search dependency graph symbols" />
        {matches.length > 0 && (
          <div className="graph-search-results">
            {matches.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => {
                  focusSymbol(n)
                  setQuery('')
                }}
              >
                <b>{highlight(n, query.trim())}</b>
              </button>
            ))}
          </div>
        )}
      </div>
      <GraphCanvas
        ref={canvasRef}
        viewBox={{ x: 0, y: 0, width, height }}
        ariaLabel={`Dependency graph with ${shown.length} of ${filtered.length} edges. Drag to pan, scroll to zoom.`}
        height={Math.min(560, Math.max(280, height))}
      >
        {shown.map((e, i) => {
          const a = left.indexOf(e.source_symbol)
          const b = right.indexOf(e.target_symbol)
          const on = related(e)
          return (
            <path
              key={i}
              d={`M ${lx} ${y(a)} C ${(lx + rx) / 2} ${y(a)}, ${(lx + rx) / 2} ${y(b)}, ${rx} ${y(b)}`}
              fill="none"
              stroke={EDGE_COLORS[e.edge_type] || 'var(--ink-faint)'}
              strokeWidth={on && selected ? 2.6 : 1.3}
              opacity={on ? (selected ? 0.95 : 0.55) : 0.06}
            />
          )
        })}
        {left.map((name, i) => {
          const isSel = selected === name
          const dim = dimNode(name)
          return (
            <g key={`l-${name}`} role="button" style={{ cursor: 'pointer' }} onClick={() => onSelect(name)} opacity={dim ? 0.3 : 1}>
              {isSel && <circle cx={lx} cy={y(i)} r={9} fill="var(--primary)" opacity={0.16} />}
              <circle cx={lx} cy={y(i)} r={isSel ? 5.5 : 5} fill={isSel ? 'var(--primary)' : 'var(--ink)'} />
              <text x={lx - 12} y={y(i) + 4} textAnchor="end" fontSize={12} fontFamily="var(--font-mono)" fontWeight={isSel ? 700 : 400} fill={isSel ? 'var(--primary-strong)' : 'var(--ink)'}>
                {name.length > 24 ? `${name.slice(0, 23)}…` : name}
              </text>
            </g>
          )
        })}
        {right.map((name, i) => {
          const isSel = selected === name
          const dim = dimNode(name)
          return (
            <g key={`r-${name}`} role="button" style={{ cursor: 'pointer' }} onClick={() => onSelect(name)} opacity={dim ? 0.3 : 1}>
              {isSel && <circle cx={rx} cy={y(i)} r={9} fill="var(--primary)" opacity={0.16} />}
              <circle cx={rx} cy={y(i)} r={isSel ? 5.5 : 5} fill={isSel ? 'var(--primary)' : 'var(--surface)'} stroke={isSel ? 'var(--primary)' : 'var(--ink)'} />
              <text x={rx + 12} y={y(i) + 4} fontSize={12} fontFamily="var(--font-mono)" fontWeight={isSel ? 700 : 400} fill={isSel ? 'var(--primary-strong)' : 'var(--ink-muted)'}>
                {name.length > 24 ? `${name.slice(0, 23)}…` : name}
              </text>
            </g>
          )
        })}
      </GraphCanvas>
      {filtered.length > limit && (
        <button className="btn btn-secondary" style={{ marginTop: 10 }} onClick={() => setLimit((l) => l + LIMIT_STEP)}>
          Show more ({filtered.length - limit} hidden)
        </button>
      )}
    </div>
  )
}
