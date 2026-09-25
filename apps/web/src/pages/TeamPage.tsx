import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assignWorkspace, inviteTeammate, listProjects, listTeam, listTeamInvitations, revokeTeamInvitation, unassignWorkspace, updateTeamMember } from '../api/endpoints'
import { ROLE_TITLES } from '../app/roles'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { pct, usePathDetails } from '../app/hooks'
import { Button } from '../components/primitives/Button'
import { Card, CardTitle } from '../components/primitives/Card'
import { SelectField, TextField } from '../components/primitives/Field'
import { EmptyState, Skeleton } from '../components/primitives/Feedback'
import { Drawer, KeyValue, Section } from '../components/primitives/Layout'
import { ProgressBar } from '../components/primitives/ProgressBar'
import type { TeamMember } from '../api/types'

const ROLE_PROFILES = ROLE_TITLES

export function TeamPage() {
  const { orgId, userId } = useSessionStore()
  const qc = useQueryClient()
  const [email, setEmail] = useState('')
  const [roleTitle, setRoleTitle] = useState(ROLE_PROFILES[0])
  const [inviteProject, setInviteProject] = useState('')
  const [memberRole, setMemberRole] = useState('')
  const [inviteUrl, setInviteUrl] = useState<string | null>(null)
  const [selected, setSelected] = useState<TeamMember | null>(null)

  const team = useQuery({ queryKey: ['team', orgId], queryFn: () => listTeam(orgId) })
  const workspaces = useQuery({ queryKey: ['projects', orgId], queryFn: () => listProjects(orgId) })
  const live = selected ? team.data?.find((m) => m.id === selected.id) ?? selected : null
  const invitations = useQuery({
    queryKey: ['team-invites', orgId],
    queryFn: () => listTeamInvitations(orgId),
    refetchInterval: 15000,
  })
  const toggleWorkspace = useMutation({
    mutationFn: (v: { projectId: string; on: boolean }) => (v.on ? assignWorkspace(v.projectId, { user_id: selected!.id }) : unassignWorkspace(v.projectId, selected!.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team', orgId] })
      toast('Workspace access updated')
    },
    onError: (e) => toast(errorMessage(e)),
  })
  const saveRole = useMutation({
    mutationFn: () => updateTeamMember(selected!.id, { role_title: memberRole }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team', orgId] })
      toast('Role saved. Their onboarding path follows this role.')
    },
    onError: (e) => toast(errorMessage(e)),
  })
  const { paths } = usePathDetails()

  const progressByUser = useMemo(() => {
    const map = new Map<string, Array<{ role: string; progress: number; xp: number }>>()
    for (const p of paths) {
      for (const m of p.members || []) {
        const rows = map.get(m.user_id) || []
        rows.push({ role: p.target_role, progress: m.progress || 0, xp: m.xp || 0 })
        map.set(m.user_id, rows)
      }
    }
    return map
  }, [paths])

  const invite = useMutation({
    mutationFn: () => inviteTeammate({ org_id: orgId, invited_by: userId, email: email || null, role_title: roleTitle, project_id: inviteProject || null }),
    onSuccess: (r) => {
      const url = `${location.origin}/join/${r.token}`
      setInviteUrl(url)
      qc.invalidateQueries({ queryKey: ['team-invites', orgId] })
      navigator.clipboard?.writeText(url).catch(() => {})
      toast('Invite link copied')
      setEmail('')
    },
    onError: (e) => toast(errorMessage(e)),
  })

  const selectedPaths = selected ? progressByUser.get(selected.id) || [] : []
  const revoke = useMutation({
    mutationFn: (token: string) => revokeTeamInvitation(orgId, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team-invites', orgId] })
      toast('Invitation revoked')
    },
    onError: (e) => toast(errorMessage(e)),
  })


  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">TEAM</p>
          <h1>Everyone onboarding with you.</h1>
          <p>Invite engineers, give them a role profile, and follow their path progress. Private conversations are never shown here.</p>
        </div>
      </div>

      <div className="split">
        <Card>
          <CardTitle title="Members" subtitle={`${team.data?.length ?? 0} people in this organization`} />
          {team.isLoading && <Skeleton height={200} />}
          {!team.isLoading && (team.data?.length ?? 0) === 0 && <EmptyState title="No members yet" description="Invite your first teammate." />}
          <div className="row-list">
            {team.data?.map((m) => {
              const rows = progressByUser.get(m.id) || []
              const best = rows.reduce((a, r) => Math.max(a, r.progress), 0)
              return (
                <button key={m.id} className="row-btn" onClick={() => setSelected(m)}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                    <span className="user-avatar">{m.avatar || m.display_name.slice(0, 2).toUpperCase()}</span>
                    <span style={{ minWidth: 0 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <b style={{ fontSize: 14 }}>{m.display_name}</b>
                        <span className={`badge role-badge ${m.app_role === 'manager' ? 'role-badge-manager' : ''}`} style={{ padding: '1px 8px', fontSize: 10 }}>
                          {m.app_role === 'manager' ? 'Manager' : 'Employee'}
                        </span>
                      </span>
                      <span className="muted" style={{ fontSize: 12 }}>
                        {m.role_title || 'Engineer'} · {m.email || 'no email'}
                      </span>
                    </span>
                  </span>
                  <span style={{ width: 140, flex: '0 0 140px' }}>
                    {rows.length ? (
                      <>
                        <span style={{ fontSize: 12, fontWeight: 700 }}>{pct(best)}</span>
                        <ProgressBar value={best} />
                      </>
                    ) : (
                      <span className="badge badge-neutral">No path yet</span>
                    )}
                  </span>
                </button>
              )
            })}
          </div>
        </Card>

        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <Card>
            <CardTitle title="Invite a teammate" subtitle="They set their own password when they accept" />
            <div style={{ display: 'grid', gap: 12 }}>
              <TextField label="Work email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="engineer@company.com" />
              <SelectField label="Role profile" value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)}>
                {ROLE_PROFILES.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </SelectField>
              <SelectField label="Assign to workspace" value={inviteProject} onChange={(e) => setInviteProject(e.target.value)}>
                <option value="">No workspace yet</option>
                {(workspaces.data || []).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </SelectField>
              <Button variant="primary" full pending={invite.isPending} disabled={!email.includes('@')} onClick={() => invite.mutate()}>
                Create invite link
              </Button>
              {inviteUrl && (
                <p className="mono" style={{ fontSize: 12, background: 'var(--primary-tint)', padding: 10, borderRadius: 8, wordBreak: 'break-all' }}>
                  {inviteUrl}
                </p>
              )}
            </div>
          </Card>
          <Section eyebrow="INVITATIONS">
            {invitations.isLoading && <Skeleton height={90} />}
            {!invitations.isLoading && !invitations.data?.length && <p className="muted">No invitations yet.</p>}
            <div className="row-list">
              {invitations.data?.map((item) => {
                const status = item.expired && item.status === 'pending' ? 'expired' : item.status
                const url = `${location.origin}${item.join_url}`
                return (
                  <div key={item.id} style={{ display: 'grid', gap: 8, padding: '10px 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <div>
                        <b style={{ fontSize: 14 }}>{item.email}</b>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {item.role_title || 'Engineer'} · {item.project_name || 'No workspace assigned'}
                        </div>
                      </div>
                      <span className={`badge ${status === 'accepted' ? 'badge-success' : status === 'pending' ? 'badge-warning' : 'badge-neutral'}`}>{status}</span>
                    </div>
                    {status === 'pending' && (
                      <div style={{ display: 'flex', gap: 8 }}>
                        <Button
                          onClick={() => {
                            navigator.clipboard?.writeText(url).catch(() => {})
                            toast('Invite link copied')
                          }}
                        >
                          Copy link
                        </Button>
                        <Button pending={revoke.isPending} onClick={() => revoke.mutate(item.token)}>
                          Revoke
                        </Button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </Section>
        </div>
      </div>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.display_name || ''}>
        {selected && live && (
          <div style={{ display: 'grid', gap: 20 }}>
            <KeyValue
              rows={[
                ['Role profile', selected.role_title],
                ['Email', selected.email],
                ['Joined', selected.created_at ? new Date(String(selected.created_at)).toLocaleDateString() : '—'],
              ]}
            />
            <div>
              <p className="eyebrow">PATH PROGRESS</p>
              {selectedPaths.length === 0 ? (
                <p className="muted">Not enrolled in any of your paths yet. Share a path link and invite code with them.</p>
              ) : (
                <div style={{ display: 'grid', gap: 12 }}>
                  {selectedPaths.map((r, i) => (
                    <div key={i}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                        <span>{r.role}</span>
                        <b>
                          {pct(r.progress)} · {r.xp} XP
                        </b>
                      </div>
                      <ProgressBar value={r.progress} />
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="eyebrow">WORKSPACES THIS PERSON CAN USE</p>
              {live.app_role === 'manager' ? (
                <p className="muted">Managers can open every workspace in the organization.</p>
              ) : (
                <div style={{ display: 'grid', gap: 8 }}>
                  {(workspaces.data || []).map((w) => (
                    <label key={w.id} className="checkbox-row" style={{ fontSize: 14 }}>
                      <input
                        type="checkbox"
                        checked={(live.workspace_ids || []).includes(w.id)}
                        disabled={toggleWorkspace.isPending}
                        onChange={(e) => toggleWorkspace.mutate({ projectId: w.id, on: e.target.checked })}
                      />
                      {w.name}
                    </label>
                  ))}
                  {(workspaces.data || []).length === 0 && <p className="muted">Create a workspace first.</p>}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <SelectField label="Role profile" value={memberRole || (ROLE_PROFILES.includes(live.role_title || '') ? (live.role_title as string) : ROLE_PROFILES[0])} onChange={(e) => setMemberRole(e.target.value)}>
                {ROLE_PROFILES.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </SelectField>
              <Button variant="primary" pending={saveRole.isPending} disabled={!memberRole} onClick={() => saveRole.mutate()}>
                Save role
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}
