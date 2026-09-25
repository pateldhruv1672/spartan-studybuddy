import { useQuery } from '@tanstack/react-query'
import { getProjectAnalytics } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { pct } from '../../app/hooks'
import { ErrorState, Skeleton } from '../../components/primitives/Feedback'

export function LearnerSummary({ projectId, userId }: { projectId: string; userId: string }) {
  const analytics = useQuery({ queryKey: ['project-analytics', projectId], queryFn: () => getProjectAnalytics(projectId) })
  if (analytics.isLoading) return <Skeleton height={100} />
  if (analytics.isError) return <ErrorState message={errorMessage(analytics.error)} onRetry={() => analytics.refetch()} />
  const learner = analytics.data?.learners.find(l => l.user_id === userId)
  if (!learner) return <p>No recorded quiz activity for this learner yet.</p>
  return <section>
    <h3>Recorded learning outcomes</h3>
    <p>{learner.quizzes_passed} quizzes passed · {learner.quizzes_attempted} attempted · {pct(learner.avg_score)} average score</p>
    {learner.mastery.length ? learner.mastery.map(m => <p key={m.topic}>{m.topic}: {pct(m.score)}</p>) : <p>No measured concept mastery yet.</p>}
  </section>
}
