import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getLeaderboard, getProjectAchievements } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { pct, usePathDetails } from '../app/hooks'
import { EmptyState, ErrorState, Skeleton } from '../components/primitives/Feedback'
import { Section, timeAgo } from '../components/primitives/Layout'
import { ProgressBar } from '../components/primitives/ProgressBar'

interface Row {
  user_id?: string
  name: string
  xp: number
  progress: number
}

export function LeaderboardPage() {
  const { userId, projectId } = useSessionStore()
  const [scope, setScope] = useState<string>('all')
  // Polling: XP events push over websocket only to the Employee who earned them, not to everyone
  // else viewing this board, so a plain default-staleTime refetch wouldn't pick up someone else's activity.
  const stats = useQuery({ queryKey: ['leaderboard', projectId, scope], queryFn: () => getLeaderboard(projectId!, scope === 'all' ? undefined : scope), enabled: !!projectId, refetchInterval: 15000 })
  const achievements = useQuery({ queryKey: ['achievements', 'project', projectId], queryFn: () => getProjectAchievements(projectId!), enabled: !!projectId, retry: false })
  const recent = [...(achievements.data ?? [])].sort((a, b) => b.earned_at.localeCompare(a.earned_at)).slice(0, 10)
  const { paths } = usePathDetails()

  const path = paths.find((p) => p.id === scope)
  const rows: Row[] = (stats.data?.leaderboard || []).map((r) => ({ user_id: r.user_id, name: r.display_name || 'Learner', xp: r.xp, progress: r.progress }))
  const myIndex = rows.findIndex((r) => r.user_id === userId)
  const top = rows[0]?.xp || 1

  return (
    <div className="view view-narrow">
      <div className="page-head page-head-center">
        <div>
          <p className="eyebrow">LEADERBOARD</p>
          <h1>Learning progress, not screen time.</h1>
          <p>All-time workspace XP: completed items earn their listed XP once; each quiz earns 30–70 XP on its first pass. Ties use completed items, then user ID.</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center', marginBottom: 20 }}>
        <button className="chip-toggle" aria-pressed={scope === 'all'} onClick={() => setScope('all')}>
          Whole team
        </button>
        {paths.map((p) => (
          <button key={p.id} className="chip-toggle" aria-pressed={scope === p.id} onClick={() => setScope(p.id)}>
            {p.target_role}
          </button>
        ))}
      </div>

      {myIndex >= 0 && (
        <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, background: 'var(--primary-tint)', boxShadow: 'none' }}>
          <div>
            <p className="eyebrow" style={{ margin: 0, color: 'var(--primary-strong)' }}>
              YOUR RANK
            </p>
            <b style={{ fontSize: 30 }}>#{myIndex + 1}</b> <span className="muted">of {rows.length}</span>
          </div>
          <div style={{ textAlign: 'right' }}>
            <b style={{ fontSize: 26, color: 'var(--coral-ink)' }}>{rows[myIndex].xp} XP</b>
            <div className="muted">{myIndex > 0 ? `${rows[myIndex - 1].xp - rows[myIndex].xp} XP to pass #${myIndex}` : 'You lead the board'}</div>
          </div>
        </div>
      )}

      {stats.isLoading ? (
        <Skeleton height={300} />
      ) : stats.isError ? <ErrorState message={errorMessage(stats.error)} onRetry={() => stats.refetch()} /> : rows.length === 0 ? (
        <EmptyState title="No one on the board yet" description="XP appears after the first completed checkpoint." />
      ) : (
        <div className="card">
          <table className="table">
            <caption>{path ? `${path.target_role} path` : 'Whole team'}, ranked by XP</caption>
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Learner</th>
                <th scope="col">Path progress</th>
                <th scope="col">XP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.user_id ?? i} style={r.user_id === userId ? { background: 'var(--primary-tint)' } : undefined}>
                  <td>
                    <b style={{ fontSize: 16, color: i < 3 ? 'var(--coral-ink)' : 'var(--ink-muted)' }}>{i + 1}</b>
                  </td>
                  <td>
                    <b>{r.name}</b> {r.user_id === userId && <span className="badge badge-info">You</span>}
                  </td>
                  <td style={{ width: 170 }}>
                    <span style={{ fontSize: 12 }}>{pct(r.progress)}</span>
                    <ProgressBar value={r.progress} />
                  </td>
                  <td style={{ width: 150 }}>
                    <b>{r.xp}</b>
                    <div style={{ height: 4, borderRadius: 2, background: 'var(--coral)', width: `${Math.max(4, (r.xp / top) * 100)}%`, marginTop: 4 }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Section eyebrow="RECENT ACHIEVEMENTS" title="Badges earned by the team">
        <div className="card">
          {achievements.isLoading ? (
            <Skeleton height={100} />
          ) : achievements.isError ? (
            <ErrorState message={errorMessage(achievements.error)} onRetry={() => achievements.refetch()} />
          ) : recent.length === 0 ? (
            <p className="muted">No badges earned yet. They appear when someone passes a section quiz or finishes a path.</p>
          ) : (
            <div className="row-list">
              {recent.map((a, i) => (
                <div key={`${a.user_id ?? ''}-${a.badge}-${i}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13, alignItems: 'center' }}>
                  <span>
                    <b>{a.display_name || 'Learner'}</b>
                    {a.user_id === userId && (
                      <>
                        {' '}
                        <span className="badge badge-info">You</span>
                      </>
                    )}{' '}
                    <span className="muted">earned</span> <span className="badge badge-coral">★ {a.title}</span>
                  </span>
                  <span className="muted">{timeAgo(a.earned_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
          <p className="muted">Rankings use persisted completions and first successful quiz attempts. Failed quizzes and repeated events earn no pass XP.</p>
        </div>
        <p className="muted" style={{ textAlign: 'center', marginTop: 14 }}>
          Want to hide your name? <Link to="/settings">Leaderboard settings</Link>
        </p>
      </Section>
    </div>
  )
}
