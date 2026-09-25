import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { sendEvent } from '../../api/endpoints'
import { useSessionStore } from '../../app/sessionStore'
import { CitationChip } from '../../components/citations/CitationChip'
import { TextAreaField } from '../../components/primitives/Field'
import { NeedsBackend } from '../../components/primitives/Layout'
import { DocumentDrawer, targetFromRef, type DocTarget } from '../graph/DocumentDrawer'
import { QuizView } from './QuizView'
import type { NodeRef, OnboardingPath, PathExercise, PathModuleItem } from '../../api/types'

export type ItemKind = 'walkthrough' | 'reading' | 'concept' | 'resource' | 'checkpoint' | 'quiz' | 'exercise' | 'lesson'

export function itemKind(type: string | undefined, isExercise: boolean): ItemKind {
  if (isExercise) return 'exercise'
  const t = (type || '').toLowerCase()
  if (t.includes('checkpoint')) return 'checkpoint'
  if (t.includes('quiz')) return 'quiz'
  if (t.includes('exercise')) return 'exercise'
  if (t.includes('doc_reading') || t === 'reading') return 'reading'
  if (t === 'concept') return 'concept'
  if (t.includes('walkthrough') || t.includes('internal') || t.includes('repo') || t.includes('code')) return 'walkthrough'
  if (['video', 'article', 'resource', 'external', 'paper', 'blog', 'public'].some((k) => t.includes(k))) return 'resource'
  return 'lesson'
}

export const MODULE_KIND_LABEL: Record<string, string> = {
  foundations: 'Foundations',
  orientation: 'Orientation',
  subsystem: 'Subsystem',
  handson: 'Hands-on',
  capstone: 'Capstone',
}

export function moduleKindLabel(kind?: string) {
  return kind ? MODULE_KIND_LABEL[kind] ?? kind : undefined
}

export const KIND_LABEL: Record<ItemKind, string> = {
  walkthrough: 'Repository walkthrough',
  reading: 'Documentation reading',
  concept: 'Concept',
  resource: 'External resource',
  checkpoint: 'Checkpoint',
  quiz: 'Quiz',
  exercise: 'Exercise',
  lesson: 'Lesson',
}

/** Unsent answers survive reloads and navigation (session-scoped, per user/path/item). */
function useDraft(key: string) {
  const [value, setValue] = useState(() => {
    try {
      return sessionStorage.getItem(key) ?? ''
    } catch {
      return ''
    }
  })
  useEffect(() => {
    try {
      if (value) sessionStorage.setItem(key, value)
      else sessionStorage.removeItem(key)
    } catch {
      /* storage unavailable */
    }
  }, [key, value])
  return [value, setValue] as const
}

function RepoRefs({ refs }: { refs?: string[] }) {
  if (!refs?.length) return null
  return (
    <div>
      <p className="eyebrow">IN THE CODEBASE</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {refs.map((r) => (
          <Link key={r} className="citation-chip" style={{ textDecoration: 'none' }} to={`/repository?q=${encodeURIComponent(r)}`}>
            {r}
          </Link>
        ))}
      </div>
    </div>
  )
}

/** Graph-grounded references: each shows its citation and why it matters, and opens the cited lines in a drawer. */
function NodeRefs({ refs, onOpen }: { refs: NodeRef[]; onOpen: (t: DocTarget) => void }) {
  return (
    <div>
      <p className="eyebrow">IN THE CODEBASE</p>
      <ul className="noderef-list">
        {refs.map((r) => (
          <li key={r.node_id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <button type="button" className="link-btn" onClick={() => onOpen(targetFromRef(r))}>
                {r.name}
              </button>
              {(r.citation || r.path) && <CitationChip citation={r.citation || r.path!} onOpen={() => onOpen(targetFromRef(r))} />}
            </div>
            {(r.reasons?.length ?? 0) > 0 && (
              <ul className="reason-list">
                {r.reasons!.slice(0, 3).map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Prefers grounded node_refs; falls back to bare repo_refs for legacy LLM-only paths. */
function ItemRefs({ item }: { item: PathModuleItem | PathExercise }) {
  const [target, setTarget] = useState<DocTarget | null>(null)
  const nodeRefs = 'node_refs' in item ? item.node_refs : undefined
  if (nodeRefs?.length) {
    return (
      <>
        <NodeRefs refs={nodeRefs} onOpen={setTarget} />
        <DocumentDrawer target={target} onClose={() => setTarget(null)} />
      </>
    )
  }
  return <RepoRefs refs={item.repo_refs} />
}

function hasRefs(item: PathModuleItem | PathExercise) {
  return !!('node_refs' in item && item.node_refs?.length) || !!item.repo_refs?.length
}

function AskLink({ mode, prompt, children }: { mode: string; prompt: string; children: string }) {
  return (
    <Link className="btn btn-secondary" to={`/assistant?mode=${mode}&q=${encodeURIComponent(prompt)}`}>
      {children}
    </Link>
  )
}

interface Props {
  path: OnboardingPath
  item: PathModuleItem | PathExercise
  kind: ItemKind
  /** Next step in the outline, used by "Continue" after a passed quiz. */
  nextItemId?: string | null
}

export function StudyItemView({ path, item, kind, nextItemId }: Props) {
  const { userId, projectId } = useSessionStore()
  const [draft, setDraft] = useDraft(`draft:${userId}:${path.id}:${item.id}`)
  const topic = 'topic' in item && item.topic ? item.topic : item.title

  if (kind === 'quiz' || (kind === 'checkpoint' && item.id.endsWith('-quiz'))) {
    return (
      <QuizView
        key={`${path.id}:${item.id}`}
        pathId={path.id}
        itemId={item.id}
        nextItemId={nextItemId}
        legacy={<LegacyCheckpoint item={item} kind="quiz" draft={draft} setDraft={setDraft} />}
      />
    )
  }

  if (kind === 'reading') {
    return (
      <div className="card" style={{ display: 'grid', gap: 18 }}>
        <p style={{ fontSize: 16, lineHeight: 1.7 }}>
          Read <b>{topic}</b> in the project's own documentation. Open each source below, skim the headings first, then note what a new teammate would need to know.
        </p>
        <ItemRefs item={item} />
        {!hasRefs(item) && (
          <p className="muted">
            No specific documents were attached to this step. Use the <Link to="/repository">repository map</Link> to find them.
          </p>
        )}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <AskLink mode="explain" prompt={`Summarize the key ideas in the ${topic} documentation for a new teammate.`}>
            Summarize this for me
          </AskLink>
        </div>
      </div>
    )
  }

  if (kind === 'concept') {
    return (
      <div className="card" style={{ display: 'grid', gap: 18 }}>
        <p style={{ fontSize: 16, lineHeight: 1.7 }}>
          <b>{topic}</b> shows up throughout this codebase. Get the idea first, then look at where the project uses it below.
        </p>
        <ItemRefs item={item} />
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <AskLink mode="explain" prompt={`Explain ${topic} simply, with an analogy, then show where this codebase uses it.`}>
            Explain this simply
          </AskLink>
          <AskLink mode="socratic" prompt={`Quiz me gently on ${topic} so I can check my understanding.`}>
            Test my understanding
          </AskLink>
        </div>
      </div>
    )
  }

  if (kind === 'walkthrough') {
    return (
      <div className="card" style={{ display: 'grid', gap: 18 }}>
        <p style={{ fontSize: 16, lineHeight: 1.7 }}>
          Walk through <b>{topic}</b> in the real repository. Open each reference below, read how it fits together, then explain the flow in your own words.
        </p>
        <ItemRefs item={item} />
        {!hasRefs(item) && (
          <p className="muted">
            No specific files were attached to this step. Use the <Link to="/repository">repository map</Link> to explore.
          </p>
        )}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <AskLink mode="explain" prompt={`Explain ${topic} in this codebase simply.`}>
            Explain this simply
          </AskLink>
          <AskLink mode="code" prompt={`Trace how ${topic} works through the repository.`}>
            Trace it in the code
          </AskLink>
        </div>
      </div>
    )
  }

  if (kind === 'resource') {
    const words = topic.toLowerCase().split(/\W+/).filter((w) => w.length > 3)
    const matches = (path.resources || []).filter((r) => words.some((w) => `${r.title} ${r.rationale ?? ''}`.toLowerCase().includes(w)))
    const list = matches.length ? matches : path.resources || []
    return (
      <div className="card" style={{ display: 'grid', gap: 14 }}>
        <p style={{ fontSize: 16, lineHeight: 1.7 }}>
          Study <b>{topic}</b> from a curated public resource. The Chrome extension remembers where you stop so you can resume later.
        </p>
        {list.length === 0 ? (
          <p className="muted">The resource scout hasn't returned public resources for this path yet.</p>
        ) : (
          <div className="row-list">
            {list.slice(0, 5).map((r, i) => (
              <a
                key={i}
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => sendEvent({ user_id: userId, project_id: projectId ?? undefined, type: 'article.opened', resource_id: r.url, context: { path_id: path.id, item_id: item.id } }).catch(() => {})}
                style={{ display: 'block', textDecoration: 'none', color: 'inherit' }}
              >
                <b style={{ color: 'var(--primary)' }}>{r.title} ↗</b>
                <div className="muted" style={{ fontSize: 12 }}>
                  {r.resource_type || r.source || 'resource'} · {r.rationale || 'Curated prerequisite'}
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (kind === 'checkpoint') {
    return <LegacyCheckpoint item={item} kind="checkpoint" draft={draft} setDraft={setDraft} />
  }

  if (kind === 'exercise') {
    const ex = item as PathExercise
    return (
      <ExerciseView ex={ex} draft={draft} setDraft={setDraft} pathId={path.id} />
    )
  }

  return (
    <div className="card" style={{ display: 'grid', gap: 14 }}>
      <p style={{ fontSize: 16, lineHeight: 1.7 }}>
        This lesson covers <b>{topic}</b>. Ask StudyBuddy to explain it, then mark it complete when you're comfortable.
      </p>
      <ItemRefs item={item} />
      <div style={{ display: 'flex', gap: 10 }}>
        <AskLink mode="explain" prompt={`Explain ${topic} simply, with an analogy.`}>
          Explain this simply
        </AskLink>
      </div>
    </div>
  )
}

/** Free-text question for legacy paths, whose quizzes and checkpoints predate server-side grading. */
function LegacyCheckpoint({
  item,
  kind,
  draft,
  setDraft,
}: {
  item: PathModuleItem | PathExercise
  kind: 'checkpoint' | 'quiz'
  draft: string
  setDraft: (v: string) => void
}) {
  const question = ('checkpoint_question' in item && item.checkpoint_question) || `In your own words: ${item.title}`
  return (
    <div className="card" style={{ display: 'grid', gap: 14 }}>
      <p className="eyebrow" style={{ margin: 0 }}>
        {kind === 'quiz' ? 'QUIZ QUESTION' : 'CHECKPOINT QUESTION'}
      </p>
      <p style={{ fontSize: 18 }}>
        <b>{question}</b>
      </p>
      <ItemRefs item={item} />
      <TextAreaField label="Your answer (saved as you type)" value={draft} onChange={(e) => setDraft(e.target.value)} rows={6} />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <AskLink mode="socratic" prompt={`Checkpoint: "${question}"\nMy answer: ${draft || '(not written yet)'}\nIs this right? Guide me, don't just tell me.`}>
          Check my answer with StudyBuddy
        </AskLink>
      </div>
    </div>
  )
}

function ExerciseView({ ex, draft, setDraft, pathId }: { ex: PathExercise; draft: string; setDraft: (v: string) => void; pathId: string }) {
  const [checked, setChecked] = useState<Record<number, boolean>>({})
  return (
    <div className="card" style={{ display: 'grid', gap: 16 }}>
      {ex.difficulty && <span className="badge badge-info" style={{ justifySelf: 'start' }}>{ex.difficulty}</span>}
      <p style={{ fontSize: 16, lineHeight: 1.7 }}>{ex.description || ex.title}</p>
      <RepoRefs refs={ex.repo_refs} />
      {(ex.acceptance?.length ?? 0) > 0 && (
        <div>
          <p className="eyebrow">DONE WHEN YOU CAN…</p>
          <div style={{ display: 'grid', gap: 8 }}>
            {ex.acceptance!.map((a, i) => (
              <label key={i} className="checkbox-row" style={{ fontSize: 14 }}>
                <input type="checkbox" checked={!!checked[i]} onChange={(e) => setChecked((c) => ({ ...c, [i]: e.target.checked }))} />
                {a}
              </label>
            ))}
          </div>
        </div>
      )}
      <TextAreaField label="Your notes and solution outline (saved as you type)" value={draft} onChange={(e) => setDraft(e.target.value)} rows={8} />
      <p className="muted" style={{ fontSize: 12 }}>
        Do the work in your own editor. StudyBuddy never edits or submits your code.
      </p>
      <NeedsBackend endpoint={`POST /api/onboarding/path/${pathId}/items/${ex.id}/submissions`}>Submitting the exercise for review, score and XP.</NeedsBackend>
    </div>
  )
}
