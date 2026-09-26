import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { askAssistant, getAgentJob, getThreadMessages, listChatThreads } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { CitationList } from '../components/citations/CitationChip'
import { Badge, statusTone } from '../components/primitives/Badge'
import type { AssistantMode, ChatMessage } from '../api/types'

const MODES: Array<{ id: AssistantMode; label: string; description: string }> = [
  { id: 'auto', label: 'Auto', description: 'Pick the best mode for me' },
  { id: 'qa', label: 'Answer', description: 'Direct answer with sources' },
  { id: 'socratic', label: 'Socratic', description: 'Hints, not the solution' },
  { id: 'explain', label: 'Explain', description: 'Simple, with analogies' },
  { id: 'code', label: 'Code', description: 'Reason about the repository' },
  { id: 'research', label: 'Research', description: 'Search public sources' },
]

const MODE_NAMES: Record<string, string> = { qa: 'Direct answer', socratic: 'Socratic tutor', explain: 'Explanation', code: 'Code reasoning', research: 'Research', auto: 'Auto' }

interface LocalMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatMessage['sources']
  metrics?: ChatMessage['metrics']
  mode?: string
  jobId?: string
  pending?: boolean
  failed?: boolean
}

function ResearchJob({ jobId }: { jobId: string }) {
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getAgentJob(jobId),
    refetchInterval: (q) => (['completed', 'failed', 'declined'].includes(q.state.data?.status ?? '') ? false : 4000),
  })
  const status = job.data?.status ?? 'queued'
  const result = job.data?.result
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <b>Research job</b>
        <Badge tone={statusTone(status)}>{status}</Badge>
      </div>
      {status === 'queued' && <p>Waiting for the Browser-Use bridge on the MacBook to pick this up. Only your question — never private code — is sent to public search.</p>}
      {status === 'running' && <p>Searching public documentation, papers and videos…</p>}
      {result?.synthesis && <p style={{ whiteSpace: 'pre-wrap' }}>{result.synthesis}</p>}
      {(result?.resources?.length ?? 0) > 0 && (
        <div style={{ display: 'grid', gap: 6 }}>
          {result!.resources!.slice(0, 8).map((r, i) => (
            <a key={i} href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12 }}>
              [{i + 1}] {r.title || r.url}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export function AssistantPage() {
  const { userId, projectId } = useSessionStore()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { threadId: routeThread } = useParams()
  const [params] = useSearchParams()
  const [mode, setMode] = useState<AssistantMode>((params.get('mode') as AssistantMode) || 'auto')
  const [threadId, setThreadId] = useState<string | null>(routeThread ?? null)
  const [question, setQuestion] = useState(params.get('q') || (params.get('item') ? `Give me a hint about: ${params.get('item')}` : ''))
  const [messages, setMessages] = useState<LocalMessage[]>([
    { role: 'assistant', content: 'Ask me anything about this workspace. I can answer directly, explain simply, teach step by step, or research public sources.' },
  ])
  const scrollRef = useRef<HTMLDivElement>(null)

  const threads = useQuery({ queryKey: ['threads', userId, projectId], queryFn: () => listChatThreads(userId, projectId ?? undefined), enabled: !!projectId })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (!routeThread) return
    let active = true
    setThreadId(routeThread)
    getThreadMessages(routeThread)
      .then((msgs) => { if (active) setMessages(msgs.map((m) => ({ role: m.role, content: m.content, sources: m.sources, metrics: m.metrics, mode: m.mode as string | undefined, jobId: m.job_id }))) })
      .catch((e) => toast(errorMessage(e)))
    return () => { active = false }
  }, [routeThread, projectId, userId])

  const replaceLast = (msg: LocalMessage) =>
    setMessages((prev) => {
      const next = [...prev]
      next[next.length - 1] = msg
      return next
    })

  const ask = useMutation({
    mutationFn: async (q: string) => {
      return {
        answer: await askAssistant({
          user_id: userId,
          project_id: projectId!,
          question: q,
          thread_id: threadId,
          mode,
          hint_level: 2,
          allow_final_answer: mode !== 'socratic',
        }),
      }
    },
    onSuccess: (r) => {
      const a = r.answer!
      replaceLast({ role: 'assistant', content: a.answer, sources: a.sources, metrics: a.metrics, mode: a.mode, jobId: a.job_id })
      if (a.thread_id) {
        setThreadId(a.thread_id)
        navigate(`/assistant/${a.thread_id}`, { replace: true })
      }
      qc.invalidateQueries({ queryKey: ['threads', userId, projectId] })
    },
    onError: (e) => {
      replaceLast({ role: 'assistant', content: `Not sent: ${errorMessage(e)}`, failed: true })
      toast(errorMessage(e))
    },
  })

  function send() {
    const q = question.trim()
    if (!q || !projectId || ask.isPending) return
    setMessages((prev) => [...prev, { role: 'user', content: q }, { role: 'assistant', content: 'Reading the private knowledge layer…', pending: true }])
    setQuestion('')
    ask.mutate(q)
  }

  if (!projectId) return null

  return (
    <div className="view" style={{ display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr)', gap: 20, height: 'calc(100vh - 72px)' }}>
      <aside style={{ overflow: 'auto' }}>
        <p className="eyebrow">CONVERSATIONS</p>
        <button
          className="nav-btn"
          onClick={() => {
            setThreadId(null)
            navigate('/assistant')
            setMessages([{ role: 'assistant', content: 'Fresh conversation. What do you want to understand?' }])
          }}
        >
          + New conversation
        </button>
        <div style={{ display: 'grid', gap: 4, marginTop: 8 }}>
          {threads.data?.map((t) => (
            <button key={t.id} className={`nav-btn${t.id === threadId ? ' active' : ''}`} onClick={() => navigate(`/assistant/${t.id}`)} style={{ fontSize: 12 }}>
              {t.title || MODE_NAMES[t.mode || ''] || 'Conversation'}
            </button>
          ))}
        </div>
      </aside>

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }} role="radiogroup" aria-label="Answer mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="radio"
              aria-checked={mode === m.id}
              onClick={() => setMode(m.id)}
              style={{
                border: '1px solid',
                borderRadius: 12,
                padding: '9px 13px',
                background: mode === m.id ? 'var(--primary-tint)' : 'var(--surface)',
                borderColor: mode === m.id ? 'var(--primary)' : 'var(--border)',
                textAlign: 'left',
              }}
            >
              <b style={{ display: 'block', fontSize: 13 }}>{m.label}</b>
              <span style={{ fontSize: 11, color: 'var(--ink-muted)' }}>{m.description}</span>
            </button>
          ))}
        </div>

        <div ref={scrollRef} className="card" style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }} aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div
                style={{
                  maxWidth: '82%',
                  padding: '13px 15px',
                  borderRadius: 17,
                  fontSize: 14,
                  lineHeight: 1.6,
                  background: m.role === 'user' ? 'var(--ink)' : m.failed ? 'var(--danger-tint)' : 'var(--surface-alt)',
                  color: m.role === 'user' ? '#fff' : m.failed ? 'var(--danger-ink)' : 'var(--ink)',
                  opacity: m.pending ? 0.7 : 1,
                }}
              >
                {m.jobId ? <ResearchJob jobId={m.jobId} /> : <p style={{ whiteSpace: 'pre-wrap' }}>{m.content}</p>}
                <CitationList sources={m.sources} />
                {m.role === 'assistant' && !m.pending && m.mode && !m.jobId && (
                  <div style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 8, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                    {MODE_NAMES[m.mode] || m.mode}
                    {m.metrics?.ttft_ms != null && ` · first token ${(m.metrics.ttft_ms / 1000).toFixed(2)}s`}
                    {m.metrics?.tokens_per_second ? ` · ${m.metrics.tokens_per_second.toFixed(1)} tok/s` : ''} · local inference
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'flex-end', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 8 }}>
          <textarea
            aria-label="Ask StudyBuddy"
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder={mode === 'research' ? 'What should I research in public sources?' : 'Ask about a function, architecture, or concept…'}
            style={{ flex: 1, border: 0, background: 'transparent', resize: 'none', padding: 8, maxHeight: 140, outline: 'none' }}
          />
          <button className="btn btn-primary" onClick={send} disabled={!question.trim() || ask.isPending} aria-label="Send">
            ↑
          </button>
        </div>
        <p className="muted" style={{ fontSize: 11, marginTop: 6, textAlign: 'center' }}>
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  )
}
