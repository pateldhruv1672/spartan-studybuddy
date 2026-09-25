import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getPath, sendEvent, updateProgress } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { celebrateXp, toast } from '../app/uiStore'
import { Button } from '../components/primitives/Button'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { ErrorState, Skeleton } from '../components/primitives/Feedback'
import { LockIcon } from '../components/primitives/Icons'
import { KIND_LABEL, StudyItemView, itemKind, moduleKindLabel, type ItemKind } from '../features/study/ItemViews'
import { isQuizMissing, useQuizInfo } from '../features/study/QuizView'
import { TutorPanel } from '../features/study/TutorPanel'
import type { PathExercise, PathModuleItem } from '../api/types'

interface OutlineEntry {
  id: string
  title: string
  group: string
  moduleKind?: string
  objectives?: string[]
  kind: ItemKind
  minutes?: number
  xp?: number
  raw: PathModuleItem | PathExercise
}

export function StudyPage() {
  const { pathId, itemId } = useParams()
  const { userId, projectId } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const pathQuery = useQuery({ queryKey: ['path', pathId, userId], queryFn: () => getPath(pathId!, userId), enabled: !!pathId })
  const path = pathQuery.data

  const outline = useMemo<OutlineEntry[]>(() => {
    if (!path) return []
    const items = (path.plan?.modules || []).flatMap((m) =>
      (m.items || []).map((it) => ({
        id: it.id,
        title: it.title,
        group: m.title,
        moduleKind: m.kind,
        objectives: m.objectives,
        kind: itemKind(it.type, false),
        minutes: it.minutes,
        xp: it.xp,
        raw: it,
      }))
    )
    const exercises = (path.plan?.exercises || []).map((ex) => ({ id: ex.id, title: ex.title, group: 'Exercises', kind: 'exercise' as const, xp: ex.xp, raw: ex }))
    return [...items, ...exercises]
  }, [path])

  const statusOf = useMemo(() => {
    const map = new Map((path?.progress_items || []).map((x) => [x.item_id, x.status]))
    return (id: string) => map.get(id) || 'not_started'
  }, [path])

  const lockedSet = useMemo(() => new Set(path?.locked_items || []), [path])
  const quizStatus = path?.quiz_status || {}

  const current =
    outline.find((i) => i.id === itemId) ||
    outline.find((i) => statusOf(i.id) !== 'completed' && !lockedSet.has(i.id)) ||
    outline.find((i) => statusOf(i.id) !== 'completed') ||
    outline[0]
  const status = current ? statusOf(current.id) : 'not_started'
  const locked = !!current && lockedSet.has(current.id)
  // Graph quizzes complete only by passing. Legacy paths have no quiz endpoint (404) and keep the manual flow.
  const quizLike = !!current && (current.kind === 'quiz' || current.id.endsWith('-quiz'))
  const quizInfo = useQuizInfo(pathId, current?.id, quizLike && !locked)
  const legacyQuiz = quizLike && isQuizMissing(quizInfo.error)
  const isGradedQuiz = quizLike && !legacyQuiz
  // The unpassed quiz that is holding the later sections closed.
  const gatingQuiz = outline.find((i) => i.kind === 'quiz' && !quizStatus[i.id]?.passed && statusOf(i.id) !== 'completed' && !lockedSet.has(i.id))
  const me = path?.members?.find((m) => m.user_id === userId)
  const isMember = !!me

  const progress = useMutation({
    mutationFn: (body: { status: 'in_progress' | 'completed'; progress: number }) =>
      updateProgress(pathId!, { user_id: userId, item_id: current!.id, ...body }),
    onSuccess: (result, vars) => {
      for (const key of [['path', pathId], ['paths', projectId], ['learner', userId], ['manager-analytics'], ['activity']]) qc.invalidateQueries({ queryKey: key })
      if (vars.status !== 'completed') return
      if (result.xp_delta) celebrateXp(result.xp_delta)
      else toast('Marked complete')
      if (current!.kind === 'checkpoint' || current!.kind === 'quiz') {
        sendEvent({
          user_id: userId,
          project_id: projectId ?? undefined,
          type: current!.kind === 'quiz' ? 'quiz.completed' : 'checkpoint.completed',
          resource_id: current!.id,
          context: { path_id: pathId, item_id: current!.id },
        }).catch(() => {})
      }
      try {
        sessionStorage.removeItem(`draft:${userId}:${pathId}:${current!.id}`)
      } catch {
        /* storage unavailable */
      }
      const next = outline.find((i) => i.id !== current!.id && statusOf(i.id) !== 'completed' && !lockedSet.has(i.id))
      if (next) navigate(`/study/${pathId}/${next.id}`)
    },
    onError: (e) => toast(errorMessage(e)),
  })

  if (pathQuery.isLoading) return <div className="view"><Skeleton height={360} /></div>
  if (pathQuery.isError) return <div className="view"><ErrorState message={errorMessage(pathQuery.error)} onRetry={() => pathQuery.refetch()} /></div>
  if (!path || !current) return <div className="view"><ErrorState message="This path has no items yet." /></div>

  const currentIndex = outline.findIndex((i) => i.id === current.id)
  const nextItemId = outline[currentIndex + 1]?.id ?? null
  let lastGroup = ''

  return (
    <div className="view study-layout">
      <aside className="study-rail">
        <Link to={`/paths/${path.id}`} className="btn btn-ghost" style={{ paddingLeft: 0 }}>
          ← {path.target_role}
        </Link>
        <div style={{ margin: '10px 0 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
            <span>Path progress</span>
            <b>{Math.round((me?.progress || 0) * 100)}%</b>
          </div>
          <ProgressBar value={me?.progress || 0} />
        </div>
        <nav aria-label="Path outline" style={{ display: 'grid', gap: 2 }}>
          {outline.map((item) => {
            const header = item.group !== lastGroup ? item.group : null
            lastGroup = item.group
            const done = statusOf(item.id) === 'completed'
            const isLocked = lockedSet.has(item.id)
            const qs = quizStatus[item.id]
            const passed = item.kind === 'quiz' && (qs?.passed || done)
            const kindLabel = moduleKindLabel(item.moduleKind)
            return (
              <div key={item.id}>
                {header && (
                  <p className="eyebrow" style={{ margin: '12px 0 4px', fontSize: 10 }}>
                    {header}
                    {kindLabel ? ` · ${kindLabel}` : ''}
                  </p>
                )}
                <button
                  onClick={() => navigate(`/study/${path.id}/${item.id}`)}
                  className={`nav-btn${item.id === current.id ? ' active' : ''}`}
                  aria-current={item.id === current.id ? 'step' : undefined}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 8,
                    fontSize: 13,
                    fontWeight: item.id === current.id ? 700 : 400,
                    color: isLocked && item.id !== current.id ? 'var(--ink-faint)' : undefined,
                  }}
                >
                  <span>{item.title}</span>
                  <span style={{ color: 'var(--success)', display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' }}>
                    {isLocked ? (
                      <span style={{ color: 'var(--ink-faint)', display: 'inline-flex' }}>
                        <LockIcon label="Locked until the previous quiz is passed" />
                      </span>
                    ) : passed ? (
                      <span
                        className="badge badge-success"
                        style={{ padding: '2px 8px', fontSize: 10 }}
                        aria-label={`Quiz passed${qs?.best_score != null ? `, best score ${Math.round(qs.best_score * 100)} percent` : ''}`}
                      >
                        ✓ Passed
                      </span>
                    ) : done ? (
                      <span aria-label="completed">✓</span>
                    ) : item.kind === 'quiz' && qs?.best_score != null ? (
                      <span className="muted" style={{ fontSize: 11 }}>
                        best {Math.round(qs.best_score * 100)}%
                      </span>
                    ) : null}
                  </span>
                </button>
              </div>
            )
          })}
        </nav>
      </aside>

      <main style={{ display: 'grid', gap: 18, minWidth: 0 }}>
        <div>
          <p className="eyebrow">
            {KIND_LABEL[current.kind].toUpperCase()} · {current.group.toUpperCase()}
            {moduleKindLabel(current.moduleKind) ? ` · ${moduleKindLabel(current.moduleKind)!.toUpperCase()}` : ''}
          </p>
          <h1 style={{ fontSize: 34 }}>{current.title}</h1>
          <p className="muted" style={{ marginTop: 6 }}>
            {current.minutes ? `${current.minutes} min · ` : ''}
            <b style={{ color: 'var(--coral-ink)' }}>
              +{current.xp || 100} XP{isGradedQuiz ? ' for passing' : ''}
            </b>
          </p>
        </div>

        {(current.objectives?.length ?? 0) > 0 && !locked && (
          <details className="objectives">
            <summary>What this section covers</summary>
            <ul>
              {current.objectives!.map((o, i) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          </details>
        )}

        {locked ? (
          <div className="card lock-panel lock-panel-lg" role="status">
            <LockIcon size={22} />
            <div style={{ display: 'grid', gap: 10 }}>
              <h2 style={{ fontSize: 22 }}>This step is locked</h2>
              <p className="muted" style={{ lineHeight: 1.6, fontSize: 14 }}>
                Pass the previous section's quiz to unlock it. Quizzes cover the code and docs you just studied, you can retake them as often as you like, and your best score counts.
              </p>
              {gatingQuiz && (
                <div>
                  <Button variant="primary" onClick={() => navigate(`/study/${path.id}/${gatingQuiz.id}`)}>
                    Go to "{gatingQuiz.title}" →
                  </Button>
                </div>
              )}
            </div>
          </div>
        ) : (
          <StudyItemView path={path} item={current.raw} kind={current.kind} nextItemId={nextItemId} />
        )}

        {!locked && (
          <div className="card-flat" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            {!isMember ? (
              <>
                <span className="muted">Join this path to track progress and earn XP.</span>
                <Link className="btn btn-primary" to={`/paths/${path.id}`}>
                  Go to path
                </Link>
              </>
            ) : status === 'completed' ? (
              <>
                <span className="badge badge-success">{isGradedQuiz ? 'Quiz passed' : 'Completed'}</span>
                <span className="muted">Pick another step from the outline.</span>
              </>
            ) : isGradedQuiz ? (
              <span className="muted">This step completes only when you pass its quiz.</span>
            ) : status === 'in_progress' ? (
              <>
                <span className="muted">Finished? Mark it complete to earn XP and move on.</span>
                <Button variant="primary" pending={progress.isPending} onClick={() => progress.mutate({ status: 'completed', progress: 1 })}>
                  Mark complete
                </Button>
              </>
            ) : (
              <>
                <span className="muted">Ready when you are.</span>
                <Button variant="primary" pending={progress.isPending} onClick={() => progress.mutate({ status: 'in_progress', progress: 0.1 })}>
                  Start this step
                </Button>
              </>
            )}
          </div>
        )}
      </main>

      <aside className="study-rail">
        <TutorPanel key={current.id} pathId={path.id} itemId={current.id} context={current.title} />
      </aside>
    </div>
  )
}
