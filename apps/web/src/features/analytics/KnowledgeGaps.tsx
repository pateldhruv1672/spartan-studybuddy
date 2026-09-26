import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getKnowledgeGaps } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { pct } from '../../app/hooks'
import { ErrorState, Skeleton } from '../../components/primitives/Feedback'
import { ProgressBar } from '../../components/primitives/ProgressBar'

/** Concepts the team scores lowest on, aggregated from quiz attempts. Contains no private conversations. */
export function KnowledgeGapList({ projectId, limit = 6, showPrompts = false }: { projectId: string; limit?: number; showPrompts?: boolean }) {
  const gaps = useQuery({ queryKey: ['knowledge-gaps', projectId], queryFn: () => getKnowledgeGaps(projectId), retry: false })

  if (gaps.isLoading) return <Skeleton height={120} />
  if (gaps.isError) return <ErrorState message={errorMessage(gaps.error)} onRetry={() => gaps.refetch()} />
  // Weakest first, so the list works even if the server does not sort.
  const list = [...(gaps.data?.gaps ?? [])].sort((a, b) => a.avg_score - b.avg_score).slice(0, limit)
  if (list.length === 0) {
    return <p className="muted">No gaps yet. They show up once learners have taken section quizzes.</p>
  }
  return (
    <div className="row-list">
      {list.map((g) => (
        <div key={g.concept}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, marginBottom: 4 }}>
            <Link to={`/repository?q=${encodeURIComponent(g.name)}`} style={{ fontWeight: 700 }}>
              {g.name}
            </Link>
            <span>
              {pct(g.avg_score)} avg · {g.learners} learner{g.learners === 1 ? '' : 's'}
            </span>
          </div>
          <ProgressBar value={g.avg_score} />
          <span className="muted" style={{ fontSize: 11 }}>
            {g.attempts} attempt{g.attempts === 1 ? '' : 's'}
          </span>
          {showPrompts && g.weak_prompts.length > 0 && (
            <ul className="reason-list" aria-label={`Questions learners missed on ${g.name}`}>
              {g.weak_prompts.slice(0, 2).map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  )
}
