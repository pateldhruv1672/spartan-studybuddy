import { useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { acceptInviteWithPassword, acceptExistingInvitation } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { Button } from '../components/primitives/Button'
import { TextField } from '../components/primitives/Field'

export function JoinPage() {
  const { token: inviteToken } = useParams()
  const { user, signIn, signOut, setUser, setProjectId } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const acceptExisting = useMutation({
    mutationFn: () => acceptExistingInvitation(inviteToken!),
    onSuccess: (u) => { qc.clear(); setProjectId(null); setUser(u); navigate('/workspace', { replace: true }) },
  })

  const accept = useMutation({
    mutationFn: () => acceptInviteWithPassword({ token: inviteToken!, display_name: name, password, email: email || null }),
    onSuccess: (r) => {
      qc.clear()
      signIn(r.token, r.user)
      navigate('/workspace', { replace: true })
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    accept.mutate()
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <p className="eyebrow" style={{ color: 'var(--primary)' }}>
          YOU'VE BEEN INVITED
        </p>
        <h1>Join your team on StudyBuddy.</h1>
        <p className="auth-sub">Set a password to accept the invitation. You'll join as an employee.</p>

        {user ? (
          <div style={{ display: 'grid', gap: 12 }}>
            <p style={{ fontSize: 14 }}>
              You're signed in as <b>{user.display_name}</b>. Accept using this account if its email matches the invitation. Accounts in active organizations cannot be transferred here.
            </p>
            <Button variant="primary" full pending={acceptExisting.isPending} onClick={() => acceptExisting.mutate()}>Accept with this account</Button>
            {acceptExisting.isError && <p role="alert">{errorMessage(acceptExisting.error)}</p>}
            <Button variant="primary" full onClick={() => { qc.clear(); signOut() }}>
              Sign out and continue
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} className="auth-form">
            <TextField label="Full name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            <TextField
              label="Work email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              hint="Leave blank to use the email your manager invited"
            />
            <TextField
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              hint="At least 8 characters"
            />
            {accept.isError && (
              <p className="auth-error" role="alert">
                {errorMessage(accept.error)}
              </p>
            )}
            <Button type="submit" variant="primary" full pending={accept.isPending} disabled={!name.trim() || password.length < 8}>
              Accept invite
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
