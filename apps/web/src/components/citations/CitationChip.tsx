import { useState } from 'react'

export interface Citation {
  ref?: string
  citation?: string
  source_name?: string
  [key: string]: unknown
}

/** A single clickable citation such as "src/app.py:12-40". Opens whatever the parent wires to onOpen. */
export function CitationChip({ citation, onOpen, label }: { citation: string; onOpen?: () => void; label?: string }) {
  if (!onOpen) return <span className="citation-chip citation-chip-static">{citation}</span>
  return (
    <button type="button" className="citation-chip" onClick={onOpen} title="Open the cited lines" aria-label={label ?? `Open source ${citation}`}>
      {citation}
    </button>
  )
}

export function CitationList({ sources }: { sources?: Citation[] }) {
  const [open, setOpen] = useState<Citation | null>(null)
  if (!sources || sources.length === 0) return null
  return (
    <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
        {sources.slice(0, 6).map((s, i) => (
          <button key={i} className="citation-chip" onClick={() => setOpen(s)}>
            {s.ref ? `${s.ref} ` : ''}
            {s.citation || s.source_name || 'source'}
          </button>
        ))}
      </div>
      {open && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setOpen(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Citation evidence" style={{ maxWidth: 480 }}>
            <div className="modal-head">
              <h2 style={{ fontSize: 18 }}>Evidence</h2>
              <button className="btn btn-icon" aria-label="Close" onClick={() => setOpen(null)}>
                ×
              </button>
            </div>
            <p className="mono" style={{ fontSize: 13, background: 'var(--surface-alt)', padding: 12, borderRadius: 8 }}>
              {open.citation || open.source_name}
            </p>
            <p style={{ fontSize: 13, color: 'var(--ink-muted)' }}>
              Full source preview is available once the secure document viewer endpoint is connected.
            </p>
          </div>
        </div>
      )}
    </>
  )
}
