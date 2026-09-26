import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { createOnboarding, getGraphStatus, listRoleProfiles } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { Button } from '../components/primitives/Button'
import { CheckboxField, TextAreaField, TextField } from '../components/primitives/Field'
import { KeyValue } from '../components/primitives/Layout'

/** Offline fallback when /api/role-profiles is unavailable. */
const FALLBACK_ROLES = ['ML Engineer', 'Data Engineer', 'Data Analyst', 'Backend Engineer', 'Frontend Engineer', 'Forward Deployed Engineer', 'DevOps / Platform Engineer']
const STEPS = ['Role', 'Background', 'Schedule', 'Review']
const LEVELS: Array<{ id: 'junior' | 'mid' | 'senior'; label: string }> = [
  { id: 'junior', label: 'Junior' },
  { id: 'mid', label: 'Mid-level' },
  { id: 'senior', label: 'Senior' },
]

export function PathBuilderPage() {
  const { userId, projectId } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [step, setStep] = useState(0)
  // `role` is a role profile id, the fallback label, or 'custom'. null means "first available".
  const [role, setRole] = useState<string | null>(null)
  const [customRole, setCustomRole] = useState('')
  const [background, setBackground] = useState('')
  const [level, setLevel] = useState<'junior' | 'mid' | 'senior'>('junior')
  const [weeks, setWeeks] = useState(4)
  const [hours, setHours] = useState(8)
  const [isPublic, setIsPublic] = useState(false)
  const [engineChoice, setEngineChoice] = useState<'graph' | 'llm' | null>(null)
  const [quizQuestions, setQuizQuestions] = useState(5)

  const roles = useQuery({ queryKey: ['role-profiles'], queryFn: listRoleProfiles, staleTime: 5 * 60_000 })
  const graph = useQuery({ queryKey: ['graph-status', projectId], queryFn: () => getGraphStatus(projectId!), enabled: !!projectId, retry: false })

  const profiles = roles.data?.roles ?? []
  const options: Array<{ id: string; label: string; description?: string }> =
    profiles.length > 0
      ? profiles.map((r) => ({ id: r.id, label: r.title, description: r.description }))
      : FALLBACK_ROLES.map((r) => ({ id: r, label: r }))
  const roleId = role ?? options.find((o) => o.id === 'software-engineer')?.id ?? options.find((o) => o.id === 'backend-engineer')?.id ?? options[0]?.id ?? 'custom'
  const profile = profiles.find((r) => r.id === roleId)
  const targetRole = roleId === 'custom' ? customRole.trim() : profile?.title ?? options.find((o) => o.id === roleId)?.label ?? roleId

  const graphReady = !!graph.data?.ready
  const engine: 'graph' | 'llm' = engineChoice === 'llm' ? 'llm' : graphReady ? 'graph' : 'llm'
  const canNext = [!!targetRole, true, weeks >= 1 && weeks <= 16 && hours >= 1 && hours <= 40 && quizQuestions >= 4 && quizQuestions <= 8, true][step]

  const create = useMutation({
    mutationFn: () =>
      createOnboarding({
        user_id: userId,
        project_id: projectId!,
        target_role: targetRole,
        level,
        weeks,
        hours_per_week: hours,
        background,
        is_public: isPublic,
        engine,
        ...(profile ? { role_id: profile.id } : {}),
        ...(engine === 'graph' ? { quiz_questions: quizQuestions } : {}),
      }),
    onSuccess: (path) => {
      qc.invalidateQueries({ queryKey: ['paths'] })
      if (path.resource_job?.id) {
        try {
          sessionStorage.setItem(`scout:${path.id}`, path.resource_job.id)
        } catch {
          /* storage unavailable */
        }
      }
      toast('Path generated · resource scout queued')
      navigate(`/paths/${path.id}`)
    },
  })

  if (!projectId) return null

  return (
    <div className="view view-narrow">
      <div className="page-head page-head-center">
        <div>
          <p className="eyebrow">NEW ONBOARDING PATH</p>
          <h1>Design the role path.</h1>
          <p>StudyBuddy reads the connected repository, orders prerequisites before internal code, and adds exercises and checkpoints.</p>
        </div>
      </div>

      <div className="stepper" aria-label="Progress">
        {STEPS.map((s, i) => (
          <span key={s} className={i < step ? 'done' : i === step ? 'current' : ''} aria-current={i === step ? 'step' : undefined}>
            {i + 1}. {s}
          </span>
        ))}
      </div>

      <div className="card" style={{ display: 'grid', gap: 18 }}>
        {step === 0 && (
          <>
            <h2 style={{ fontSize: 22 }}>Which role is this path for?</h2>
            {roles.isLoading && <p className="muted">Loading role profiles…</p>}
            <div className="grid-2">
              {[...options, { id: 'custom', label: 'Other role…', description: 'Type your own role name' }].map((r) => (
                <button
                  key={r.id}
                  onClick={() => setRole(r.id)}
                  aria-pressed={roleId === r.id}
                  className="card-flat"
                  style={{ textAlign: 'left', cursor: 'pointer', padding: 14, borderColor: roleId === r.id ? 'var(--primary)' : 'var(--border)', background: roleId === r.id ? 'var(--primary-tint)' : 'var(--surface)' }}
                >
                  <b>{r.label}</b>
                  {r.description && (
                    <span className="muted" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
                      {r.description.length > 110 ? `${r.description.slice(0, 109)}…` : r.description}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {roleId === 'custom' && <TextField label="Role name" value={customRole} onChange={(e) => setCustomRole(e.target.value)} placeholder="e.g. Security Engineer" autoFocus hint="Custom roles are matched to the closest role profile for the graph roadmap." />}
            {profile && profile.concepts.length > 0 && (
              <div>
                <p className="eyebrow">KEY CONCEPTS FOR THIS ROLE</p>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {profile.concepts.slice(0, 8).map((c) => (
                    <span key={c.id} className="badge badge-neutral">
                      {c.name}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {step === 1 && (
          <>
            <h2 style={{ fontSize: 22 }}>What does the learner already know?</h2>
            <TextAreaField
              label="Background and known skills (optional)"
              value={background}
              onChange={(e) => setBackground(e.target.value)}
              placeholder="Strong Python and SQL. Some ML. New to Kafka and our deployment pipeline."
              rows={6}
              hint="StudyBuddy skips prerequisites the learner already has."
            />
          </>
        )}

        {step === 2 && (
          <>
            <h2 style={{ fontSize: 22 }}>Level and schedule</h2>
            <div>
              <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-muted)', marginBottom: 8 }}>Seniority</p>
              <div style={{ display: 'flex', gap: 8 }}>
                {LEVELS.map((l) => (
                  <button key={l.id} className="chip-toggle" aria-pressed={level === l.id} onClick={() => setLevel(l.id)}>
                    {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid-2">
              <TextField label="Length (1–16 weeks)" type="number" min={1} max={16} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} />
              <TextField label="Hours per week (1–40)" type="number" min={1} max={40} value={hours} onChange={(e) => setHours(Number(e.target.value))} />
            </div>
            <div>
              <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-muted)', marginBottom: 8 }}>Engine</p>
              <div className="engine-choice" role="radiogroup" aria-label="Roadmap engine">
                <label className={`engine-option${engine === 'graph' ? ' selected' : ''}${!graphReady ? ' disabled' : ''}`}>
                  <input type="radio" name="engine" value="graph" checked={engine === 'graph'} disabled={!graphReady} onChange={() => setEngineChoice('graph')} />
                  <span>
                    <b>
                      Graph-grounded <span className="badge badge-success" style={{ padding: '2px 8px', fontSize: 10 }}>Recommended</span>
                    </b>
                    <small>Built from the knowledge graph: real files, docs and dependencies, with cited references and a quiz after every section.</small>
                    {!graphReady && (
                      <small className="engine-hint">
                        {graph.isLoading ? 'Checking the knowledge graph…' : 'The knowledge graph is not built yet.'}{' '}
                        <Link to="/kit">Build it from the Onboarding kit</Link>.
                      </small>
                    )}
                  </span>
                </label>
                <label className={`engine-option${engine === 'llm' ? ' selected' : ''}`}>
                  <input type="radio" name="engine" value="llm" checked={engine === 'llm'} onChange={() => setEngineChoice('llm')} />
                  <span>
                    <b>LLM-only</b>
                    <small>The language model plans the curriculum from retrieved excerpts. Faster to start, but less grounded and without quiz gating.</small>
                  </span>
                </label>
              </div>
            </div>
            {engine === 'graph' && (
              <TextField
                label="Quiz questions per section (4–8)"
                type="number"
                min={4}
                max={8}
                value={quizQuestions}
                onChange={(e) => setQuizQuestions(Number(e.target.value))}
                hint="Each quiz is drawn from a larger bank, so retakes differ."
              />
            )}
            <CheckboxField label="Anyone in the workspace can join (otherwise invite code only)" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          </>
        )}

        {step === 3 && (
          <>
            <h2 style={{ fontSize: 22 }}>Review</h2>
            <KeyValue
              rows={[
                ['Role', <b key="r">{targetRole}</b>],
                ['Level', LEVELS.find((l) => l.id === level)?.label],
                ['Schedule', `${weeks} weeks · ${hours} hours/week`],
                ['Engine', engine === 'graph' ? `Graph-grounded · ${quizQuestions} questions per quiz` : 'LLM-only'],
                ['Background', background || 'Not specified'],
                ['Who can join', isPublic ? 'Anyone in the workspace' : 'Invite code only'],
              ]}
            />
            <div style={{ background: 'var(--teal-tint)', borderRadius: 12, padding: 14, fontSize: 13 }}>
              <b>Privacy:</b> private code and documents stay on this infrastructure. Only generic topics (like "Kafka consumer groups") are sent to public resource search — never file names, function names or source code.
            </div>
            {create.isError && (
              <p className="auth-error" role="alert">
                {errorMessage(create.error)} — your answers are kept, so you can try again.
              </p>
            )}
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
          <Button onClick={() => (step === 0 ? navigate('/paths') : setStep(step - 1))} disabled={create.isPending}>
            {step === 0 ? 'Cancel' : '← Back'}
          </Button>
          {step < 3 ? (
            <Button variant="primary" disabled={!canNext} onClick={() => setStep(step + 1)}>
              Next →
            </Button>
          ) : (
            <Button variant="primary" pending={create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? 'Reading the repository…' : 'Generate path'}
            </Button>
          )}
        </div>
        {create.isPending && (
          <p className="muted" style={{ textAlign: 'center' }}>
            This can take a minute while the local model plans the curriculum. You can leave this page — the path will appear under Paths.
          </p>
        )}
      </div>
    </div>
  )
}
