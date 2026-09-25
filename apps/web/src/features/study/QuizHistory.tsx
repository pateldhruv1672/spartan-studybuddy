import { useMutation, useQuery } from '@tanstack/react-query'
import { getQuizHint, getQuizHistory } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'
import { Button } from '../../components/primitives/Button'
import { ErrorState } from '../../components/primitives/Feedback'

export function QuizHint({ attemptId, questionId }: { attemptId: string; questionId: string }) {
  const { userId } = useSessionStore()
  const hint = useMutation({ mutationFn: () => getQuizHint(attemptId, questionId, userId) })
  return <div style={{ marginTop: 12 }}>
    <Button type="button" pending={hint.isPending} onClick={() => hint.mutate()}>Get hint</Button>
    {hint.data && <p role="status">{hint.data.hint}</p>}
    {hint.isError && <p role="alert">{errorMessage(hint.error)}</p>}
  </div>
}

export function QuizHistory({ pathId, itemId }: { pathId: string; itemId: string }) {
  const { userId } = useSessionStore()
  const history = useQuery({ queryKey: ['quiz-history', pathId, itemId, userId], queryFn: () => getQuizHistory(pathId, itemId, userId) })
  if (history.isError) return <ErrorState message={errorMessage(history.error)} onRetry={() => history.refetch()} />
  return <section aria-label="Quiz attempt history">
    <h3>Previous attempts</h3>
    {history.isLoading ? <p>Loading history…</p> : !history.data?.length ? <p>No attempts yet.</p> : history.data.map(a =>
      <details key={a.id}>
        <summary>Attempt {a.attempt_no} · {a.status === 'graded' ? (a.passed ? 'Passed' : 'Failed') : 'In progress'} · {a.score === null ? '—' : Math.round(a.score * 100) + '%'}</summary>
        {a.questions.map(q => {
          const result = a.results.find(r => r.question_id === q.id)
          const answer = a.answers[q.id]
          const chosen = (Array.isArray(answer) ? answer : [answer]).map(id => q.choices?.find(c => c.id === id)?.text || id).filter(Boolean).join(', ')
          return <article key={q.id} style={{ padding: 12 }}>
            <b>{q.prompt}</b><p>Your answer: {chosen || 'Not submitted'}</p>
            {result && <><p>{result.correct ? 'Correct' : 'Needs review'} · {result.explanation}</p><p>{result.feedback}</p>
              <p>{result.evidence.map(e => e.citation).join(' · ')}</p></>}
            {(a.hints[q.id] || []).map(h => <p key={h.level}>Hint {h.level}: {h.hint}</p>)}
            <QuizHint attemptId={a.id} questionId={q.id} />
          </article>
        })}
      </details>
    )}
  </section>
}
