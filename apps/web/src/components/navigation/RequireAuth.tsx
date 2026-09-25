import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { getMe } from '../../api/endpoints'
import { isAppError } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'

export function RequireAuth() {
  const { token, user, setUser, signOut } = useSessionStore()
  const location = useLocation()

  const me = useQuery({ queryKey: ['auth', 'me', token], queryFn: getMe, enabled: !!token, retry: false, staleTime: 5 * 60 * 1000 })

  useEffect(() => {
    if (me.data) setUser(me.data)
  }, [me.data, setUser])

  const rejected = me.isError && isAppError(me.error) && me.error.status === 401
  useEffect(() => {
    if (rejected) signOut()
  }, [rejected, signOut])

  if (!token || rejected) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  if (!user) {
    return (
      <div className="auth-screen">
        <p style={{ color: 'var(--ink-muted)' }}>
          {me.isError ? 'Cannot reach the StudyBuddy backend. Retrying…' : 'Checking your session…'}
        </p>
      </div>
    )
  }

  return <Outlet />
}
