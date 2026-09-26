import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { login, register, listRoleProfiles } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
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
  const [roleTitle, setRoleTitle] = useState('')
  const roles = useQuery({ queryKey: ['role-profiles'], queryFn: listRoleProfiles })
  // Manager: creates and owns a brand-new organization. Employee: joins the shared demo org/workspace --
  // no invite or org id needed, the backend defaults org_id to the demo org for direct employee signup.
  const [signupRole, setSignupRole] = useState<'manager' | 'employee'>('manager')
  const role = signupRole === 'manager' ? ('manager' as const) : ('learner' as const)
  // UX-only hint for which experience the person expects to land in. The backend's app_role on the
  // authenticated account is the only thing that ever decides permissions or routing -- this never
  // touches either, it just tells them clearly when their expectation and the account disagree.
  const [signinRoleHint, setSigninRoleHint] = useState<'manager' | 'employee'>('manager')

  const from = (location.state as { from?: string } | null)?.from
  const onAuthed = (r: AuthResponse) => {
    qc.clear()
    signIn(r.token, r.user)
    if (mode === 'signin' && r.user.role !== (signinRoleHint === 'manager' ? 'manager' : 'learner')) {
      toast(r.user.role === 'manager' ? "This account is a Manager account — taking you to the Manager dashboard." : "This account is an Employee account — taking you to your learning dashboard.")
    }
    navigate(from && from !== '/login' ? from : '/workspace', { replace: true })
  }

  const signInMutation = useMutation({ mutationFn: () => login({ email, password }), onSuccess: onAuthed })
  const signUpMutation = useMutation({
    mutationFn: () =>
      register({
        email,
        password,
        display_name: name,
        role,
        role_title: roleTitle.trim() || undefined,
      }),
    onSuccess: onAuthed,
  })
  const active = mode === 'signin' ? signInMutation : signUpMutation

  if (token) return <Navigate to="/workspace" replace />

  function submit(e: FormEvent) {
    e.preventDefault()
    active.mutate()
  }

  const canSubmit = email.includes('@') && password.length >= 8 && (mode === 'signin' || name.trim().length > 0)

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
          {mode === 'signin'
            ? 'Sign in to continue your onboarding.'
            : signupRole === 'manager'
              ? 'Create a workspace and manage your team.'
              : 'Join the demo workspace and start your learning path.'}
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
          {mode === 'signin' && (
            <div className="field">
              <label id="signin-role-label">I am signing in as</label>
              <div className="row" role="radiogroup" aria-labelledby="signin-role-label">
                <button type="button" className="chip-toggle" aria-pressed={signinRoleHint === 'manager'} onClick={() => setSigninRoleHint('manager')}>
                  Manager
                </button>
                <button type="button" className="chip-toggle" aria-pressed={signinRoleHint === 'employee'} onClick={() => setSigninRoleHint('employee')}>
                  Employee
                </button>
              </div>
              <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>This only picks which dashboard we expect — your account's actual role always decides what you can do.</p>
            </div>
          )}
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
                  {signupRole === 'manager'
                    ? 'Managers get their own private organization. Create a workspace, then invite teammates and assign them a workspace and role from the Team page. You can set your job role later in Settings.'
                    : "You'll join the shared demo workspace right away — no invite needed. You can set your job role later in Settings."}
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
        </form>
      </div>
    </div>
  )
}
