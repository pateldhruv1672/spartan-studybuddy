import { create } from 'zustand'
import type { AuthUser } from '../api/types'

const TOKEN_KEY = 'spartan_token'
const PROJECT_KEY = 'spartan_project'
const VIEW_ROLE_KEY = 'spartan_view_role'

type Role = 'manager' | 'learner'

function read(key: string) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* storage unavailable */
  }
}

interface SessionState {
  token: string | null
  user: AuthUser | null
  userId: string
  orgId: string
  projectId: string | null
  role: Role
  signIn: (token: string, user: AuthUser) => void
  setUser: (user: AuthUser) => void
  signOut: () => void
  setProjectId: (id: string | null) => void
  setRole: (role: Role) => void
}

function fromUser(user: AuthUser) {
  const stored = read(VIEW_ROLE_KEY) as Role | null
  // Learners always see the learner view; managers may preview it.
  const role: Role = user.role === 'manager' ? stored ?? 'manager' : 'learner'
  return { user, userId: user.id, orgId: user.org_id, role }
}

export const useSessionStore = create<SessionState>((set) => ({
  token: read(TOKEN_KEY),
  user: null,
  userId: '',
  orgId: 'demo-company',
  projectId: read(PROJECT_KEY),
  role: 'learner',
  signIn: (token, user) => {
    write(TOKEN_KEY, token)
    set({ token, ...fromUser(user) })
  },
  setUser: (user) => set(fromUser(user)),
  signOut: () => {
    write(TOKEN_KEY, null)
    write(PROJECT_KEY, null)
    write(VIEW_ROLE_KEY, null)
    set({ token: null, user: null, userId: '', projectId: null, role: 'learner' })
  },
  setProjectId: (id) => {
    write(PROJECT_KEY, id)
    set({ projectId: id })
  },
  setRole: (role) => {
    write(VIEW_ROLE_KEY, role)
    set((s) => ({ role: s.user?.role === 'manager' ? role : 'learner' }))
  },
}))
