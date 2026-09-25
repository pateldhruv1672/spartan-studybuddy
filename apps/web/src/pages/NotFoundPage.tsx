import { Link } from 'react-router-dom'
import { useSessionStore } from '../app/sessionStore'

export function NotFoundPage() {
  const role = useSessionStore((s) => s.role)
  return (
    <div className="view view-narrow" style={{ textAlign: 'center', paddingTop: 96 }}>
      <p className="eyebrow">404</p>
      <h1 style={{ fontSize: 40 }}>This page doesn't exist.</h1>
      <p className="muted" style={{ margin: '12px 0 24px' }}>
        The link may be old, or the page may have moved.
      </p>
      <Link className="btn btn-primary" to={role === 'manager' ? '/manager' : '/learn'}>
        Go to your home page
      </Link>
    </div>
  )
}
