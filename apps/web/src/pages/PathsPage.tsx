import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { listPaths, startRoleOnboarding } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { Button } from '../components/primitives/Button'
import { EmptyState, Skeleton } from '../components/primitives/Feedback'

export function PathsPage() {
  const { userId, projectId, role } = useSessionStore()
  const isManager = role === 'manager'
  const navigate = useNavigate()
  const qc = useQueryClient()
  const startRole = useMutation({
    mutationFn: () => startRoleOnboarding({ user_id: userId, project_id: projectId! }),
    onSuccess: (path) => {
      qc.invalidateQueries({ queryKey: ['paths'] })
      qc.invalidateQueries({ queryKey: ['path'] })
      toast('You are enrolled in the onboarding path')
      navigate(`/paths/${path.id}`)
    },
    onError: (e) => toast(errorMessage(e)),
  })
  const { data, isLoading } = useQuery({ queryKey: ['paths', projectId, userId], queryFn: () => listPaths(projectId!, userId), enabled: !!projectId })

  if (!projectId) return null

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">ROLE-BASED ONBOARDING</p>
          <h1>A learning path that starts with the actual codebase.</h1>
          <p>StudyBuddy identifies prerequisites, finds public resources without leaking private identifiers, and blends them with repository walkthroughs and checkpoints.</p>
        </div>
        {isManager && (
          <Button variant="primary" onClick={() => navigate('/paths/new')}>
            Generate path
          </Button>
        )}
      </div>

      {isLoading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
          <Skeleton height={160} />
          <Skeleton height={160} />
          <Skeleton height={160} />
        </div>
      )}

      {!isLoading && (data?.length ?? 0) === 0 && (
        <EmptyState
          title="No onboarding paths yet"
          description={
            isManager
              ? 'Generate one after connecting a repository or internal documents.'
              : 'Start one for your role now (no invite code needed), or use a link and invite code from your manager.'
          }
          action={
            isManager ? (
              <Button variant="primary" onClick={() => navigate('/paths/new')}>
                Generate path
              </Button>
            ) : (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
                <Button variant="primary" pending={startRole.isPending} onClick={() => startRole.mutate()}>
                  Start onboarding for my role
                </Button>
                <Link className="btn btn-secondary" to="/kit">
                  Choose your role first
                </Link>
              </div>
            )
          }
        />
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {data?.map((p) => (
          <button key={p.id} className="card" style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => navigate(`/paths/${p.id}`)}>
            <div className="eyebrow" style={{ color: 'var(--primary)' }}>
              {p.level.toUpperCase()} · {p.weeks} WEEKS
            </div>
            <h3 style={{ fontSize: 20, margin: '10px 0 8px' }}>{p.target_role}</h3>
            <p style={{ fontSize: 12, color: 'var(--ink-muted)', lineHeight: 1.5 }}>
              {(p.plan?.summary || 'Role-specific onboarding generated from the private codebase.').slice(0, 140)}
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <span className="badge badge-neutral">{p.hours_per_week}h / week</span>
              <span className="badge badge-neutral">{p.plan?.modules?.length ?? 0} modules</span>
              <span className="badge badge-neutral">{p.is_public ? 'Shared' : 'Invite only'}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
