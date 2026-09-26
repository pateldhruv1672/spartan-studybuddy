import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getAgentJob, getPath, joinPath, sendEvent } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { pct } from '../app/hooks'
import { Button } from '../components/primitives/Button'
import { Badge, statusTone } from '../components/primitives/Badge'
import { Card, CardTitle } from '../components/primitives/Card'
import { ErrorState, Skeleton } from '../components/primitives/Feedback'
import { NeedsBackend, Section, timeAgo } from '../components/primitives/Layout'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { LockIcon } from '../components/primitives/Icons'
import { KIND_LABEL, itemKind, moduleKindLabel } from '../features/study/ItemViews'
import type { PathModule, PlanMeta } from '../api/types'
import { PathManagerActions } from '../features/study/PathManagerActions'

function youtubeThumbnail(url: string): string | null {
  try {
    const u = new URL(url)
    const id = u.hostname === 'youtu.be' ? u.pathname.slice(1) : u.hostname.includes('youtube.com') ? u.searchParams.get('v') : null
    return id ? `https://img.youtube.com/vi/${id}/hqdefault.jpg` : null
  } catch {
    return null
  }
}

/** Compact provenance card: which engine built the roadmap, for whom, and how it fit the time budget. */
function BuildCard({ meta }: { meta: PlanMeta }) {
  const budget = meta.budget_minutes
  const est = meta.estimated_minutes
  const ratio = budget && est ? Math.min(1, est / budget) : 0
  return (
    <Card>
      <CardTitle title="How this roadmap was built" subtitle={meta.engine === 'graph' ? 'Grounded in the knowledge graph' : 'Written by the language model only'} />
      {(meta.provenance === 'fallback' || (meta.warnings?.length ?? 0) > 0) && (
        <div className="lock-panel" role="alert" style={{ marginBottom: 12 }}>
          <div>
            <b>{meta.provenance === 'fallback' ? 'Placeholder roadmap — needs review' : 'Check this roadmap'}</b>
            {meta.provenance === 'fallback' && meta.warning && <p className="muted">{meta.warning}</p>}
            {(meta.warnings || []).map((w) => (
              <p key={w} className="muted">
                {w}
              </p>
            ))}
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {meta.coverage && meta.coverage.ratio != null && <Badge tone={meta.coverage.ratio >= 0.5 ? 'success' : 'warning'}>{`Covers ${meta.coverage.top_files_covered}/${meta.coverage.top_files} key files`}</Badge>}
        <Badge tone={meta.engine === 'graph' ? 'success' : 'neutral'}>{meta.engine === 'graph' ? 'Graph-grounded' : 'LLM-only'}</Badge>
        {meta.role_title && <Badge tone="info">{meta.role_title}</Badge>}
        {meta.gating && <Badge tone="coral">Quiz-gated</Badge>}
      </div>
      {budget != null && est != null && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
            <span>Estimated time</span>
            <b>
              {est} of {budget} min budget
            </b>
          </div>
          <ProgressBar value={ratio} />
        </div>
      )}
      <div className="row-list" style={{ fontSize: 13 }}>
        {meta.quiz_pass_threshold != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="muted">Quiz pass mark</span>
            <b>{pct(meta.quiz_pass_threshold)}</b>
          </div>
        )}
        {meta.generated_at && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="muted">Generated</span>
            <b>{timeAgo(meta.generated_at)}</b>
          </div>
        )}
        {meta.graph_build_id && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
            <span className="muted">Graph build</span>
            <b className="mono" style={{ fontSize: 11 }}>
              {meta.graph_build_id.slice(0, 10)}
            </b>
          </div>
        )}
      </div>
      {(meta.dropped_sections?.length ?? 0) > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="eyebrow">LEFT OUT TO FIT THE TIME</p>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {meta.dropped_sections!.map((d) => (
              <span key={d} className="badge badge-neutral">
                {d}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

function moduleMinutes(m: PathModule) {
  return m.minutes ?? (m.items || []).reduce((s, i) => s + (i.minutes || 0), 0)
}

function ScoutStatus({ jobId }: { jobId: string }) {
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getAgentJob(jobId),
    refetchInterval: (q) => (['completed', 'failed', 'declined'].includes(q.state.data?.status ?? '') ? false : 5000),
  })
  const status = job.data?.status ?? 'queued'
  const topics = (job.data?.payload?.topics as string[] | undefined) || []
  const text: Record<string, string> = {
    queued: 'Waiting for the Browser-Use bridge on the MacBook to pick up the search.',
    running: 'Searching public docs, videos, blogs and papers.',
    completed: 'Done — curated resources are listed below.',
    failed: 'The scout failed. Resources can be regenerated once that endpoint exists.',
  }
  return (
    <div className="card-flat" style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <b>Resource scout</b>
        <Badge tone={statusTone(status)}>{status}</Badge>
      </div>
      <p className="muted">{text[status] ?? status}</p>
      {topics.length > 0 && (
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--ink-faint)', marginBottom: 4 }}>PUBLIC SEARCH TOPICS (generic only)</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {topics.map((t) => (
              <span key={t} className="badge badge-neutral">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function PathDetailPage() {
  const { pathId } = useParams()
  const { userId, projectId, role } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [joinCode, setJoinCode] = useState('')

  const pathQuery = useQuery({ queryKey: ['path', pathId, userId], queryFn: () => getPath(pathId!, userId), enabled: !!pathId })
  const p = pathQuery.data
  const me = useMemo(() => p?.members?.find((m) => m.user_id === userId), [p, userId])
  const isCreator = p?.creator_id === userId
  const isManager = role === 'manager'
  const scoutJobId = useMemo(() => {
    try {
      return p?.resource_job?.id ?? sessionStorage.getItem(`scout:${pathId}`)
    } catch {
      return p?.resource_job?.id ?? null
    }
  }, [p, pathId])

  const join = useMutation({
    mutationFn: () => joinPath(pathId!, { user_id: userId, invite_code: joinCode.trim() || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['path', pathId] })
      qc.invalidateQueries({ queryKey: ['paths', projectId] })
      sendEvent({ user_id: userId, project_id: projectId ?? undefined, type: 'path.joined', resource_id: pathId }).catch(() => {})
      toast('You joined the path')
    },
    onError: (e) => toast(errorMessage(e)),
  })

  if (pathQuery.isLoading) return <div className="view"><Skeleton height={360} /></div>
  if (pathQuery.isError || !p) return <div className="view"><ErrorState message={errorMessage(pathQuery.error)} onRetry={() => pathQuery.refetch()} /></div>

  const status = new Map((p.progress_items || []).map((x) => [x.item_id, x.status]))
  // First resource found for each topic, so a module item (e.g. "Git branching and pull requests")
  // can show its own scouted video/article inline instead of only in the disconnected flat
  // "Curated resources" list below -- see the topic/module_id reverse-mapping added in get_path().
  const resourceByTopic = new Map((p.resources || []).filter((r) => r.topic).map((r) => [r.topic!, r]))
  const lockedSet = new Set(p.locked_items || [])
  const quizStatus = p.quiz_status || {}
  const firstOpen = [...(p.plan?.modules || []).flatMap((m) => m.items || []), ...(p.plan?.exercises || [])].find((i) => status.get(i.id) !== 'completed' && !lockedSet.has(i.id))

  return (
    <div className="view">
      <Link to="/paths" className="btn btn-ghost" style={{ paddingLeft: 0 }}>
        ← All paths
      </Link>
      <div className="page-head" style={{ marginTop: 8 }}>
        <div>
          <p className="eyebrow">
            {p.level.toUpperCase()} · {p.weeks} WEEKS · {p.hours_per_week} H/WEEK
          </p>
          <h1>{p.target_role}</h1>
          <p>{p.plan?.summary || 'Role-specific onboarding generated from the private codebase.'}</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 10 }}>
          {me ? (
            <Button variant="primary" onClick={() => navigate(firstOpen ? `/study/${p.id}/${firstOpen.id}` : `/study/${p.id}`)}>
              {firstOpen ? 'Continue studying →' : 'Review path'}
            </Button>
          ) : (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {!p.is_public && !isCreator && (
                <input
                  aria-label="Invite code"
                  placeholder="Invite code"
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value)}
                  style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '11px 12px', width: 140 }}
                />
              )}
              <Button variant="primary" pending={join.isPending} onClick={() => join.mutate()}>
                Join this path
              </Button>
            </div>
          )}
        </div>
      </div>

      {me && (
        <div className="card-flat" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
            <b>Your progress</b>
            <span>
              {pct(me.progress)} · <b style={{ color: 'var(--coral-ink)' }}>{me.xp || 0} XP</b>
            </span>
          </div>
          <ProgressBar value={me.progress || 0} />
        </div>
      )}

      <div className="split">
        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          {(p.plan?.prerequisites?.length ?? 0) > 0 && (
            <Card>
              <CardTitle title="Prerequisites" subtitle="Learned first, before internal code" />
              <div className="row-list">
                {p.plan.prerequisites!.map((pr, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <b style={{ fontSize: 14 }}>{pr.concept}</b>
                      {pr.priority && <Badge tone={pr.priority === 'essential' ? 'coral' : 'neutral'}>{pr.priority}</Badge>}
                    </div>
                    {pr.reason && <p className="muted">{pr.reason}</p>}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {(p.plan?.modules || []).map((m, mi) => {
            const quizItem = (m.items || []).find((i) => itemKind(i.type, false) === 'quiz')
            const qs = quizItem ? quizStatus[quizItem.id] : undefined
            const kindLabel = moduleKindLabel(m.kind)
            const minutes = moduleMinutes(m)
            const moduleLocked = !!qs?.locked
            return (
              <Card key={m.id ?? mi}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <p className="eyebrow">MODULE {String(mi + 1).padStart(2, '0')}</p>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {kindLabel && <Badge tone="info">{kindLabel}</Badge>}
                    {minutes > 0 && <Badge tone="neutral">~{minutes} min</Badge>}
                    {qs &&
                      (qs.passed ? (
                        <Badge tone="success">Quiz passed{qs.best_score != null ? ` · ${pct(qs.best_score)}` : ''}</Badge>
                      ) : moduleLocked ? (
                        <Badge tone="neutral">
                          <LockIcon size={12} /> Locked
                        </Badge>
                      ) : qs.attempts > 0 ? (
                        <Badge tone="warning">Best {pct(qs.best_score)} · {qs.attempts} attempt{qs.attempts === 1 ? '' : 's'}</Badge>
                      ) : (
                        <Badge tone="warning">Quiz to pass</Badge>
                      ))}
                  </div>
                </div>
                <h3 style={{ fontSize: 19 }}>{m.title}</h3>
                {m.outcome && <p className="muted" style={{ margin: '4px 0 10px' }}>Outcome: {m.outcome}</p>}
                <div className="row-list">
                  {(m.items || []).map((item) => {
                    const st = status.get(item.id)
                    const locked = lockedSet.has(item.id)
                    const resource = item.topic ? resourceByTopic.get(item.topic) : undefined
                    const resShot = resource?.metadata?.screenshot_base64
                    const resThumb = resource ? youtubeThumbnail(resource.url) || (resShot ? `data:image/png;base64,${resShot}` : null) : null
                    return (
                      <div key={item.id} className="row-btn" style={{ ...(locked ? { opacity: 0.72 } : undefined), flexDirection: 'column', alignItems: 'stretch', gap: 8, cursor: 'default' }}>
                        <button
                          onClick={() => navigate(`/study/${p.id}/${item.id}`)}
                          style={{ display: 'flex', justifyContent: 'space-between', width: '100%', background: 'none', border: 0, padding: 0, cursor: 'pointer', textAlign: 'left' }}
                        >
                          <span style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                            <span
                              aria-hidden="true"
                              style={{ width: 26, height: 26, borderRadius: 8, display: 'grid', placeItems: 'center', fontSize: 12, background: st === 'completed' ? 'var(--success-tint)' : 'var(--surface-alt)' }}
                            >
                              {locked ? <LockIcon size={13} /> : st === 'completed' ? '✓' : st === 'in_progress' ? '…' : ''}
                            </span>
                            <span>
                              <b style={{ fontSize: 14 }}>{item.title}</b>
                              <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                                {KIND_LABEL[itemKind(item.type, false)]} · {item.minutes || 15} min · +{item.xp || 100} XP
                              </span>
                            </span>
                          </span>
                          <span className="muted">{locked ? 'Locked' : st === 'completed' ? 'Done' : 'Open →'}</span>
                        </button>
                        {resource && (
                          <a
                            href={resource.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => {
                              e.stopPropagation()
                              sendEvent({ user_id: userId, project_id: projectId ?? undefined, type: 'article.opened', resource_id: resource.url, context: { path_id: p.id } }).catch(() => {})
                            }}
                            style={{ display: 'flex', gap: 10, alignItems: 'center', textDecoration: 'none', color: 'inherit', paddingLeft: 38, marginTop: -2 }}
                          >
                            {resThumb && <img src={resThumb} alt="" style={{ width: 56, height: 32, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }} />}
                            <span style={{ fontSize: 12, lineHeight: 1.4 }}>
                              <Badge tone="info">{resource.resource_type || 'resource'}</Badge>{' '}
                              <span className="muted">{resource.title}</span>
                            </span>
                          </a>
                        )}
                      </div>
                    )
                  })}
                </div>
              </Card>
            )
          })}

          {(p.plan?.exercises?.length ?? 0) > 0 && (
            <Card>
              <CardTitle title="Exercises" subtitle="Built from this repository" />
              <div className="row-list">
                {p.plan.exercises!.map((ex) => (
                  <button key={ex.id} className="row-btn" onClick={() => navigate(`/study/${p.id}/${ex.id}`)}>
                    <span>
                      <b style={{ fontSize: 14 }}>{ex.title}</b>
                      <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                        {ex.difficulty || 'exercise'} · {ex.acceptance?.length ?? 0} acceptance criteria · +{ex.xp || 100} XP
                      </span>
                    </span>
                    <span className="muted">{status.get(ex.id) === 'completed' ? 'Done' : 'Open →'}</span>
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          {p.plan?.meta && <BuildCard meta={p.plan.meta} />}

          {(isCreator || isManager) && (
            <Card>
              <CardTitle title="Share" subtitle={p.is_public ? 'Anyone in the workspace can join' : 'Invite code required'} />
              {p.invite_code && (
                <p style={{ fontSize: 14, marginBottom: 10 }}>
                  Invite code: <b className="mono">{p.invite_code}</b>
                </p>
              )}
              <Button
                full
                onClick={() => {
                  navigator.clipboard?.writeText(`${location.origin}/paths/${p.id}`).catch(() => {})
                  toast('Path link copied — share it with the invite code')
                }}
              >
                Copy path link
              </Button>
            </Card>
          )}

          {scoutJobId && <ScoutStatus jobId={scoutJobId} />}

          <Card>
            <CardTitle title="Curated resources" subtitle="Public sources only" />
            {(p.resources || []).length === 0 ? (
              <p className="muted">No public resources yet. They arrive when the resource scout finishes.</p>
            ) : (
              <div className="row-list">
                {p.resources!.map((r, i) => {
                  const shot = r.metadata?.screenshot_base64
                  const thumb = youtubeThumbnail(r.url) || (shot ? `data:image/png;base64,${shot}` : null)
                  return (
                  <a
                    key={i}
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => sendEvent({ user_id: userId, project_id: projectId ?? undefined, type: 'article.opened', resource_id: r.url, context: { path_id: p.id } }).catch(() => {})}
                    style={{ display: 'flex', gap: 10, alignItems: 'center', textDecoration: 'none', color: 'inherit' }}
                  >
                    {thumb && (
                      <img
                        src={thumb}
                        alt=""
                        style={{ width: 64, height: 36, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }}
                      />
                    )}
                    <div style={{ minWidth: 0 }}>
                      <b style={{ fontSize: 13, color: 'var(--primary)' }}>{r.title} ↗</b>
                      <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                        {r.resource_type || r.source || 'resource'} · {r.rationale || 'Curated prerequisite'}
                      </span>
                    </div>
                  </a>
                  )
                })}
              </div>
            )}
          </Card>

          <Card>
            <CardTitle title="Learners" subtitle={`${p.members?.length ?? 0} enrolled`} />
            {(p.members || []).length === 0 ? (
              <p className="muted">Nobody has joined yet.</p>
            ) : (
              <div className="row-list">
                {p.members!.map((m) => (
                  <div key={m.user_id}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                      <b>
                        {m.display_name || 'Learner'} {m.user_id === userId && <span className="badge badge-info">You</span>}
                      </b>
                      <span>
                        {pct(m.progress)} · {m.xp || 0} XP
                      </span>
                    </div>
                    <ProgressBar value={m.progress || 0} />
                    <span className="muted" style={{ fontSize: 11 }}>
                      Joined {timeAgo(m.joined_at)} · streak {m.streak || 0}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {isManager && (
            <Section eyebrow="MANAGE PATH">
              <div style={{ display: 'grid', gap: 10 }}>
                <PathManagerActions pathId={p.id} />
                <NeedsBackend endpoint={`PATCH /api/onboarding/path/${p.id}`}>Editing, reordering, publishing or archiving the path.</NeedsBackend>
              </div>
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}
