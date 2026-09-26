import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { acceptExistingInvitation, createProject, listMyInvitations, listProjects } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { Button } from '../components/primitives/Button'
import { TextField, TextAreaField } from '../components/primitives/Field'
import { EmptyState, ErrorState, Modal, Skeleton } from '../components/primitives/Feedback'

export function WorkspacePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { orgId, userId, user, role, setProjectId, setUser, signOut } = useSessionStore()
  const isManager = user?.role === 'manager'
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const { data: projects, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['projects', orgId],
    queryFn: () => listProjects(orgId),
  })
  const invitations = useQuery({
    queryKey: ['invitations', userId],
    queryFn: listMyInvitations,
    enabled: !!userId,
    refetchInterval: 10000,
  })

  const createMutation = useMutation({
    mutationFn: () => createProject({ org_id: orgId, user_id: userId, name, description }),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ['projects', orgId] })
      setProjectId(project.id)
      setCreateOpen(false)
      toast('Workspace created')
      navigate('/sources')
    },
    onError: (e) => toast(errorMessage(e)),
  })

  const acceptInvitation = useMutation({
    mutationFn: (token: string) => acceptExistingInvitation(token),
    onSuccess: (updatedUser) => {
      qc.clear()
      setProjectId(null)
      setUser(updatedUser)
      qc.invalidateQueries({ queryKey: ['invitations'] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast('Invitation accepted. Your assigned workspace is ready.')
    },
    onError: (e) => toast(errorMessage(e)),
  })

  function openWorkspace(id: string) {
    setProjectId(id)
    navigate(role === 'learner' ? '/learn' : '/manager')
  }

  return (
    <div className="view view-narrow">
      <div className="page-head page-head-center">
        <div>
          <p className="eyebrow">WELCOME, {user?.display_name?.toUpperCase()}</p>
          <h1>
            Choose a <span style={{ color: 'var(--primary)' }}>workspace.</span>
          </h1>
          <p>Each workspace holds one team's private repositories, documents, and onboarding paths.</p>
        </div>
      </div>

      <div className="section-bar">
        <h2>Your workspaces</h2>
      {!!invitations.data?.length && (
        <div className="card-flat" style={{ marginBottom: 22, borderColor: 'var(--primary)', textAlign: 'left' }}>
          <p className="eyebrow">PENDING INVITATIONS</p>
          <h2 style={{ fontSize: 20, marginBottom: 10 }}>A team invited you to join.</h2>
          <div style={{ display: 'grid', gap: 12 }}>
            {invitations.data.map((item) => (
              <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                <div><b>{item.organization_name}</b><div className="muted" style={{ fontSize: 13 }}>{item.role_title || 'Engineer'} · {item.project_name || 'Team membership'}</div></div>
                <Button variant="primary" pending={acceptInvitation.isPending} onClick={() => acceptInvitation.mutate(item.token)}>Accept invitation</Button>
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>Invitations are matched to your signed-in email. Active organizations are protected from automatic transfer.</p>
        </div>
      )}

        {isManager && (
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            + Create workspace
          </Button>
        )}
      </div>

      {isLoading && (
        <div className="grid-2">
          <Skeleton height={120} />
          <Skeleton height={120} />
        </div>
      )}

      {isError && <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />}

      {!isLoading && !isError && (!projects || projects.length === 0) && (
        <EmptyState
          title="No workspaces yet"
          description={isManager ? 'Create the first private workspace, then connect a repository or documents.' : 'No workspace has been assigned to you yet. Your manager assigns workspaces from the Team page. Ask them to add you, and it will appear here.'}
        />
      )}

      {!isLoading && projects && projects.length > 0 && (
        <div className="grid-2">
          {projects.map((p) => (
            <button key={p.id} className="card-flat" style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => openWorkspace(p.id)}>
              <div className="eyebrow">WORKSPACE</div>
              <h3 style={{ fontSize: 18, marginBottom: 6 }}>{p.name}</h3>
              <p style={{ fontSize: 13, color: 'var(--ink-muted)' }}>{p.description || 'Private engineering onboarding workspace'}</p>
            </button>
          ))}
        </div>
      )}

      <p style={{ marginTop: 40, fontSize: 13, color: 'var(--ink-faint)', textAlign: 'center' }}>
        Signed in as <b>{user?.email}</b> ·{' '}
        <button
          className="btn-ghost"
          style={{ border: 0, background: 'none', color: 'var(--primary)', fontWeight: 700, cursor: 'pointer' }}
          onClick={() => {
            qc.clear()
            signOut()
            navigate('/login', { replace: true })
          }}
        >
          Sign out
        </button>
      </p>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New workspace">
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Payments Platform" />
        <div style={{ height: 12 }} />
        <TextAreaField
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Private engineering onboarding workspace"
        />
        <div style={{ height: 16 }} />
        <Button variant="primary" full pending={createMutation.isPending} disabled={!name.trim()} onClick={() => createMutation.mutate()}>
          Create workspace
        </Button>
      </Modal>
    </div>
  )
}
