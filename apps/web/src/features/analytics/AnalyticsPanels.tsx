import { useMemo } from 'react'
import { pct } from '../../app/hooks'
import { ProgressBar } from '../../components/primitives/ProgressBar'
import type { LearnerAnalytics, QuizAnalytics, ResourceAnalytics } from '../../api/types'

const MAX_TOPICS = 8

/** Learners x topics mastery, colored by score. Every cell also prints its value, so color is never the only signal. */
export function MasteryHeatmap({ learners }: { learners: LearnerAnalytics[] }) {
  const topics = useMemo(() => {
    const counts = new Map<string, number>()
    for (const l of learners) for (const m of l.mastery) counts.set(m.topic, (counts.get(m.topic) ?? 0) + 1)
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, MAX_TOPICS)
      .map(([t]) => t)
  }, [learners])

  if (learners.length === 0 || topics.length === 0) {
    return <p className="muted">No mastery data yet. Mastery is measured from quiz attempts, not from reading time.</p>
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="table heatmap">
        <caption>Mastery score by learner and topic (0 to 100)</caption>
        <thead>
          <tr>
            <th scope="col">Learner</th>
            {topics.map((t) => (
              <th key={t} scope="col" title={t}>
                {t.length > 14 ? `${t.slice(0, 13)}…` : t}
              </th>
            ))}
            <th scope="col">Quizzes</th>
          </tr>
        </thead>
        <tbody>
          {learners.map((l) => {
            const byTopic = new Map(l.mastery.map((m) => [m.topic, m.score]))
            return (
              <tr key={l.user_id}>
                <th scope="row">{l.display_name || 'Learner'}</th>
                {topics.map((t) => {
                  const score = byTopic.get(t)
                  return (
                    <td key={t} className="heat-td">
                      {score == null ? (
                        <span className="heat-cell heat-empty" aria-label="No data">
                          –
                        </span>
                      ) : (
                        <span
                          className="heat-cell"
                          style={{ background: `color-mix(in srgb, var(--success) ${Math.round(Math.max(0, Math.min(1, score)) * 85)}%, var(--warning-tint))` }}
                        >
                          {Math.round(score * 100)}
                        </span>
                      )}
                    </td>
                  )
                })}
                <td>
                  <span style={{ whiteSpace: 'nowrap' }}>
                    {l.quizzes_passed}/{l.quizzes_attempted}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function QuizPerformance({ quizzes }: { quizzes: QuizAnalytics[] }) {
  if (quizzes.length === 0) return <p className="muted">No quiz attempts yet.</p>
  const sorted = [...quizzes].sort((a, b) => a.pass_rate - b.pass_rate)
  return (
    <div className="row-list">
      {sorted.map((q) => (
        <div key={`${q.path_id}-${q.item_id}`}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, marginBottom: 4 }}>
            <b>{q.title}</b>
            <span>
              {pct(q.pass_rate)} pass · {pct(q.avg_score)} avg
            </span>
          </div>
          <ProgressBar value={q.pass_rate} />
          <span className="muted" style={{ fontSize: 11 }}>
            {q.attempts} attempt{q.attempts === 1 ? '' : 's'}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Which curated resources (articles, videos, docs) the team actually finishes, from persisted resource-session progress. */
export function ResourceCompletion({ resources }: { resources: ResourceAnalytics[] }) {
  if (resources.length === 0) return <p className="muted">No resource activity yet.</p>
  const sorted = [...resources].sort((a, b) => a.completion_rate - b.completion_rate)
  return (
    <div className="row-list">
      {sorted.map((r) => (
        <div key={r.url}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, marginBottom: 4 }}>
            <b style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.title}</b>
            <span style={{ flex: '0 0 auto' }}>
              {pct(r.completion_rate)} completed · {pct(r.avg_progress)} avg progress
            </span>
          </div>
          <ProgressBar value={r.completion_rate} />
          <span className="muted" style={{ fontSize: 11 }}>
            {r.sessions} session{r.sessions === 1 ? '' : 's'}
            {r.resource_type ? ` · ${r.resource_type}` : ''}
          </span>
        </div>
      ))}
    </div>
  )
}
