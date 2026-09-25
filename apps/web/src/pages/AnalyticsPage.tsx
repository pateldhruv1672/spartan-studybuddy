import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { getProjectAnalytics, listDocuments } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { pct, usePathDetails } from '../app/hooks'
import { Badge } from '../components/primitives/Badge'
import { Card, CardTitle, StatCard } from '../components/primitives/Card'
import { EmptyState, ErrorState, Skeleton } from '../components/primitives/Feedback'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { KnowledgeGapList } from '../features/analytics/KnowledgeGaps'
import { MasteryHeatmap, QuizPerformance, ResourceCompletion } from '../features/analytics/AnalyticsPanels'

const FUNNEL = [
  { label: 'Enrolled', test: () => true },
  { label: 'Started', test: (p: number) => p > 0 },
  { label: 'Halfway', test: (p: number) => p >= 0.5 },
  { label: 'Completed', test: (p: number) => p >= 1 },
]

export function AnalyticsPage() {
  const { userId, projectId } = useSessionStore()
  const [params, setParams] = useSearchParams()
  const pathFilter = params.get('path')
  const { paths, loading } = usePathDetails()
  const docs = useQuery({ queryKey: ['documents', projectId], queryFn: () => listDocuments(projectId!), enabled: !!projectId })
  const isDemo = (docs.data || []).some((d) => d.metadata?.demo)
  const analytics = useQuery({ queryKey: ['project-analytics', projectId], queryFn: () => getProjectAnalytics(projectId!), enabled: !!projectId, retry: false })

  const scoped = pathFilter ? paths.filter((p) => p.id === pathFilter) : paths
  const enrollments = useMemo(
    () => scoped.flatMap((p) => (p.members || []).filter((m) => m.user_id !== userId).map((m) => ({ ...m, role: p.target_role, pathId: p.id }))),
    [scoped, userId]
  )
  const cohorts = useMemo(() => {
    const by = new Map<string, number[]>()
    for (const e of enrollments) by.set(e.role, [...(by.get(e.role) || []), e.progress || 0])
    return Array.from(by.entries()).map(([role, vals]) => ({ role, n: vals.length, avg: vals.reduce((a, b) => a + b, 0) / vals.length }))
  }, [enrollments])

  const avg = enrollments.length ? enrollments.reduce((s, e) => s + (e.progress || 0), 0) / enrollments.length : 0
  const totalXp = enrollments.reduce((s, e) => s + (e.xp || 0), 0)

  function setPath(id: string | null) {
    const next = new URLSearchParams(params)
    if (id) next.set('path', id)
    else next.delete('path')
    setParams(next, { replace: true })
  }

  if (!projectId) return null

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            ANALYTICS {isDemo && <Badge tone="warning">Demo data</Badge>}
          </p>
          <h1>Onboarding and competency insight.</h1>
          <p>
            Based on {enrollments.length} enrollment{enrollments.length === 1 ? '' : 's'} across {scoped.length} path{scoped.length === 1 ? '' : 's'}, measured as of now. No time-saved or productivity figures are shown without measured evidence.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 20 }}>
        <button className="chip-toggle" aria-pressed={!pathFilter} onClick={() => setPath(null)}>
          All paths
        </button>
        {paths.map((p) => (
          <button key={p.id} className="chip-toggle" aria-pressed={pathFilter === p.id} onClick={() => setPath(p.id)}>
            {p.target_role}
          </button>
        ))}
      </div>

      {loading ? (
        <Skeleton height={300} />
      ) : enrollments.length === 0 ? (
        <EmptyState title="Not enough data yet" description="Analytics appear once learners join a path and complete checkpoints." />
      ) : (
        <>
          <div className="grid-4">
            <StatCard label="Enrolled learners" value={String(enrollments.length)} />
            <StatCard label="Average progress" value={pct(avg)} />
            <StatCard label="Completed paths" value={String(enrollments.filter((e) => (e.progress || 0) >= 1).length)} />
            <StatCard label="XP earned" value={String(totalXp)} />
          </div>

          <div className="split section">
            <Card>
              <CardTitle title="Completion funnel" subtitle="How far enrolled learners have got" />
              <div style={{ display: 'grid', gap: 12 }}>
                {FUNNEL.map((step) => {
                  const n = enrollments.filter((e) => step.test(e.progress || 0)).length
                  return (
                    <div key={step.label}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                        <b>{step.label}</b>
                        <span>
                          {n} of {enrollments.length}
                        </span>
                      </div>
                      <ProgressBar value={n / enrollments.length} />
                    </div>
                  )
                })}
              </div>
            </Card>
            <Card>
              <CardTitle title="Cohort comparison" subtitle="Average progress by role" />
              <div style={{ display: 'grid', gap: 12 }}>
                {cohorts.map((c) => (
                  <div key={c.role}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                      <b>{c.role}</b>
                      <span>
                        {pct(c.avg)} · n={c.n}
                      </span>
                    </div>
                    <ProgressBar value={c.avg} />
                  </div>
                ))}
              </div>
              {cohorts.some((c) => c.n < 5) && (
                <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
                  Small samples (n &lt; 5) — treat differences as indicative only.
                </p>
              )}
            </Card>
          </div>

          <Card>
            <CardTitle title="Learner progress" />
            <table className="table">
              <caption>Every enrollment in the selected paths</caption>
              <thead>
                <tr>
                  <th scope="col">Learner</th>
                  <th scope="col">Path</th>
                  <th scope="col">Progress</th>
                  <th scope="col">XP</th>
                  <th scope="col">Streak</th>
                </tr>
              </thead>
              <tbody>
                {enrollments
                  .slice()
                  .sort((a, b) => (b.progress || 0) - (a.progress || 0))
                  .map((e) => (
                    <tr key={`${e.pathId}-${e.user_id}`}>
                      <td>
                        <b>{e.display_name || 'Learner'}</b>
                      </td>
                      <td>{e.role}</td>
                      <td style={{ width: 170 }}>
                        <span style={{ fontSize: 12 }}>{pct(e.progress)}</span>
                        <ProgressBar value={e.progress || 0} />
                      </td>
                      <td>{e.xp || 0}</td>
                      <td>{e.streak || 0}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <div className="grid-2 section">
        <Card className="span-2">
          <CardTitle title="Mastery heatmap" subtitle="Learners × topics, from quiz attempts" />
          {analytics.isLoading ? (
            <Skeleton height={140} />
          ) : analytics.isError ? (
            <ErrorState message={errorMessage(analytics.error)} onRetry={() => analytics.refetch()} />
          ) : (
            <MasteryHeatmap learners={analytics.data?.learners ?? []} />
          )}
        </Card>
        <Card>
          <CardTitle title="Knowledge gaps" subtitle="Concepts learners score lowest on" />
          <KnowledgeGapList projectId={projectId} limit={8} showPrompts />
        </Card>
        <Card>
          <CardTitle title="Quiz performance" subtitle="Pass rate and average score per section quiz" />
          {analytics.isLoading ? (
            <Skeleton height={140} />
          ) : analytics.isError ? (
            <ErrorState message={errorMessage(analytics.error)} onRetry={() => analytics.refetch()} />
          ) : (
            <QuizPerformance quizzes={analytics.data?.quizzes ?? []} />
          )}
        </Card>
        <Card>
          <CardTitle title="Resource completion" subtitle="Which curated resources get finished" />
          {analytics.isLoading ? (
            <Skeleton height={140} />
          ) : analytics.isError ? (
            <ErrorState message={errorMessage(analytics.error)} onRetry={() => analytics.refetch()} />
          ) : (
            <ResourceCompletion resources={analytics.data?.resources ?? []} />
          )}
        </Card>
      </div>
    </div>
  )
}
