import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { askAssistant, sendEvent } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'
import { CitationList } from '../../components/citations/CitationChip'
import type { AskResponse } from '../../api/types'

const HINT_LABELS = ['Nudge', 'Pointer', 'Approach', 'Walkthrough', 'Near-solution']

/** Socratic side panel: each "Next hint" raises the hint level so help gets progressively more specific. */
export function TutorPanel({ pathId, itemId, context }: { pathId: string; itemId: string; context: string }) {
  const { userId, projectId } = useSessionStore()
  const [level, setLevel] = useState(0)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Array<{ q: string; a?: AskResponse; error?: string }>>([])

  const ask = useMutation({
    mutationFn: ({ q, hintLevel }: { q: string; hintLevel: number }) =>
      askAssistant({
        user_id: userId,
        project_id: projectId!,
        question: `${q}\n\nContext: I'm working on "${context}".`,
        mode: 'socratic',
        hint_level: hintLevel,
        allow_final_answer: false,
      }),
    onSuccess: (a) =>
      setTurns((t) => {
        const next = [...t]
        next[next.length - 1] = { ...next[next.length - 1], a }
        return next
      }),
    onError: (e) =>
      setTurns((t) => {
        const next = [...t]
        next[next.length - 1] = { ...next[next.length - 1], error: errorMessage(e) }
        return next
      }),
  })

  function requestHint(q: string) {
    const hintLevel = Math.min(level + 1, 5)
    setLevel(hintLevel)
    setTurns((t) => [...t, { q }])
    ask.mutate({ q, hintLevel })
    sendEvent({ user_id: userId, project_id: projectId ?? undefined, type: 'code.hint_requested', resource_id: itemId, context: { path_id: pathId, hint_level: hintLevel } }).catch(() => {})
  }

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 'calc(100vh - 160px)' }}>
      <div>
        <p className="eyebrow" style={{ margin: 0 }}>
          STUDYBUDDY TUTOR
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          Hints get more specific each time. It won't hand you the full solution.
        </p>
      </div>
      <div style={{ display: 'flex', gap: 4 }} aria-label={`Hint level ${level} of 5`}>
        {HINT_LABELS.map((l, i) => (
          <span key={l} title={l} style={{ flex: 1, height: 6, borderRadius: 3, background: i < level ? 'var(--primary)' : 'var(--surface-alt)' }} />
        ))}
      </div>
      <div style={{ flex: 1, overflow: 'auto', display: 'grid', gap: 10, alignContent: 'start' }} aria-live="polite">
        {turns.length === 0 && <p className="muted" style={{ fontSize: 13 }}>Stuck? Ask a question or take the first hint.</p>}
        {turns.map((t, i) => (
          <div key={i} style={{ display: 'grid', gap: 6 }}>
            <p style={{ fontSize: 12, fontWeight: 700 }}>{t.q}</p>
            <div style={{ fontSize: 13, background: t.error ? 'var(--danger-tint)' : 'var(--surface-alt)', borderRadius: 10, padding: 10, whiteSpace: 'pre-wrap' }}>
              {t.error ?? t.a?.answer ?? 'Thinking…'}
              <CitationList sources={t.a?.sources} />
            </div>
          </div>
        ))}
      </div>
      <button className="btn btn-secondary btn-full" disabled={ask.isPending || level >= 5} onClick={() => requestHint(level === 0 ? 'Give me a first hint.' : 'Give me the next hint.')}>
        {level >= 5 ? 'All hints used' : level === 0 ? 'Get a hint' : `Next hint (${HINT_LABELS[level]})`}
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (question.trim()) {
            requestHint(question.trim())
            setQuestion('')
          }
        }}
        style={{ display: 'flex', gap: 6 }}
      >
        <input
          aria-label="Ask the tutor"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this step…"
          style={{ flex: 1, border: '1px solid var(--border)', borderRadius: 10, padding: '10px 12px' }}
        />
        <button className="btn btn-primary" disabled={!question.trim() || ask.isPending} aria-label="Ask">
          ↑
        </button>
      </form>
    </div>
  )
}
