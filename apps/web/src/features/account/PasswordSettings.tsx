import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { changePassword } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'
import { Button } from '../../components/primitives/Button'
import { TextField } from '../../components/primitives/Field'

export function PasswordSettings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const { signIn } = useSessionStore()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: () => changePassword({ current_password: current, new_password: next }),
    onSuccess: r => { qc.clear(); signIn(r.token,r.user); setCurrent(''); setNext(''); setConfirm('') },
  })
  return <form onSubmit={e => { e.preventDefault(); save.mutate() }} style={{ display: 'grid', gap: 12 }}>
    <TextField label="Current password" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} />
    <TextField label="New password" type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} />
    <TextField label="Confirm password" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} />
    <Button type="submit" pending={save.isPending} disabled={!current || next.length < 8 || next !== confirm}>Change password</Button>
    <p className="muted">Changing your password revokes previous API and browser sessions. Reconnect extensions using the new session token.</p>
    {save.isError && <p role="alert">{errorMessage(save.error)}</p>}
    {save.isSuccess && <p role="status">Password updated.</p>}
  </form>
}
