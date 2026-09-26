import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { getQuiz, startQuiz, submitQuiz } from '../../api/endpoints'
import { QuizHistory, QuizHint } from './QuizHistory'
import { errorMessage, isAppError } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'
import { celebrateXp, toast } from '../../app/uiStore'
import { pct } from '../../app/hooks'
import { Button } from '../../components/primitives/Button'
import { Badge } from '../../components/primitives/Badge'
import { CitationChip } from '../../components/citations/CitationChip'
import { ErrorState, Skeleton } from '../../components/primitives/Feedback'
import { LockIcon } from '../../components/primitives/Icons'
import { ProgressBar, ProgressRing } from '../../components/primitives/ProgressBar'
import { DocumentDrawer, targetFromCitation, type DocTarget } from '../graph/DocumentDrawer'
import type { QuizAnswer, QuizAttempt, QuizInfo, QuizQuestion, QuizQuestionResult, QuizResult } from '../../api/types'

/** Shared with StudyPage so both see the same cached quiz info (and the same 404 for legacy checkpoints). */
export function useQuizInfo(pathId: string | undefined, itemId: string | undefined, enabled = true) {
  const { userId } = useSessionStore()
  return useQuery({
    queryKey: ['quiz', pathId, itemId, userId],
    queryFn: () => getQuiz(pathId!, itemId!, userId),
    enabled: enabled && !!pathId && !!itemId && !!userId,
    retry: false,
  })
}

export function isQuizMissing(error: unknown) {
  return isAppError(error) && error.status === 404
}

/* ---------- Session persistence (per user, path, item) ---------- */

interface Saved {
  attempt: QuizAttempt
  answers: Record<string, QuizAnswer>
}

function readSaved(key: string): Saved | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Saved
    return parsed?.attempt?.attempt_id && Array.isArray(parsed.attempt.questions) ? parsed : null
  } catch {
    return null
  }
}

function writeSaved(key: string, value: Saved | null) {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value))
    else sessionStorage.removeItem(key)
  } catch {
    /* storage unavailable */
  }
}

/** Order questions start in the presented order, so they always count as answered. */
function initialAnswers(questions: QuizQuestion[]): Record<string, QuizAnswer> {
  const out: Record<string, QuizAnswer> = {}
  for (const q of questions) if (q.type === 'order') out[q.id] = (q.choices || []).map((c) => c.id)
  return out
}

function isAnswered(q: QuizQuestion, a: QuizAnswer | undefined) {
  if (q.type === 'short') return typeof a === 'string' && a.trim().length > 0
  if (q.type === 'mcq') return typeof a === 'string' && a.length > 0
  return Array.isArray(a) && a.length > 0
}

/* ---------- Question inputs ---------- */

function McqInput({ q, value, onChange }: { q: QuizQuestion; value?: QuizAnswer; onChange: (v: QuizAnswer) => void }) {
  return (
    <div className="quiz-choices" role="radiogroup" aria-label={q.prompt}>
      {(q.choices || []).map((c) => (
        <label key={c.id} className={`quiz-choice${value === c.id ? ' selected' : ''}`}>
          <input type="radio" name={`q-${q.id}`} checked={value === c.id} onChange={() => onChange(c.id)} />
          <span>{c.text}</span>
        </label>
      ))}
    </div>
  )
}

function MultiInput({ q, value, onChange }: { q: QuizQuestion; value?: QuizAnswer; onChange: (v: QuizAnswer) => void }) {
  const picked = Array.isArray(value) ? value : []
  return (
    <div className="quiz-choices" role="group" aria-label={q.prompt}>
      {(q.choices || []).map((c) => {
        const on = picked.includes(c.id)
        return (
          <label key={c.id} className={`quiz-choice${on ? ' selected' : ''}`}>
            <input
              type="checkbox"
              checked={on}
              onChange={() => onChange(on ? picked.filter((id) => id !== c.id) : [...picked, c.id])}
            />
            <span>{c.text}</span>
          </label>
        )
      })}
    </div>
  )
}

function OrderInput({ q, value, onChange }: { q: QuizQuestion; value?: QuizAnswer; onChange: (v: QuizAnswer) => void }) {
  const choices = q.choices || []
  const order = Array.isArray(value) && value.length === choices.length ? value : choices.map((c) => c.id)
  const text = new Map(choices.map((c) => [c.id, c.text]))
  const [note, setNote] = useState('')
  const focusRef = useRef<string | null>(null)

  useEffect(() => {
    if (!focusRef.current) return
    document.getElementById(focusRef.current)?.focus()
    focusRef.current = null
  })

  function move(index: number, delta: -1 | 1) {
    const to = index + delta
    if (to < 0 || to >= order.length) return
    const next = [...order]
    ;[next[index], next[to]] = [next[to], next[index]]
    focusRef.current = `mv-${q.id}-${next[to]}-${delta === -1 ? 'up' : 'down'}`
    // If the moved item hit an end, its own button is disabled: fall back to the opposite button.
    if (to === 0 && delta === -1) focusRef.current = `mv-${q.id}-${next[to]}-down`
    if (to === order.length - 1 && delta === 1) focusRef.current = `mv-${q.id}-${next[to]}-up`
    setNote(`Moved "${text.get(order[index])}" to position ${to + 1} of ${order.length}`)
    onChange(next)
  }

  return (
    <div>
      <p className="muted" style={{ marginBottom: 8 }}>
        Put these in the right order using the arrow buttons.
      </p>
      <ol className="quiz-order" aria-label={q.prompt}>
        {order.map((id, i) => (
          <li key={id}>
            <span className="quiz-order-n" aria-hidden="true">
              {i + 1}
            </span>
            <span style={{ flex: 1 }}>{text.get(id) ?? id}</span>
            <button
              type="button"
              id={`mv-${q.id}-${id}-up`}
              className="btn btn-icon"
              disabled={i === 0}
              aria-label={`Move "${text.get(id) ?? id}" up`}
              onClick={() => move(i, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              id={`mv-${q.id}-${id}-down`}
              className="btn btn-icon"
              disabled={i === order.length - 1}
              aria-label={`Move "${text.get(id) ?? id}" down`}
              onClick={() => move(i, 1)}
            >
              ↓
            </button>
          </li>
        ))}
      </ol>
      <span className="sr-only" role="status" aria-live="polite">
        {note}
      </span>
    </div>
  )
}

function ShortInput({ q, value, onChange }: { q: QuizQuestion; value?: QuizAnswer; onChange: (v: QuizAnswer) => void }) {
  const id = `short-${q.id}`
  return (
    <div className="field">
      <label htmlFor={id} className="sr-only">
        Your answer
      </label>
      <textarea id={id} rows={4} value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value)} placeholder="Answer in a few sentences, in your own words." />
    </div>
  )
}

const TYPE_HINT: Record<QuizQuestion['type'], string> = {
  mcq: 'Choose one',
  multi: 'Choose all that apply',
  order: 'Put in order',
  short: 'Short answer',
}

/* ---------- Results ---------- */

function answerText(q: QuizQuestion, a: QuizAnswer | undefined): string {
  if (a == null || a === '' || (Array.isArray(a) && a.length === 0)) return 'No answer'
  if (q.type === 'short') return String(a)
  const text = new Map((q.choices || []).map((c) => [c.id, c.text]))
  if (Array.isArray(a)) return q.type === 'order' ? a.map((id, i) => `${i + 1}. ${text.get(id) ?? id}`).join('  ') : a.map((id) => text.get(id) ?? id).join(', ')
  return text.get(a) ?? a
}

function correctText(q: QuizQuestion, ids: string[] | undefined): string | null {
  if (!ids?.length) return null
  const text = new Map((q.choices || []).map((c) => [c.id, c.text]))
  if (q.type === 'order') return ids.map((id, i) => `${i + 1}. ${text.get(id) ?? id}`).join('  ')
  return ids.map((id) => text.get(id) ?? id).join(', ')
}

function ResultRow({ index, q, r, answer, onOpen }: { index: number; q: QuizQuestion; r?: QuizQuestionResult; answer?: QuizAnswer; onOpen: (t: DocTarget) => void }) {
  const state = r?.correct === true ? 'correct' : r?.correct === false ? 'incorrect' : 'ungraded'
  const correct = correctText(q, r?.correct_answer)
  return (
    <li className={`quiz-result-row ${state}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <p style={{ fontSize: 15 }}>
          <b>
            {index + 1}. {q.prompt}
          </b>
        </p>
        {state === 'correct' ? (
          <Badge tone="success">Correct</Badge>
        ) : state === 'incorrect' ? (
          <Badge tone="danger">{r && r.score > 0 ? `Partly right · ${pct(r.score)}` : 'Incorrect'}</Badge>
        ) : (
          <Badge tone="neutral">Not auto-graded</Badge>
        )}
      </div>
      <p className="muted" style={{ marginTop: 6 }}>
        Your answer: <span style={{ color: 'var(--ink)' }}>{answerText(q, answer)}</span>
      </p>
      {state !== 'correct' && correct && (
        <p className="muted">
          Correct answer: <b style={{ color: 'var(--success-ink)' }}>{correct}</b>
        </p>
      )}
      {r?.explanation && <p style={{ fontSize: 14, lineHeight: 1.6, marginTop: 8 }}>{r.explanation}</p>}
      {r?.feedback && (
        <p className="quiz-feedback">
          {r.feedback}
          {r.graded_by !== 'exact' && <span className="muted"> · graded by {r.graded_by === 'llm' ? 'the local model' : 'keyword match'}</span>}
        </p>
      )}
      {(r?.evidence?.length ?? 0) > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {r!.evidence.map((ev, i) => (
            <CitationChip key={i} citation={ev.citation} onOpen={() => onOpen(targetFromCitation(ev.citation, ev.path, ev.start_line, ev.end_line))} />
          ))}
        </div>
      )}
    </li>
  )
}

function Results({
  result,
  attempt,
  answers,
  onRetake,
  retaking,
  onContinue,
  canContinue,
  onOpen,
}: {
  result: QuizResult
  attempt: QuizAttempt
  answers: Record<string, QuizAnswer>
  onRetake: () => void
  retaking: boolean
  onContinue: () => void
  canContinue: boolean
  onOpen: (t: DocTarget) => void
}) {
  const byQuestion = new Map(result.results.map((r) => [r.question_id, r]))
  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <div className={`card quiz-summary ${result.passed ? 'passed' : 'failed'}`}>
        <ProgressRing value={result.score} size={104} />
        <div style={{ display: 'grid', gap: 8, alignContent: 'center' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {result.passed ? <Badge tone="success">Passed</Badge> : <Badge tone="warning">Not yet</Badge>}
            <span className="muted">Needed {pct(result.pass_threshold)} to pass</span>
            {result.xp_delta > 0 && <Badge tone="coral">+{result.xp_delta} XP</Badge>}
          </div>
          <h2 style={{ fontSize: 24 }}>
            {result.passed ? 'Section unlocked. Nicely done.' : 'Close. Review and try again.'}
          </h2>
          <p className="muted">
            You scored {pct(result.score)} on attempt {attempt.attempt_no}. Your best score counts, and you can retake it as often as you like. Questions are redrawn each time.
          </p>
        </div>
      </div>

      {result.achievements.length > 0 && (
        <div className="card-flat" style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <b style={{ fontSize: 13 }}>Achievement unlocked</b>
          {result.achievements.map((a) => (
            <Badge key={a.badge} tone="coral">
              ★ {a.title}
            </Badge>
          ))}
        </div>
      )}

      {result.weak_concepts.length > 0 && (
        <div className="card-flat">
          <p className="eyebrow">WORTH REVISITING</p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {result.weak_concepts.map((w) => (
              <Link key={w.concept} className="badge badge-warning" style={{ textDecoration: 'none' }} to={`/repository?q=${encodeURIComponent(w.name)}`}>
                {w.name}
              </Link>
            ))}
          </div>
          {result.review.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 14 }}>
                REVIEW THESE
              </p>
              <div className="row-list">
                {result.review.map((rv, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Link to={`/repository?q=${encodeURIComponent(rv.path || rv.title)}`}>
                      <b style={{ fontSize: 14 }}>{rv.title}</b>
                    </Link>
                    {rv.citation && <CitationChip citation={rv.citation} onOpen={() => onOpen(targetFromCitation(rv.citation!, rv.path))} />}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="card">
        <CardHeading count={attempt.questions.length} />
        <ol className="quiz-results">
          {attempt.questions.map((q, i) => (
            <ResultRow key={q.id} index={i} q={q} r={byQuestion.get(q.id)} answer={answers[q.id]} onOpen={onOpen} />
          ))}
        </ol>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {canContinue && (
          <Button variant="primary" onClick={onContinue}>
            Continue to next section →
          </Button>
        )}
        <Button variant={canContinue ? 'secondary' : 'primary'} pending={retaking} onClick={onRetake}>
          {result.passed ? 'Retake for practice' : 'Retake quiz'}
        </Button>
      </div>
    </div>
  )
}

function CardHeading({ count }: { count: number }) {
  return (
    <p className="eyebrow" style={{ marginBottom: 12 }}>
      QUESTION BY QUESTION ({count})
    </p>
  )
}

/* ---------- Main ---------- */

interface Props {
  /** Callers must pass `key={pathId:itemId}` so state resets when the learner switches quiz. */
  pathId: string
  itemId: string
  /** Item to open after this quiz (the outline's next step). */
  nextItemId?: string | null
  /** Rendered when the quiz endpoint 404s: the legacy free-text checkpoint. */
  legacy?: React.ReactNode
}

export function QuizView({ pathId, itemId, nextItemId, legacy }: Props) {
  const { userId } = useSessionStore()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const storageKey = `quiz:${userId}:${pathId}:${itemId}`
  const info = useQuizInfo(pathId, itemId)

  const [attempt, setAttempt] = useState<QuizAttempt | null>(() => readSaved(storageKey)?.attempt ?? null)
  const [answers, setAnswers] = useState<Record<string, QuizAnswer>>(() => readSaved(storageKey)?.answers ?? {})
  const [result, setResult] = useState<{ result: QuizResult; attempt: QuizAttempt; answers: Record<string, QuizAnswer> } | null>(null)
  const [source, setSource] = useState<DocTarget | null>(null)
  const [resumed] = useState(() => !!readSaved(storageKey))

  // Answers survive reloads and navigation for the lifetime of the session.
  useEffect(() => {
    if (attempt && !result) writeSaved(storageKey, { attempt, answers })
  }, [attempt, answers, result, storageKey])

  const refresh = () => {
    for (const key of [['path'], ['paths'], ['learner'], ['activity'], ['manager-analytics'], ['leaderboard'], ['quiz-history'], ['quiz', pathId], ['achievements'], ['knowledge-gaps'], ['quiz-list']]) {
      qc.invalidateQueries({ queryKey: key })
    }
  }

  const start = useMutation({
    mutationFn: () => startQuiz(pathId, itemId, userId),
    onSuccess: (a) => {
      const init = initialAnswers(a.questions)
      setAttempt(a)
      setAnswers(init)
      setResult(null)
      writeSaved(storageKey, { attempt: a, answers: init })
    },
    onError: (e) => {
      toast(isAppError(e) && e.status === 423 ? 'This quiz is locked. Pass the previous section first.' : errorMessage(e))
      qc.invalidateQueries({ queryKey: ['quiz', pathId, itemId] })
    },
  })

  const submit = useMutation({
    mutationFn: () => submitQuiz(attempt!.attempt_id, { user_id: userId, answers }),
    onSuccess: (r) => {
      setResult({ result: r, attempt: attempt!, answers })
      setAttempt(null)
      writeSaved(storageKey, null)
      if (r.xp_delta > 0) celebrateXp(r.xp_delta)
      if (r.achievements.length > 0) toast(`Achievement unlocked: ${r.achievements.map((a) => a.title).join(', ')}`)
      else if (r.passed) toast('Quiz passed')
      refresh()
    },
    onError: (e) => toast(errorMessage(e)),
  })

  const answered = useMemo(() => (attempt ? attempt.questions.filter((q) => isAnswered(q, answers[q.id])).length : 0), [attempt, answers])

  if (info.isLoading) return <Skeleton height={220} />
  if (info.isError) {
    if (isQuizMissing(info.error)) return <>{legacy ?? <ErrorState message="This step has no quiz." />}</>
    return <ErrorState message={errorMessage(info.error)} onRetry={() => info.refetch()} />
  }
  const quiz = info.data as QuizInfo

  if (result) {
    const target = result.result.next_unlocked ?? nextItemId ?? null
    return (
      <>
        <Results
          result={result.result}
          attempt={result.attempt}
          answers={result.answers}
          onRetake={() => start.mutate()}
          retaking={start.isPending}
          onContinue={() => target && navigate(`/study/${pathId}/${target}`)}
          canContinue={result.result.passed && !!target}
          onOpen={setSource}
        />
        <DocumentDrawer target={source} onClose={() => setSource(null)} />
      </>
    )
  }

  if (attempt) {
    const ready = answered === attempt.questions.length
    return (
      <form
        className="card"
        style={{ display: 'grid', gap: 22 }}
        onSubmit={(e) => {
          e.preventDefault()
          if (ready && !submit.isPending) submit.mutate()
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <p className="eyebrow" style={{ margin: 0 }}>
              ATTEMPT {attempt.attempt_no}
              {resumed && ' · RESUMED'}
            </p>
            <b style={{ fontSize: 16 }}>{quiz.title}</b>
          </div>
          <div style={{ minWidth: 160 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
              <span>Answered</span>
              <b>
                {answered} of {attempt.questions.length}
              </b>
            </div>
            <ProgressBar value={attempt.questions.length ? answered / attempt.questions.length : 0} />
          </div>
        </div>

        {attempt.questions.map((q, i) => (
          <fieldset key={q.id} className="quiz-question">
            <legend>
              <span className="muted">
                Question {i + 1} of {attempt.questions.length} · {TYPE_HINT[q.type]}
              </span>
            </legend>
            <p style={{ fontSize: 17, lineHeight: 1.55, marginBottom: 12 }}>
              <b>{q.prompt}</b>
            </p>
            {q.type === 'mcq' && <McqInput q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />}
            {q.type === 'multi' && <MultiInput q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />}
            {q.type === 'order' && <OrderInput q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />}
            {q.type === 'short' && <ShortInput q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />}
            <QuizHint attemptId={attempt.attempt_id} questionId={q.id} />
          </fieldset>
        ))}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span className="muted">{ready ? 'All answered. Submit when you are ready.' : `Answer every question to submit (${attempt.questions.length - answered} left).`}</span>
          <Button type="submit" variant="primary" disabled={!ready} pending={submit.isPending}>
            {submit.isPending ? 'Grading…' : 'Submit answers'}
          </Button>
        </div>
      </form>
    )
  }

  return (
    <div className="card" style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div>
          <p className="eyebrow" style={{ margin: 0 }}>
            SECTION QUIZ
          </p>
          <h2 style={{ fontSize: 22 }}>{quiz.title}</h2>
        </div>
        {quiz.passed ? (
          <Badge tone="success">Passed</Badge>
        ) : quiz.locked ? (
          <Badge tone="neutral">Locked</Badge>
        ) : (
          <Badge tone="info">Not passed yet</Badge>
        )}
      </div>

      <div className="quiz-stats">
        <div>
          <b>{quiz.question_count}</b>
          <span>questions</span>
        </div>
        <div>
          <b>{pct(quiz.pass_threshold)}</b>
          <span>to pass</span>
        </div>
        <div>
          <b>{quiz.attempts}</b>
          <span>attempt{quiz.attempts === 1 ? '' : 's'}</span>
        </div>
        <div>
          <b>{quiz.best_score == null ? '—' : pct(quiz.best_score)}</b>
          <span>best score</span>
        </div>
      </div>

      <QuizHistory pathId={pathId} itemId={itemId} />
      {quiz.locked ? (
        <div className="lock-panel" role="status">
          <LockIcon size={18} />
          <div>
            <b>Locked</b>
            <p className="muted">{quiz.lock_reason || "Pass the previous section's quiz to unlock this one."}</p>
          </div>
        </div>
      ) : (
        <>
          <p className="muted" style={{ lineHeight: 1.6 }}>
            Questions are drawn from the code and docs you just studied and are redrawn on every attempt. Passing completes this section and unlocks the next. You can retake it as often as you like, and your best score counts.
          </p>
          <div>
            <Button variant="primary" pending={start.isPending} onClick={() => start.mutate()}>
              {quiz.attempts > 0 ? (quiz.passed ? 'Retake for practice' : 'Retake quiz') : 'Start quiz'}
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
