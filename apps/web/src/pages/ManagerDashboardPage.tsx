import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { getEvents, getHealth, getProjectMap, listSources, listTeam } from '../api/endpoints'
import { useSessionStore } from '../app/sessionStore'
import { pct, usePathDetails } from '../app/hooks'
import { Button } from '../components/primitives/Button'
import { Badge } from '../components/primitives/Badge'
import { Card, CardTitle, StatCard } from '../components/primitives/Card'
import { Skeleton } from '../components/primitives/Feedback'
import { Drawer, KeyValue, eventLabel, timeAgo } from '../components/primitives/Layout'
import { LearnerSummary } from '../features/analytics/LearnerSummary'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { KnowledgeGapList } from '../features/analytics/KnowledgeGaps'

interface LearnerRow {
  user_id: string
  name: string
  paths: Array<{ id: string; role: string; progress: number; xp: number; streak: number }>
}

export function ManagerDashboardPage() {
  const { orgId, userId, projectId } = useSessionStore()
  const navigate = useNavigate()
  const [learner, setLearner] = useState<LearnerRow | null>(null)

  const map = useQuery({ queryKey: ['repository-map', projectId], queryFn: () => getProjectMap(projectId!), enabled: !!projectId })
  const sources = useQuery({ queryKey: ['sources', projectId], queryFn: () => listSources(projectId!), enabled: !!projectId })
  const team = useQuery({ queryKey: ['team', orgId], queryFn: () => listTeam(orgId) })
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth })
  const activity = useQuery({ queryKey: ['activity', userId, projectId], queryFn: () => getEvents(userId, projectId ?? undefined, 10), enabled: !!projectId })
  const { paths, loading: pathsLoading } = usePathDetails()

  const learners = useMemo<LearnerRow[]>(() => {
    const byUser = new Map<string, LearnerRow>()
    for (const p of paths) {
      for (const m of p.members || []) {
        if (m.user_id === userId) continue
        const row = byUser.get(m.user_id) || { user_id: m.user_id, name: m.display_name || 'Learner', paths: [] }
        row.paths.push({ id: p.id, role: p.target_role, progress: m.progress || 0, xp: m.xp || 0, streak: m.streak || 0 })
        byUser.set(m.user_id, row)
      }
    }
    return Array.from(byUser.values()).sort((a, b) => b.paths[0].progress - a.paths[0].progress)
  }, [paths, userId])

  const completions = learners.filter((l) => l.paths.some((p) => p.progress >= 1)).length
  const failedSources = (sources.data || []).filter((s) => s.status === 'failed').length
  const embeddingsOnline = health.data?.model_endpoints?.embeddings

  const checklist = [
    { done: true, label: 'Workspace created' },
    { done: (sources.data?.length ?? 0) > 0 || (map.data?.documents ?? 0) > 0, label: 'Knowledge connected', to: '/sources' },
    { done: (map.data?.symbols.length ?? 0) > 0, label: 'Repository indexed', to: '/repository' },
    { done: paths.length > 0, label: 'Path generated', to: '/paths/new' },
    { done: learners.length > 0, label: 'Learner enrolled', to: '/team' },
  ]

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">OVERVIEW</p>
          <h1>Readiness, at a glance.</h1>
          <p>Measured from ingestion, path and checkpoint data. Nothing here estimates productivity or time saved.</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button onClick={() => navigate('/sources')}>Add knowledge</Button>
          <Button variant="primary" onClick={() => navigate('/paths/new')}>
            Generate path
          </Button>
        </div>
      </div>

      <div className="card-flat">
        <CardTitle title="Setup" subtitle={`${checklist.filter((c) => c.done).length} of ${checklist.length} steps done`} />
        <div className="grid-4" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
          {checklist.map((item) => (
            <button
              key={item.label}
              onClick={() => item.to && navigate(item.to)}
              disabled={!item.to}
              style={{ textAlign: 'left', border: '1px solid var(--border)', borderRadius: 12, padding: 14, background: item.done ? 'var(--success-tint)' : 'var(--surface)', cursor: item.to ? 'pointer' : 'default' }}
            >
              <div style={{ fontSize: 18, color: item.done ? 'var(--success-ink)' : 'var(--ink-faint)' }}>{item.done ? '✓' : '○'}</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginTop: 6 }}>{item.label}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="grid-4 section">
        {map.isLoading || pathsLoading ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} height={96} />)
        ) : (
          <>
            <StatCard label="Learners enrolled" value={String(learners.length)} />
            <StatCard label="Paths completed" value={String(completions)} />
            <StatCard label="Onboarding paths" value={String(paths.length)} />
            <StatCard label="Indexed documents" value={String(map.data?.documents ?? 0)} />
          </>
        )}
      </div>

      <div className="split section">
        <Card>
          <CardTitle title="Learner progress" subtitle="Checkpoint-based path progress" action={<Link className="btn btn-ghost" to="/team">Team →</Link>} />
          {pathsLoading ? (
            <Skeleton height={160} />
          ) : learners.length === 0 ? (
            <p className="muted">No learners enrolled yet. Invite teammates from the Team page and share a path link.</p>
          ) : (
            <table className="table">
              <caption>Learners across your paths</caption>
              <thead>
                <tr>
                  <th scope="col">Learner</th>
                  <th scope="col">Path</th>
                  <th scope="col">Progress</th>
                  <th scope="col">XP</th>
                </tr>
              </thead>
              <tbody>
                {learners.slice(0, 8).map((l) => (
                  <tr key={l.user_id}>
                    <td>
                      <button className="btn-ghost" style={{ border: 0, background: 'none', padding: 0, fontWeight: 700, color: 'var(--primary)', cursor: 'pointer' }} onClick={() => setLearner(l)}>
                        {l.name}
                      </button>
                    </td>
                    <td>{l.paths[0].role}</td>
                    <td style={{ width: 160 }}>
                      <span style={{ fontSize: 12, fontWeight: 700 }}>{pct(l.paths[0].progress)}</span>
                      <ProgressBar value={l.paths[0].progress} />
                    </td>
                    <td>{l.paths.reduce((s, p) => s + p.xp, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <Card>
            <CardTitle title="Knowledge health" action={<Link className="btn btn-ghost" to="/sources">Manage →</Link>} />
            <KeyValue
              rows={[
                ['Sources', String(sources.data?.length ?? 0)],
                ['Failed sources', failedSources ? <Badge key="f" tone="danger">{failedSources}</Badge> : '0'],
                ['Indexed files', String(map.data?.documents ?? 0)],
                ['Code symbols', String(map.data?.symbols.length ?? 0)],
                ['Embedding model', embeddingsOnline ? <Badge key="e" tone="success">Online</Badge> : <Badge key="e" tone="warning">Offline</Badge>],
              ]}
            />
          </Card>
          <Card>
            <CardTitle title="Common knowledge gaps" subtitle="Topics most learners struggle with" action={<Link className="btn btn-ghost" to="/analytics">More →</Link>} />
            {projectId && <KnowledgeGapList projectId={projectId} limit={4} />}
          </Card>
        </div>
      </div>

      <div className="split section">
        <Card>
          <CardTitle title="Paths" action={<Link className="btn btn-ghost" to="/paths">All →</Link>} />
          {paths.length === 0 ? (
            <p className="muted">No paths yet.</p>
          ) : (
            <div className="row-list">
              {paths.slice(0, 5).map((p) => {
                const others = (p.members || []).filter((m) => m.user_id !== userId)
                const avg = others.length ? others.reduce((s, m) => s + (m.progress || 0), 0) / others.length : 0
                return (
                  <button key={p.id} className="row-btn" onClick={() => navigate(`/paths/${p.id}`)}>
                    <span>
                      <b style={{ fontSize: 14 }}>{p.target_role}</b>
                      <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                        {others.length} learner{others.length === 1 ? '' : 's'} · average {pct(avg)}
                      </span>
                    </span>
                    <span className="muted">Open →</span>
                  </button>
                )
              })}
            </div>
          )}
        </Card>
        <Card>
          <CardTitle title="Recent activity" subtitle="Your account in this workspace" />
          {(activity.data?.length ?? 0) === 0 ? (
            <p className="muted">No activity yet.</p>
          ) : (
            <div className="row-list">
              {activity.data!.map((e) => (
                <div key={e.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>{eventLabel(e.type)}</span>
                  <span className="muted">{timeAgo(e.created_at)}</span>
                </div>
              ))}
            </div>
          )}
          <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
            Team-wide activity needs <code>GET /api/projects/{'{id}'}/manager-summary</code>.
          </p>
        </Card>
      </div>

      <Drawer open={!!learner} onClose={() => setLearner(null)} title={learner?.name ?? ''}>
        {learner && (
          <div style={{ display: 'grid', gap: 18 }}>
            {learner.paths.map((p) => (
              <div key={p.id} className="card-flat">
                <b>{p.role}</b>
                <div style={{ margin: '8px 0 4px', display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>{pct(p.progress)} complete</span>
                  <span>
                    {p.xp} XP · streak {p.streak}
                  </span>
                </div>
                <ProgressBar value={p.progress} />
                <Link to={`/paths/${p.id}`} className="btn btn-ghost" style={{ paddingLeft: 0, marginTop: 6 }}>
                  Open path →
                </Link>
              </div>
            ))}
            {projectId && <LearnerSummary projectId={projectId} userId={learner.user_id} />}
          </div>
        )}
      </Drawer>
    </div>
  )
}
