import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { getLeaderboard, getLearnerSnapshot, getResumeFeed, sendEvent, startRoleOnboarding } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { toast } from '../app/uiStore'
import { useSessionStore } from '../app/sessionStore'
import { myMemberships, pct, usePathDetails } from '../app/hooks'
import { Card, CardTitle } from '../components/primitives/Card'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { Badge } from '../components/primitives/Badge'
import { Button } from '../components/primitives/Button'
import { TextAreaField } from '../components/primitives/Field'
import { EmptyState, Skeleton } from '../components/primitives/Feedback'
import { Drawer, NeedsBackend, Section, eventLabel, timeAgo } from '../components/primitives/Layout'
import type { ResumeItem } from '../api/types'

function questionText(q: string | { question?: string }): string {
  return typeof q === 'string' ? q : q?.question || ''
}

function resumeUrl(r: ResumeItem) {
  try {
    const u = new URL(r.resource_url)
    const isYoutube = u.hostname.includes('youtube.com') || u.hostname === 'youtu.be'
    if (isYoutube && r.last_position) u.searchParams.set('t', `${Math.floor(r.last_position)}s`)
    // Non-video resources resume by scroll fraction (the extension reads this hash on load),
    // since an absolute pixel position from a past visit isn't reliable if the page reflows.
    else if (!isYoutube && r.progress) u.hash = `studybuddy-resume=${r.progress.toFixed(3)}`
    return u.toString()
  } catch {
    return r.resource_url
  }
}

function youtubeId(url: string): string | null {
  try {
    const u = new URL(url)
    return u.hostname === 'youtu.be' ? u.pathname.slice(1) : u.hostname.includes('youtube.com') ? u.searchParams.get('v') : null
  } catch {
    return null
  }
}

function clock(seconds?: number) {
  if (!seconds) return null
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

export function LearnerDashboardPage() {
  const { user, userId, projectId } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [recall, setRecall] = useState<{ item: ResumeItem; question: string } | null>(null)
  const [answer, setAnswer] = useState('')
  const [playingId, setPlayingId] = useState<string | number | null>(null)

  const { paths, loading: pathsLoading } = usePathDetails()
  const memberships = myMemberships(paths, userId)
  const active = memberships[0]
  const resume = useQuery({ queryKey: ['resume', userId, projectId], queryFn: () => getResumeFeed(userId, projectId ?? undefined), enabled: !!projectId })
  const learner = useQuery({ queryKey: ['learner', userId, projectId], queryFn: () => getLearnerSnapshot(userId, projectId!), enabled: !!projectId })
  const stats = useQuery({ queryKey: ['leaderboard', projectId], queryFn: () => getLeaderboard(projectId!), enabled: !!projectId })

  const startRole = useMutation({
    mutationFn: (_opts?: { auto?: boolean }) => startRoleOnboarding({ user_id: userId, project_id: projectId! }),
    onSuccess: (path, opts) => {
      qc.invalidateQueries({ queryKey: ['paths'] })
      qc.invalidateQueries({ queryKey: ['path'] })
      if (opts?.auto) return // stay on Home: the path now shows as "Up next"
      toast('You are enrolled in the onboarding path')
      navigate(`/paths/${path.id}`)
    },
    onError: (e) => toast(errorMessage(e)),
  })

  // A new hire opening a workspace gets the roadmap for their role automatically (once per workspace visit).
  const autoFor = useRef<string | null>(null)
  useEffect(() => {
    if (user?.role !== 'learner' || !projectId || pathsLoading || autoFor.current === projectId) return
    autoFor.current = projectId
    if (memberships.length === 0) startRole.mutate({ auto: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role, projectId, pathsLoading, memberships.length])

  const nextItems = useMemo(() => {
    if (!active) return []
    const done = new Set((active.path.progress_items || []).filter((x) => x.status === 'completed').map((x) => x.item_id))
    return (active.path.plan?.modules || []).flatMap((m) => m.items || []).filter((i) => !done.has(i.id)).slice(0, 3)
  }, [active])

  const totalXp = memberships.reduce((s, m) => s + (m.xp || 0), 0)
  const streak = memberships.reduce((s, m) => Math.max(s, m.streak || 0), 0)
  const board = stats.data?.leaderboard || []
  const myRank = board.findIndex((r) => r.user_id === userId)

  function openResource(r: ResumeItem) {
    sendEvent({ user_id: userId, project_id: projectId ?? undefined, type: 'article.opened', resource_id: r.resource_url, context: { from: 'resume_card' } }).catch(() => {})
    window.open(resumeUrl(r), '_blank', 'noopener,noreferrer')
  }

  if (!projectId) return null

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">WELCOME BACK, {user?.display_name?.split(' ')[0]?.toUpperCase()}</p>
          <h1>Pick up exactly where you left off.</h1>
          <p>Time on a page is shown as activity, never as proof you've mastered something.</p>
        </div>
      </div>

      {/* Continue learning hero */}
      {pathsLoading || startRole.isPending ? (
        <div className="card-flat">
          <b>{startRole.isPending ? 'Setting up your roadmap…' : 'Loading…'}</b>
          {startRole.isPending && <p className="muted" style={{ marginTop: 6 }}>Reading the workspace and picking what matters for your role. This takes a few seconds.</p>}
          <Skeleton height={80} />
        </div>
      ) : active && nextItems[0] ? (
        <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, background: 'var(--ink)', color: '#fff' }}>
          <div>
            <p className="eyebrow" style={{ color: '#b8b7b0' }}>
              UP NEXT · {active.path.target_role.toUpperCase()}
            </p>
            <h2 style={{ fontSize: 26 }}>{nextItems[0].title}</h2>
            <p style={{ color: '#d6d5cf', marginTop: 6 }}>
              {nextItems[0].type || 'lesson'} · {nextItems[0].minutes || 15} min · <b style={{ color: 'var(--coral)' }}>+{nextItems[0].xp || 100} XP</b>
            </p>
          </div>
          <button className="btn" style={{ background: '#fff', color: 'var(--ink)' }} onClick={() => navigate(`/study/${active.path.id}/${nextItems[0].id}`)}>
            Continue learning →
          </button>
        </div>
      ) : (
        <EmptyState
          title={active ? 'Path complete' : 'No path yet'}
          description={active ? 'Nice work. Ask your manager for the next milestone.' : startRole.isError ? `We could not set up your roadmap yet: ${errorMessage(startRole.error)}` : 'You can start now: StudyBuddy builds a roadmap for your role from this workspace, with a quiz after every section. No invite code needed.'}
          action={
            active ? (
              <Button variant="primary" onClick={() => navigate('/paths')}>
                See paths
              </Button>
            ) : (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
                <Button variant="primary" pending={startRole.isPending} onClick={() => startRole.mutate()}>
                  Start onboarding for my role
                </Button>
                <Link className="btn btn-secondary" to="/kit">
                  Choose your role first
                </Link>
              </div>
            )
          }
        />
      )}

      {/* Role onboarding */}
      <div className="card-flat section onboarding-card">
        <div style={{ minWidth: 0 }}>
          <p className="eyebrow" style={{ margin: 0 }}>
            YOUR ONBOARDING
          </p>
          <h3 style={{ fontSize: 20, marginTop: 6 }}>{user?.role_title ? `Get productive as ${/^[aeiou]/i.test(user.role_title) ? 'an' : 'a'} ${user.role_title}` : 'Get productive on this codebase'}</h3>
          <p className="muted" style={{ marginTop: 6, lineHeight: 1.55, maxWidth: 560 }}>
            See the files, docs and concepts that matter most for your role, then start a roadmap with a quiz after every section.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <Link className="btn btn-secondary" to="/kit">
            Open onboarding kit
          </Link>
          <Button variant="primary" pending={startRole.isPending} onClick={() => startRole.mutate()}>
            Start onboarding for my role
          </Button>
        </div>
      </div>

      {/* Resume cards */}
      <Section eyebrow="CONTINUE WHERE YOU STOPPED">
        {resume.isLoading && <Skeleton height={180} />}
        {!resume.isLoading && (resume.data?.length ?? 0) === 0 && (
          <div className="card-flat">
            <p className="muted">
              Resume cards appear when you study videos, articles or papers with the Chrome extension. <Link to="/integrations">Connect Chrome</Link>
            </p>
          </div>
        )}
        <div className="grid-3">
          {resume.data?.slice(0, 3).map((r, i) => {
            const vid = youtubeId(r.resource_url)
            const cardKey = r.id ?? i
            return (
            <div key={cardKey} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <Badge tone="info">{r.resource_type || 'resource'}</Badge>
                <span className="muted" style={{ fontSize: 11 }}>
                  {timeAgo(r.last_seen_at)}
                </span>
              </div>
              {vid && (
                <div style={{ position: 'relative', aspectRatio: '16/9', borderRadius: 8, overflow: 'hidden', background: '#000' }}>
                  {playingId === cardKey ? (
                    <iframe
                      src={`https://www.youtube.com/embed/${vid}${r.last_position ? `?start=${Math.floor(r.last_position)}` : ''}&autoplay=1`}
                      title={r.resource_title || 'Video'}
                      allow="accelerate-compute; autoplay; encrypted-media; picture-in-picture"
                      allowFullScreen
                      style={{ width: '100%', height: '100%', border: 0 }}
                    />
                  ) : (
                    <button
                      onClick={() => setPlayingId(cardKey)}
                      style={{ width: '100%', height: '100%', padding: 0, border: 0, cursor: 'pointer', position: 'relative', background: 'none' }}
                      aria-label="Play video"
                    >
                      <img src={`https://img.youtube.com/vi/${vid}/hqdefault.jpg`} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                      <span
                        style={{
                          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 40, color: '#fff', textShadow: '0 2px 8px rgba(0,0,0,.6)',
                        }}
                      >
                        ▶
                      </span>
                    </button>
                  )}
                </div>
              )}
              <h3 style={{ fontSize: 16 }}>{r.resource_title || r.resource_url}</h3>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                  <span>{clock(r.last_position) ? `Stopped at ${clock(r.last_position)}` : 'Progress'}</span>
                  <b>{pct(r.progress)}</b>
                </div>
                <ProgressBar value={r.progress || 0} />
              </div>
              <p className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
                {r.summary || 'A recap appears here once StudyBuddy has read enough of this resource.'}
              </p>
              {(r.concepts?.length ?? 0) > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {r.concepts!.slice(0, 5).map((c) => (
                    <span key={c} className="badge badge-neutral">
                      {c}
                    </span>
                  ))}
                </div>
              )}
              {(r.questions?.length ?? 0) > 0 && (
                <div style={{ background: 'var(--primary-tint)', borderRadius: 10, padding: 12 }}>
                  <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary-strong)', marginBottom: 4 }}>RECALL QUESTION</p>
                  <p style={{ fontSize: 13 }}>{questionText(r.questions![0])}</p>
                  <button
                    className="btn btn-ghost"
                    style={{ padding: '6px 0', minHeight: 30 }}
                    onClick={() => {
                      setAnswer('')
                      setRecall({ item: r, question: questionText(r.questions![0]) })
                    }}
                  >
                    Answer it →
                  </button>
                </div>
              )}
              <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="muted" style={{ fontSize: 11 }}>
                  {Math.round((r.seconds_active || 0) / 60)} min active
                </span>
                <Button variant="primary" onClick={() => openResource(r)}>
                  Resume
                </Button>
              </div>
            </div>
            )
          })}
        </div>
      </Section>

      <div className="grid-3 section">
        <Card>
          <CardTitle title="Onboarding progress" subtitle={active?.path.target_role || 'No path yet'} action={<b style={{ fontSize: 20 }}>{pct(active?.progress)}</b>} />
          <ProgressBar value={active?.progress || 0} />
          <div className="row-list" style={{ marginTop: 12 }}>
            {nextItems.map((item) => (
              <button key={item.id} className="row-btn" onClick={() => navigate(`/study/${active!.path.id}/${item.id}`)}>
                <b style={{ fontSize: 13 }}>{item.title}</b>
                <span className="muted" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                  +{item.xp || 100} XP
                </span>
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <CardTitle title="XP and streak" action={<button className="btn btn-ghost" onClick={() => navigate('/progress')}>Details →</button>} />
          <div style={{ display: 'flex', gap: 24 }}>
            <div>
              <b style={{ fontSize: 34, color: 'var(--coral-ink)' }}>{totalXp}</b>
              <div className="muted" style={{ fontSize: 12 }}>
                total XP
              </div>
            </div>
            <div>
              <b style={{ fontSize: 34 }}>{streak}</b>
              <div className="muted" style={{ fontSize: 12 }}>
                day streak
              </div>
            </div>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            {myRank >= 0 ? `You're #${myRank + 1} on the team leaderboard.` : 'Complete a checkpoint to join the leaderboard.'}
          </p>
        </Card>

        <Card>
          <CardTitle title="Mastery" subtitle="Weakest topics first" />
          {(learner.data?.mastery?.length ?? 0) === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>
              Mastery builds as you pass checkpoints and quizzes.
            </p>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {learner.data!.mastery!.slice(0, 4).map((m) => (
                <div key={m.topic}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span>{m.topic}</span>
                    <b>{pct(m.score)}</b>
                  </div>
                  <ProgressBar value={m.score} />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="split section">
        <Card>
          <CardTitle title="Recent activity" subtitle="Web, Chrome and VS Code" />
          {(learner.data?.recent_events?.length ?? 0) === 0 ? (
            <p className="muted">Nothing yet.</p>
          ) : (
            <div className="row-list">
              {learner.data!.recent_events!.slice(0, 6).map((e) => (
                <div key={e.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>
                    {eventLabel(e.type)} <span className="muted">· {e.source}</span>
                  </span>
                  <span className="muted">{timeAgo(e.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <CardTitle title="Leaderboard" action={<button className="btn btn-ghost" onClick={() => navigate('/leaderboard')}>All →</button>} />
          <div className="row-list">
            {board.slice(0, 5).map((r, i) => (
              <div key={r.user_id ?? i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: r.user_id === userId ? 700 : 400 }}>
                <span>
                  {i + 1}. {r.display_name || 'Learner'} {r.user_id === userId && <span className="badge badge-info">You</span>}
                </span>
                <span className="badge badge-coral">{r.xp ?? 0} XP</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Drawer open={!!recall} onClose={() => setRecall(null)} title="Recall question">
        {recall && (
          <div style={{ display: 'grid', gap: 14 }}>
            <p className="muted">From: {recall.item.resource_title || recall.item.resource_url}</p>
            <p style={{ fontSize: 16 }}>
              <b>{recall.question}</b>
            </p>
            <TextAreaField label="Your answer" value={answer} onChange={(e) => setAnswer(e.target.value)} />
            <Button
              variant="primary"
              disabled={!answer.trim()}
              onClick={() =>
                navigate(
                  `/assistant?mode=socratic&q=${encodeURIComponent(`Recall question: "${recall.question}"\nMy answer: ${answer}\nIs my answer right? Guide me if not.`)}`
                )
              }
            >
              Check my answer with StudyBuddy
            </Button>
            <NeedsBackend endpoint="POST /api/resource/recall">Scoring recall answers automatically and updating mastery.</NeedsBackend>
          </div>
        )}
      </Drawer>
    </div>
  )
}
