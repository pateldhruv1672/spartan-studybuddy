import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { login, register, listRoleProfiles } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { Button } from '../components/primitives/Button'
import { SelectField, TextField } from '../components/primitives/Field'
import type { AuthResponse } from '../api/types'

export function LoginPage() {
  const { token, signIn } = useSessionStore()
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const role = 'manager' as const
  const [roleTitle, setRoleTitle] = useState('')
  const roles = useQuery({ queryKey: ['role-profiles'], queryFn: listRoleProfiles })
  // Create-account only: Manager is a real, functional choice. Employee is shown for clarity but stays
  // invite-only — selecting it explains how to join instead of submitting a public employee signup.
  const [signupRole, setSignupRole] = useState<'manager' | 'employee'>('manager')

  const from = (location.state as { from?: string } | null)?.from
  const onAuthed = (r: AuthResponse) => {
    qc.clear()
    signIn(r.token, r.user)
    navigate(from && from !== '/login' ? from : '/workspace', { replace: true })
  }

  const signInMutation = useMutation({ mutationFn: () => login({ email, password }), onSuccess: onAuthed })
  const signUpMutation = useMutation({
    mutationFn: () => register({ email, password, display_name: name, role, role_title: roleTitle.trim() || undefined }),
    onSuccess: onAuthed,
  })
  const active = mode === 'signin' ? signInMutation : signUpMutation

  if (token) return <Navigate to="/workspace" replace />

  function submit(e: FormEvent) {
    e.preventDefault()
    active.mutate()
  }

  const canSubmit = email.includes('@') && password.length >= 8 && (mode === 'signin' || (name.trim().length > 0 && signupRole === 'manager'))

  return (
    <div className="auth-screen">
      <div className="auth-intro">
        <div className="auth-brand">
          <div className="mark" aria-hidden="true">
            S
          </div>
          <div>
            <b>Spartan StudyBuddy</b>
            <span>Private engineering onboarding</span>
          </div>
        </div>
        <p className="auth-mission">
          Spartan StudyBuddy turns a company's private engineering knowledge into a personalized onboarding
          academy. It understands the codebase, determines what each employee needs to learn, builds a
          curriculum from internal and public resources, and uses a locally fine-tuned Socratic coding tutor
          to help engineers understand systems&nbsp;— instead of simply generating answers for them.
        </p>
        <ul className="auth-pillars">
          <li>Repository intelligence over your own code</li>
          <li>Role-aware curricula from internal + public sources</li>
          <li>Socratic tutoring, not copy-paste answers</li>
          <li>Everything runs locally — private by default</li>
        </ul>
      </div>
      <div className="auth-card">
        <div className="auth-brand auth-brand--mobile">
          <div className="mark" aria-hidden="true">
            S
          </div>
          <div>
            <b>Spartan StudyBuddy</b>
            <span>Private engineering onboarding</span>
          </div>
        </div>
        <h1>{mode === 'signin' ? 'Welcome back.' : 'Create your account.'}</h1>
        <p className="auth-sub">
          {mode === 'signin' ? 'Sign in to continue your onboarding.' : 'Create a manager workspace. Employees join from a team invitation.'}
        </p>

        <div className="auth-tabs" role="tablist">
          <button role="tab" aria-selected={mode === 'signin'} className={mode === 'signin' ? 'active' : ''} onClick={() => setMode('signin')}>
            Sign in
          </button>
          <button role="tab" aria-selected={mode === 'signup'} className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>
            Create account
          </button>
        </div>

        <form onSubmit={submit} className="auth-form">
          {mode === 'signup' && (
            <div className="field">
              <label id="signup-role-label">Account type</label>
              <div className="row" role="radiogroup" aria-labelledby="signup-role-label">
                <button type="button" className="chip-toggle" aria-pressed={signupRole === 'manager'} onClick={() => setSignupRole('manager')}>
                  Manager
                </button>
                <button type="button" className="chip-toggle" aria-pressed={signupRole === 'employee'} onClick={() => setSignupRole('employee')}>
                  Employee
                </button>
              </div>
            </div>
          )}
          {mode === 'signup' && signupRole === 'employee' ? (
            <div className="auth-employee-notice">
              <p style={{ fontSize: 13, lineHeight: 1.5, margin: 0 }}>
                Employee accounts join through a team invite link from a manager — there's no public employee signup. Ask
                your manager to invite you from the Team page, then open the link they send you to set your password and
                get started.
              </p>
              <Button type="button" variant="secondary" full onClick={() => setMode('signin')}>
                Already have an invite? Sign in instead
              </Button>
            </div>
          ) : (
            <>
              {mode === 'signup' && <TextField label="Full name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />}
              <TextField label="Work email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                hint={mode === 'signup' ? 'At least 8 characters' : undefined}
              />
              {mode === 'signup' && (
                <>
                  <SelectField
                    label="Job role (optional — decides your onboarding path)"
                    value={roleTitle}
                    onChange={(e) => setRoleTitle(e.target.value)}
                  >
                    <option value="">Skip for now</option>
                    {(roles.data?.roles || []).map((r) => (
                      <option key={r.id} value={r.title}>
                        {r.title}
                      </option>
                    ))}
                  </SelectField>
                  {roles.isLoading && <p>Loading job roles…</p>}
                  {roles.isError && <p role="alert">Job roles could not load. You can retry or set your role later. <button type="button" onClick={() => roles.refetch()}>Retry</button></p>}
                  <p className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
                    Managers get their own private organization. Create a workspace, then invite teammates and assign them a workspace and role from the Team page. You can set your job role later in Settings.
                  </p>
                </>
              )}
              {active.isError && (
                <p className="auth-error" role="alert">
                  {errorMessage(active.error)}
                </p>
              )}
              <Button type="submit" variant="primary" full pending={active.isPending} disabled={!canSubmit}>
                {mode === 'signin' ? 'Sign in' : 'Create account'}
              </Button>
            </>
          )}
        </form>
      </div>
    </div>
  )
}
