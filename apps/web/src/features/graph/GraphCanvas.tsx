import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type PointerEvent, type ReactNode } from 'react'

export interface GraphCanvasHandle {
  fit: () => void
  reset: () => void
  panTo: (x: number, y: number, scale?: number) => void
}

interface Transform {
  x: number
  y: number
  scale: number
}

const IDENTITY: Transform = { x: 0, y: 0, scale: 1 }

/**
 * Pan/zoom chrome around a deterministically-laid-out SVG graph. The layout algorithm stays untouched —
 * this only adds an interaction layer (drag to pan, wheel/buttons to zoom, fit/reset) on top of it, since
 * the app deliberately has no graph library and the underlying node/edge positions must stay reproducible.
 */
export const GraphCanvas = forwardRef<
  GraphCanvasHandle,
  {
    viewBox: { x: number; y: number; width: number; height: number }
    ariaLabel: string
    height?: number
    minScale?: number
    maxScale?: number
    onReset?: () => void
    children: ReactNode
  }
>(function GraphCanvas({ viewBox, ariaLabel, height = 560, minScale = 0.3, maxScale = 5, onReset, children }, ref) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [t, setT] = useState<Transform>(IDENTITY)
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)

  const clampScale = (s: number) => Math.min(maxScale, Math.max(minScale, s))

  function toViewBoxPoint(clientX: number, clientY: number) {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const pt = svg.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return { x: 0, y: 0 }
    const p = pt.matrixTransform(ctm.inverse())
    return { x: p.x, y: p.y }
  }

  function zoomAt(clientX: number, clientY: number, factor: number) {
    setT((cur) => {
      const next = clampScale(cur.scale * factor)
      if (next === cur.scale) return cur
      const p = toViewBoxPoint(clientX, clientY)
      const cx = (p.x - cur.x) / cur.scale
      const cy = (p.y - cur.y) / cur.scale
      return { scale: next, x: p.x - cx * next, y: p.y - cy * next }
    })
  }

  function zoomAtCenter(factor: number) {
    const svg = svgRef.current
    if (!svg) return
    const r = svg.getBoundingClientRect()
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor)
  }

  useImperativeHandle(ref, () => ({
    fit: () => setT(IDENTITY),
    reset: () => {
      setT(IDENTITY)
      onReset?.()
    },
    panTo: (x, y, scale) => {
      const targetScale = clampScale(scale ?? Math.max(1.4, t.scale))
      const vbCenterX = viewBox.x + viewBox.width / 2
      const vbCenterY = viewBox.y + viewBox.height / 2
      setT({ scale: targetScale, x: vbCenterX - x * targetScale, y: vbCenterY - y * targetScale })
    },
  }))

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15)
    }
    svg.addEventListener('wheel', wheel, { passive: false })
    return () => svg.removeEventListener('wheel', wheel)
  })

  function onPointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    if ((e.target as Element).closest('[role="button"]')) return
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
    dragRef.current = { x: e.clientX, y: e.clientY, ox: t.x, oy: t.y }
    setDragging(true)
  }
  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    const d = dragRef.current
    const svg = svgRef.current
    if (!d || !svg) return
    const start = toViewBoxPoint(d.x, d.y)
    const current = toViewBoxPoint(e.clientX, e.clientY)
    setT((cur) => ({ ...cur, x: d.ox + current.x - start.x, y: d.oy + current.y - start.y }))
  }
  function endDrag() {
    dragRef.current = null
    setDragging(false)
  }

  return (
    <div className="graph-canvas">
      <div className="graph-toolbar" role="toolbar" aria-label="Graph view controls">
        <button type="button" className="btn btn-icon" aria-label="Zoom in" onClick={() => zoomAtCenter(1.3)}>
          +
        </button>
        <button type="button" className="btn btn-icon" aria-label="Zoom out" onClick={() => zoomAtCenter(1 / 1.3)}>
          −
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => setT(IDENTITY)}>
          Fit to screen
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            setT(IDENTITY)
            onReset?.()
          }}
        >
          Reset view
        </button>
      </div>
      <svg
        ref={svgRef}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        role="group"
        aria-label={ariaLabel}
        className="graph-svg"
        style={{ height, cursor: dragging ? 'grabbing' : 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
        onPointerCancel={endDrag}
      >
        <g transform={`translate(${t.x} ${t.y}) scale(${t.scale})`}>{children}</g>
      </svg>
    </div>
  )
})
