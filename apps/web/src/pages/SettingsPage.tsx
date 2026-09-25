import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { updateMe, getLeaderboardPreference, setLeaderboardPreference } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { toast } from '../app/uiStore'
import { ROLE_TITLES } from '../app/roles'
import { useSessionStore } from '../app/sessionStore'
import { Button } from '../components/primitives/Button'
import { Card, CardTitle } from '../components/primitives/Card'
import { CheckboxField, SelectField } from '../components/primitives/Field'
import { KeyValue } from '../components/primitives/Layout'
import { PasswordSettings } from '../features/account/PasswordSettings'

function sessionExpiry(token: string | null) {
  try {
    const payload = JSON.parse(atob(token!.split('.')[0].replace(/-/g, '+').replace(/_/g, '/')))
    return new Date(payload.exp * 1000).toLocaleString()
  } catch {
    return '—'
  }
}

export function SettingsPage() {
  const { user, token, signOut, setUser } = useSessionStore()
  const qc = useQueryClient()
  const preference = useQuery({ queryKey: ['leaderboard-preference', user?.id], queryFn: getLeaderboardPreference })
  const savePreference = useMutation({
    mutationFn: setLeaderboardPreference,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['leaderboard-preference'] }); qc.invalidateQueries({ queryKey: ['leaderboard'] }); toast('Leaderboard preference saved') },
    onError: (e) => toast(errorMessage(e)),
  })
  const navigate = useNavigate()
  const [roleTitle, setRoleTitle] = useState(user?.role_title && ROLE_TITLES.includes(user.role_title) ? user.role_title : '')
  const saveRole = useMutation({
    mutationFn: () => updateMe({ role_title: roleTitle }),
    onSuccess: (u) => {
      setUser(u)
      qc.invalidateQueries({ queryKey: ['auth', 'me'] })
      toast(roleTitle ? 'Role saved. New onboarding paths will follow this role.' : 'Job role cleared.')
    },
    onError: (e) => toast(errorMessage(e)),
  })

  return (
    <div className="view view-narrow">
      <div className="page-head page-head-center">
        <div>
          <p className="eyebrow">SETTINGS</p>
          <h1>Your account.</h1>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 14 }}>
        <Card>
          <CardTitle title="Profile" />
          <KeyValue
            rows={[
              ['Name', <b key="n">{user?.display_name}</b>],
              ['Email', user?.email],
              ['Account type', user?.role === 'manager' ? 'Manager' : 'Employee'],
              ['Role profile', user?.role_title],
              ['Session ends', sessionExpiry(token)],
            ]}
          />
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <SelectField label="My job role" value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)}>
                <option value="">No job role</option>
                {ROLE_TITLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </SelectField>
              <Button variant="primary" pending={saveRole.isPending} onClick={() => saveRole.mutate()}>
                Save role
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <CardTitle title="Leaderboard" subtitle="Control how your name appears" />
          <CheckboxField label="Show my name on the workspace leaderboard" checked={preference.data?.visible ?? false} disabled={!preference.data || savePreference.isPending} onChange={(e) => savePreference.mutate(e.target.checked)} />
          <p className="muted" style={{ margin: '10px 0 14px' }}>
            When disabled, the ranking shows “Private learner”. Your earned XP and progress remain visible; conversations and prompts are never included.
          </p>
          {preference.isError && <p role="alert">{errorMessage(preference.error)}</p>}
        </Card>

        <Card>
          <CardTitle title="Password" />
          <PasswordSettings />
        </Card>

        <Card>
          <CardTitle title="Sign out" subtitle="Ends this browser's session" />
          <Button
            variant="danger"
            onClick={() => {
              qc.clear()
              signOut()
              navigate('/login', { replace: true })
            }}
          >
            Sign out of StudyBuddy
          </Button>
        </Card>
      </div>
    </div>
  )
}
