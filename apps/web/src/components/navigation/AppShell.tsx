import { useCallback, useEffect, useState } from 'react'
import { NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getHealth } from '../../api/endpoints'
import { useLiveUpdates, type WsMessage } from '../../api/websocket'
import { useSessionStore } from '../../app/sessionStore'
import { NAV_ITEMS } from './nav'
import { ProjectSwitcher } from './ProjectSwitcher'
import { Toast } from '../primitives/Feedback'
import { Avatar } from '../primitives/Avatar'

/** Maps each server push to the cached queries it makes stale; pushes trigger refetches, never direct renders. */
const INVALIDATIONS: Record<string, string[][]> = {
  onboarding_created: [['paths'], ['path']],
  progress: [['path'], ['paths'], ['learner'], ['manager-analytics'], ['activity']],
  resource_session: [['resume'], ['learner']],
  agent_job: [['job'], ['path'], ['paths'], ['activity']],
  learning_event: [['activity'], ['learner']],
  invitation: [['invitations']],
}

function useOnline() {
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

export function AppShell() {
  const { projectId, role, setRole, user, userId, signOut } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const online = useOnline()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 20000 })

  const onMessage = useCallback(
    (msg: WsMessage) => {
      for (const key of INVALIDATIONS[msg.kind] ?? []) qc.invalidateQueries({ queryKey: key })
    },
    [qc]
  )
  const { connected } = useLiveUpdates(userId || null, onMessage)

  // Only surface a lost connection after 10s, so brief reconnects stay invisible.
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (connected) {
      setPaused(false)
      return
    }
    const t = setTimeout(() => setPaused(true), 10000)
    return () => clearTimeout(t)
  }, [connected])

  if (!projectId) return <Navigate to="/workspace" replace />

  const modelsOnline = health ? Object.values(health.model_endpoints || {}).some(Boolean) : undefined
  const items = NAV_ITEMS.filter((i) => i.roles.includes(role))

  function logout() {
    qc.clear()
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="mark" aria-hidden="true">
            S
          </div>
          <div>
            <b>Spartan</b>
            <span>StudyBuddy</span>
          </div>
        </div>
        <nav aria-label="Primary">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-btn${isActive ? ' active' : ''}`} title={item.label}>
              <span aria-hidden="true" style={{ marginRight: 8 }}>
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-links">
            <NavLink to="/integrations">Connect</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <Avatar label={user?.avatar} name={user?.display_name} />
            <div style={{ minWidth: 0 }}>
              <b style={{ display: 'block', fontSize: 13, color: 'var(--ink)' }}>{user?.display_name}</b>
              <span className={`badge role-badge ${user?.role === 'manager' ? 'role-badge-manager' : ''}`} style={{ padding: '2px 9px', fontSize: 10.5 }}>
                {user?.role === 'manager' ? 'Manager' : 'Employee'}
              </span>
            </div>
          </div>
          {user?.role === 'manager' && (
            <select
              aria-label="Preview role"
              value={role}
              onChange={(e) => {
                const next = e.target.value as 'manager' | 'learner'
                setRole(next)
                navigate(next === 'manager' ? '/manager' : '/learn')
              }}
              style={{ width: '100%', border: '1px solid var(--border-strong)', borderRadius: 8, padding: 6, background: 'var(--surface)', marginBottom: 8 }}
            >
              <option value="manager">Manager view</option>
              <option value="learner">Preview as employee</option>
            </select>
          )}
          <button className="btn btn-secondary btn-full" style={{ padding: '8px 12px', minHeight: 34, fontSize: 12 }} onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main>
        {!online && (
          <div className="offline-banner" role="alert">
            You're offline. Unsent messages and drafts are kept until the connection returns.
          </div>
        )}
        <header className="topbar">
          <ProjectSwitcher />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {paused && online && <span className="live-chip">Live updates paused</span>}
            <span className="system-chip">
              {health === undefined ? 'Checking Spark…' : modelsOnline ? 'DGX Spark · models online' : 'App online · models warming'}
            </span>
            <button className="btn btn-secondary topbar-signout" style={{ padding: '8px 12px', minHeight: 34, fontSize: 12 }} onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <Outlet />
      </main>
      <Toast />
    </div>
  )
}
