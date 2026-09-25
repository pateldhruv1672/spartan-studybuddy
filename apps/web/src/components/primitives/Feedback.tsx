import { useEffect, useRef, type ReactNode } from 'react'
import { useToastStore } from '../../app/uiStore'

export function Skeleton({ width = '100%', height = 16 }: { width?: string | number; height?: number | string }) {
  return <div className="skeleton" style={{ width, height }} aria-hidden="true" />
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{description}</p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="empty-state" role="alert">
      <h3 style={{ color: 'var(--danger-ink)' }}>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && (
        <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function Toast() {
  const message = useToastStore((s) => s.message)
  const xp = useToastStore((s) => s.xp)
  return (
    <>
      <div className={`toast ${message ? '' : 'hidden-toast'}`} role="status" aria-live="polite">
        {message}
      </div>
      {xp !== null && (
        <div className="xp-burst" role="status" aria-live="polite">
          +{xp} XP
        </div>
      )}
    </>
  )
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const openerRef = useRef<Element | null>(null)
  // Callers typically pass an inline `() => ...` for onClose, which gets a new identity on every parent
  // re-render (e.g. on every keystroke in a form inside the modal). Keeping it in a ref — instead of the
  // effect's dependency array — stops that from tearing the effect down and refocusing the opener button
  // (via the cleanup below) on every render, which was stealing focus away from whatever the user was typing in.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onCloseRef.current()
      }
      document.addEventListener('keydown', onKey)
      return () => {
        document.removeEventListener('keydown', onKey)
        if (openerRef.current instanceof HTMLElement) openerRef.current.focus()
      }
    }
  }, [open])

  if (!open) return null
  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="btn btn-icon" aria-label="Close dialog" onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
