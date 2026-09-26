import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { getLeaderboard, getProjectAnalytics, listDocuments, listProjects, listTeam } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { pct, usePathDetails } from '../app/hooks'
import { Badge } from '../components/primitives/Badge'
import { Card, CardTitle, StatCard } from '../components/primitives/Card'
import { EmptyState, ErrorState, Skeleton } from '../components/primitives/Feedback'
import { Section, timeAgo } from '../components/primitives/Layout'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { KnowledgeGapList } from '../features/analytics/KnowledgeGaps'
import { MasteryHeatmap, QuizPerformance, ResourceCompletion } from '../features/analytics/AnalyticsPanels'

const FUNNEL = [
  { label: 'Enrolled', test: () => true },
  { label: 'Started', test: (p: number) => p > 0 },
  { label: 'Halfway', test: (p: number) => p >= 0.5 },
  { label: 'Completed', test: (p: number) => p >= 1 },
]

const RECENT_DAYS = 14
const STALE_ENROLLMENT_DAYS = 3

type Status = 'Not started' | 'In progress' | 'Completed'

function daysAgo(iso?: string | null) {
  if (!iso) return Infinity
  return (Date.now() - new Date(iso).getTime()) / 86400000
}

export function AnalyticsPage() {
  const { orgId, projectId } = useSessionStore()
  const [params, setParams] = useSearchParams()
  const pathFilter = params.get('path')
  const { paths, loading } = usePathDetails()
  const docs = useQuery({ queryKey: ['documents', projectId], queryFn: () => listDocuments(projectId!), enabled: !!projectId })
  const isDemo = (docs.data || []).some((d) => d.metadata?.demo)
  const analytics = useQuery({ queryKey: ['project-analytics', projectId], queryFn: () => getProjectAnalytics(projectId!), enabled: !!projectId, retry: false })
  // Polling, same reasoning as the Team page: an Employee's quiz/progress event only pushes to that
  // Employee's own websocket connection, never to the Manager watching this page.
  const team = useQuery({ queryKey: ['team', orgId], queryFn: () => listTeam(orgId), refetchInterval: 15000 })
  const workspaces = useQuery({ queryKey: ['projects', orgId], queryFn: () => listProjects(orgId) })
  const leaderboard = useQuery({ queryKey: ['leaderboard', projectId], queryFn: () => getLeaderboard(projectId!), enabled: !!projectId, refetchInterval: 15000 })
  const workspaceName = (workspaces.data || []).find((w) => w.id === projectId)?.name

  // The Team roster (app_role) is the source of truth for who is an Employee. A path's member list
  // alone isn't enough: a Manager who creates a path auto-enrolls as its creator (see leaderboard.py),
  // so filtering only the current viewer out (as this page used to) still let a *second* manager leak in.
  const employees = useMemo(() => (team.data || []).filter((m) => m.app_role !== 'manager'), [team.data])
  const employeeIds = useMemo(() => new Set(employees.map((e) => e.id)), [employees])

  const scoped = pathFilter ? paths.filter((p) => p.id === pathFilter) : paths
  const enrollments = useMemo(
    () => scoped.flatMap((p) => (p.members || []).filter((m) => employeeIds.has(m.user_id)).map((m) => ({ ...m, role: p.target_role, pathId: p.id }))),
    [scoped, employeeIds]
  )
  // Workspace-wide (ignores the path-role chips below) -- summary cards answer "how is the whole team
  // doing", not just the currently selected path.
  const allEnrollments = useMemo(
    () => paths.flatMap((p) => (p.members || []).filter((m) => employeeIds.has(m.user_id)).map((m) => ({ ...m, role: p.target_role, pathId: p.id }))),
    [paths, employeeIds]
  )
  const bestByUser = useMemo(() => {
    const map = new Map<string, (typeof allEnrollments)[number]>()
    for (const e of allEnrollments) {
      const cur = map.get(e.user_id)
      if (!cur || (e.progress || 0) > (cur.progress || 0)) map.set(e.user_id, e)
    }
    return map
  }, [allEnrollments])

  const cohorts = useMemo(() => {
    const by = new Map<string, number[]>()
    for (const e of enrollments) by.set(e.role, [...(by.get(e.role) || []), e.progress || 0])
    return Array.from(by.entries()).map(([role, vals]) => ({ role, n: vals.length, avg: vals.reduce((a, b) => a + b, 0) / vals.length }))
  }, [enrollments])

  const avg = enrollments.length ? enrollments.reduce((s, e) => s + (e.progress || 0), 0) / enrollments.length : 0
  const totalXp = enrollments.reduce((s, e) => s + (e.xp || 0), 0)

  const quizByUser = useMemo(() => new Map((analytics.data?.learners || []).map((l) => [l.user_id, l])), [analytics.data])
  const lastActivity = analytics.data?.last_activity || {}

  function statusOf(userId: string): Status {
    const best = bestByUser.get(userId)
    const quiz = quizByUser.get(userId)
    if ((best?.progress || 0) >= 1) return 'Completed'
    if ((best?.progress || 0) > 0 || (quiz?.quizzes_attempted || 0) > 0) return 'In progress'
    return 'Not started'
  }

  const summary = useMemo(() => {
    const withPath = employees.filter((e) => bestByUser.has(e.id))
    const withActivity = employees.filter((e) => statusOf(e.id) !== 'Not started')
    const activeRecent = employees.filter((e) => daysAgo(lastActivity[e.id]) <= RECENT_DAYS)
    const completedSomething = employees.filter((e) => (bestByUser.get(e.id)?.progress || 0) >= 1 || (quizByUser.get(e.id)?.quizzes_passed || 0) > 0)
    const quizParticipants = employees.filter((e) => (quizByUser.get(e.id)?.quizzes_attempted || 0) > 0)
    const avgProgress = withPath.length ? withPath.reduce((s, e) => s + (bestByUser.get(e.id)?.progress || 0), 0) / withPath.length : 0
    const needsAttention = withPath
      .map((e) => ({ member: e, best: bestByUser.get(e.id)! }))
      .filter(({ best }) => (best.progress || 0) < 0.15 && daysAgo(best.joined_at) >= STALE_ENROLLMENT_DAYS)
    return { withPath, withActivity, activeRecent, completedSomething, quizParticipants, avgProgress, needsAttention }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employees, bestByUser, quizByUser, lastActivity])

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
            ANALYTICS · {workspaceName || 'WORKSPACE'} {isDemo && <Badge tone="warning">Demo data</Badge>}
          </p>
          <h1>Who joined, who's progressing, who needs a nudge.</h1>
          <p>
            {employees.length} employee{employees.length === 1 ? '' : 's'} in this organization, {summary.withPath.length} on a learning path here. No time-saved or productivity figures are shown without measured evidence.
          </p>
        </div>
      </div>

      {team.isLoading || loading ? (
        <Skeleton height={100} />
      ) : employees.length === 0 ? (
        <EmptyState title="No employees yet" description="Analytics appear once Employees sign up or accept an invite." />
      ) : (
        <>
          <div className="grid-4">
            <StatCard label="Total employees" value={String(employees.length)} />
            <StatCard label="Employees with a learning path" value={String(summary.withPath.length)} />
            <StatCard label="Employees with activity" value={String(summary.withActivity.length)} />
            <StatCard label="Average progress" value={pct(summary.avgProgress)} />
          </div>
          <div className="grid-3 section">
            <StatCard label={`Active in last ${RECENT_DAYS}d`} value={String(summary.activeRecent.length)} />
            <StatCard label="Completed something" value={String(summary.completedSomething.length)} />
            <StatCard label="Quiz participation" value={employees.length ? pct(summary.quizParticipants.length / employees.length) : '0%'} />
          </div>

          {summary.needsAttention.length > 0 && (
            <Card className="section">
              <CardTitle title="May need attention" subtitle={`Enrolled ${STALE_ENROLLMENT_DAYS}+ days ago, still under 15% progress`} />
              <div className="row-list">
                {summary.needsAttention.slice(0, 8).map(({ member, best }) => (
                  <div key={member.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '6px 0' }}>
                    <span>
                      <b>{member.display_name}</b> <span className="muted">{best.role}</span>
                    </span>
                    <span className="muted">{pct(best.progress)} · enrolled {timeAgo(best.joined_at)}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '20px 0' }}>
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
        <EmptyState title="Not enough data for this path yet" description="Analytics appear once employees join a path and complete checkpoints." />
      ) : (
        <div className="split section">
          <Card>
            <CardTitle title="Completion funnel" subtitle="How far enrolled employees have got" />
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
      )}

      <Card className="section">
        <CardTitle title="Employee progress" subtitle="Every employee in this organization, whether or not they've started" />
        <table className="table">
          <caption>{employees.length} employees · {totalXp} XP earned on {pathFilter ? 'the selected path' : 'all paths'}</caption>
          <thead>
            <tr>
              <th scope="col">Employee</th>
              <th scope="col">Job role</th>
              <th scope="col">Learning path</th>
              <th scope="col">Progress</th>
              <th scope="col">XP</th>
              <th scope="col">Quiz attempts</th>
              <th scope="col">Last activity</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {employees
              .slice()
              .sort((a, b) => (bestByUser.get(b.id)?.progress || 0) - (bestByUser.get(a.id)?.progress || 0))
              .map((e) => {
                const best = bestByUser.get(e.id)
                const quiz = quizByUser.get(e.id)
                const status = statusOf(e.id)
                return (
                  <tr key={e.id}>
                    <td>
                      <b>{e.display_name}</b>
                    </td>
                    <td>{e.role_title || '—'}</td>
                    <td>{best?.role || '—'}</td>
                    <td style={{ width: 170 }}>
                      <span style={{ fontSize: 12 }}>{pct(best?.progress)}</span>
                      <ProgressBar value={best?.progress || 0} />
                    </td>
                    <td>{best?.xp || 0}</td>
                    <td>{quiz?.quizzes_attempted || 0}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{timeAgo(lastActivity[e.id])}</td>
                    <td>
                      <span className={`badge ${status === 'Completed' ? 'badge-success' : status === 'In progress' ? 'badge-warning' : 'badge-neutral'}`}>{status}</span>
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </Card>

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

      <Section eyebrow="LEADERBOARD" title="Top performers on this workspace's leaderboard">
        <Card>
          {leaderboard.isLoading ? (
            <Skeleton height={100} />
          ) : (leaderboard.data?.leaderboard.length ?? 0) === 0 ? (
            <p className="muted">No one has earned XP yet.</p>
          ) : (
            <div className="row-list">
              {leaderboard.data!.leaderboard.slice(0, 5).map((r, i) => (
                <div key={r.user_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '6px 0' }}>
                  <span>
                    <b style={{ color: i < 3 ? 'var(--coral-ink)' : undefined }}>#{i + 1}</b> {r.display_name || 'Employee'}
                  </span>
                  <span className="muted">{r.xp} XP · {pct(r.progress)}</span>
                </div>
              ))}
            </div>
          )}
          <p style={{ marginTop: 12 }}>
            <Link to="/leaderboard">View full leaderboard →</Link>
          </p>
        </Card>
      </Section>
    </div>
  )
}
