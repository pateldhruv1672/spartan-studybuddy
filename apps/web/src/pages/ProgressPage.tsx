import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getLearnerSnapshot, getUserAchievements } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { myMemberships, pct, usePathDetails } from '../app/hooks'
import { Card, CardTitle, StatCard } from '../components/primitives/Card'
import { EmptyState, ErrorState, Skeleton } from '../components/primitives/Feedback'
import { Section, Tabs, eventLabel, timeAgo } from '../components/primitives/Layout'
import { ProgressBar } from '../components/primitives/ProgressBar'

/** XP rules from SPEC §20; awarded by the backend, listed here so learners know how to earn them. */
const XP_RULES: Array<[string, number]> = [
  ['Resource completed', 20],
  ['Checkpoint passed', 30],
  ['Mastery improvement', 50],
  ['Weekly milestone', 100],
  ['Project exercise', 100],
  ['Learning streak', 20],
]

const BADGES = [
  { title: 'First checkpoint', description: 'Pass your first checkpoint' },
  { title: 'Code reader', description: 'Finish a repository walkthrough' },
  { title: 'Seven-day streak', description: 'Learn seven days in a row' },
  { title: 'Question asker', description: 'Ask StudyBuddy ten questions' },
  { title: 'Path finisher', description: 'Complete an onboarding path' },
  { title: 'Bug hunter', description: 'Solve a debugging exercise' },
]

type MemoryTab = 'long' | 'episodic' | 'session'

export function ProgressPage() {
  const { userId, projectId } = useSessionStore()
  const [tab, setTab] = useState<MemoryTab>('long')
  const { paths, loading } = usePathDetails()
  const snapshot = useQuery({ queryKey: ['learner', userId, projectId], queryFn: () => getLearnerSnapshot(userId, projectId!), enabled: !!projectId })

  const achievements = useQuery({
    queryKey: ['achievements', userId, projectId],
    queryFn: () => getUserAchievements(userId, projectId ?? undefined),
    enabled: !!userId,
    retry: false,
  })
  const earned = achievements.data ?? []
  const earnedKeys = new Set(earned.flatMap((a) => [a.title.toLowerCase(), a.badge.toLowerCase()]))

  const memberships = myMemberships(paths, userId)
  const totalXp = memberships.reduce((s, m) => s + (m.xp || 0), 0)
  const bestStreak = memberships.reduce((s, m) => Math.max(s, m.streak || 0), 0)
  const mastery = snapshot.data?.mastery || []
  const memories = snapshot.data?.memories || []
  const events = snapshot.data?.recent_events || []
  const longTerm = memories.filter((m) => ['misconception', 'mastery', 'preference', 'research', 'summary'].includes(m.kind))
  const episodic = memories.filter((m) => !longTerm.includes(m))

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">MY PROGRESS</p>
          <h1>What you've learned so far.</h1>
          <p>XP and streaks come from completed work, never from time spent on a page. StudyBuddy's memory of you is shared by the web app, Chrome and VS Code.</p>
        </div>
      </div>

      {loading ? (
        <Skeleton height={100} />
      ) : (
        <div className="grid-4">
          <StatCard label="Total XP" value={String(totalXp)} />
          <StatCard label="Best streak" value={`${bestStreak} day${bestStreak === 1 ? '' : 's'}`} />
          <StatCard label="Paths joined" value={String(memberships.length)} />
          <StatCard label="Topics tracked" value={String(mastery.length)} />
        </div>
      )}

      <div className="split section">
        <Card>
          <CardTitle title="Path progress" subtitle="Checkpoint-based, measured by the backend" />
          {memberships.length === 0 ? (
            <p className="muted">You haven't joined a path yet. Ask your manager for a path link and invite code.</p>
          ) : (
            <div style={{ display: 'grid', gap: 14 }}>
              {memberships.map((m) => (
                <div key={m.path.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                    <b>{m.path.target_role}</b>
                    <span>
                      {pct(m.progress)} · <b style={{ color: 'var(--coral-ink)' }}>{m.xp || 0} XP</b>
                    </span>
                  </div>
                  <ProgressBar value={m.progress || 0} />
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <CardTitle title="How to earn XP" subtitle="Awarded by the backend when work is confirmed" />
          <div className="row-list">
            {XP_RULES.map(([label, xp]) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span>{label}</span>
                <span className="badge badge-coral">+{xp} XP</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Section eyebrow="ACHIEVEMENTS" title="Badges">
        {achievements.isError && <ErrorState message={errorMessage(achievements.error)} onRetry={() => achievements.refetch()} />}
        {achievements.isLoading && <Skeleton height={110} />}
        {!achievements.isLoading && !achievements.isError && (
          <div className="grid-3">
            {earned.map((a) => (
              <div key={a.badge} className="card-flat achievement earned">
                <div style={{ fontSize: 22, color: 'var(--coral)' }} aria-hidden="true">
                  ★
                </div>
                <b style={{ fontSize: 14 }}>{a.title}</b>
                <p className="muted" style={{ fontSize: 12 }}>
                  {a.description}
                </p>
                <span className="badge badge-coral" style={{ marginTop: 8 }}>
                  Earned {timeAgo(a.earned_at)}
                </span>
              </div>
            ))}
            {BADGES.filter((b) => !earnedKeys.has(b.title.toLowerCase())).map((b) => (
              <div key={b.title} className="card-flat" style={{ opacity: 0.6 }}>
                <div style={{ fontSize: 22 }} aria-hidden="true">
                  ☆
                </div>
                <b style={{ fontSize: 14 }}>{b.title}</b>
                <p className="muted" style={{ fontSize: 12 }}>
                  {b.description}
                </p>
                <span className="badge badge-neutral" style={{ marginTop: 8 }}>
                  Locked
                </span>
              </div>
            ))}
          </div>
        )}
        {earned.length === 0 && !achievements.isLoading && !achievements.isError && (
          <p className="muted" style={{ marginTop: 12 }}>
            No badges yet. Pass a section quiz to earn your first.
          </p>
        )}
      </Section>

      <Section eyebrow="MASTERY" title="Confidence by topic">
        {snapshot.isLoading ? (
          <Skeleton height={120} />
        ) : mastery.length === 0 ? (
          <EmptyState title="No mastery data yet" description="Mastery is measured from checkpoints, quizzes and exercises — not from reading time." />
        ) : (
          <div className="card">
            <div className="row-list">
              {mastery.map((m) => (
                <div key={m.topic}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                    <b>{m.topic}</b>
                    <span>
                      {pct(m.score)} {m.confidence != null && <span className="muted">· confidence {pct(m.confidence)}</span>}
                    </span>
                  </div>
                  <ProgressBar value={m.score} />
                </div>
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section eyebrow="CENTRAL MEMORY" title="What StudyBuddy remembers">
        <Tabs<MemoryTab>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'long', label: 'Long-term' },
            { id: 'episodic', label: 'Episodes' },
            { id: 'session', label: 'Recent activity' },
          ]}
        />
        <div className="card">
          {tab === 'session' ? (
            events.length === 0 ? (
              <p className="muted">No activity yet. Studying in the web app, Chrome or VS Code shows up here.</p>
            ) : (
              <div className="row-list">
                {events.map((e) => (
                  <div key={e.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13 }}>
                    <span>
                      <b>{eventLabel(e.type)}</b> <span className="muted">· from {e.source}</span>
                    </span>
                    <span className="muted">{timeAgo(e.created_at)}</span>
                  </div>
                ))}
              </div>
            )
          ) : (tab === 'long' ? longTerm : episodic).length === 0 ? (
            <p className="muted">Nothing stored here yet.</p>
          ) : (
            <div className="row-list">
              {(tab === 'long' ? longTerm : episodic).map((m) => (
                <div key={m.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <b style={{ fontSize: 14 }}>{m.title}</b>
                    <span className="badge badge-neutral">{m.kind}</span>
                  </div>
                  <p className="muted" style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>
                    {m.content.slice(0, 400)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>
    </div>
  )
}
