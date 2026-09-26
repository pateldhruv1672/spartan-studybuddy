import { useEffect, useRef, type ReactNode } from 'react'

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const openerRef = useRef<Element | null>(null)
  // See Modal's onCloseRef comment: keeping onClose out of the dependency array stops every re-render of a
  // caller with an inline onClose (e.g. typing in a field inside the drawer) from tearing the effect down
  // and stealing focus back to the opener button via the cleanup below.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    if (!open) return
    openerRef.current = document.activeElement
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCloseRef.current()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (openerRef.current instanceof HTMLElement) openerRef.current.focus()
    }
  }, [open])

  if (!open) return null
  return (
    <div className="drawer-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2 style={{ fontSize: 22 }}>{title}</h2>
          <button className="btn btn-icon" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </aside>
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: Array<{ id: T; label: string }>; value: T; onChange: (id: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={value === t.id ? 'active' : ''} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

/** Marks a control or panel whose backend endpoint does not exist yet, naming the endpoint so the owner can build it. */
export function NeedsBackend({ endpoint, children }: { endpoint: string; children?: ReactNode }) {
  return (
    <div className="needs-backend">
      <b>Coming soon</b>
      <span>{children ?? 'This feature is designed and waiting on its backend endpoint.'}</span>
      <code>{endpoint}</code>
    </div>
  )
}

export function Section({ eyebrow, title, action, children }: { eyebrow?: string; title?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      {(eyebrow || title || action) && (
        <div className="section-bar">
          <div>
            {eyebrow && <p className="eyebrow" style={{ margin: 0 }}>{eyebrow}</p>}
            {title && <h2>{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function KeyValue({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function timeAgo(iso?: string | null) {
  if (!iso) return '—'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

export function eventLabel(type: string) {
  const map: Record<string, string> = {
    'video.started': 'Started a video',
    'video.paused': 'Paused a video',
    'video.completed': 'Finished a video',
    'article.opened': 'Opened an article',
    'article.progress': 'Read an article',
    'research.source_saved': 'Saved a research source',
    'code.file_opened': 'Opened a file in VS Code',
    'code.test_failed': 'A test failed in VS Code',
    'code.hint_requested': 'Asked for a hint',
    'quiz.completed': 'Completed a quiz',
    'path.joined': 'Joined a path',
    'checkpoint.completed': 'Completed a checkpoint',
  }
  return map[type] ?? type
}
