import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { createOnboarding, getGraphStatus, getKnowledgePack, listRoleProfiles, matchRole, rebuildGraph, startRoleOnboarding } from '../api/endpoints'
import { errorMessage, isAppError } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { pct } from '../app/hooks'
import { toast } from '../app/uiStore'
import { Badge } from '../components/primitives/Badge'
import { Button } from '../components/primitives/Button'
import { Card, CardTitle } from '../components/primitives/Card'
import { CitationChip } from '../components/citations/CitationChip'
import { SelectField } from '../components/primitives/Field'
import { EmptyState, ErrorState, Skeleton } from '../components/primitives/Feedback'
import { Section, Tabs, timeAgo } from '../components/primitives/Layout'
import { ProgressBar } from '../components/primitives/ProgressBar'
import { DocumentDrawer, targetFromCitation, targetFromItem, type DocTarget } from '../features/graph/DocumentDrawer'
import { RoleSubgraph } from '../features/graph/RoleSubgraph'
import type { GraphRebuildResult, GraphStatus, KnowledgePack, PackItem, PackSubsystem } from '../api/types'

type Tab = 'pack' | 'graph'
type Level = 'junior' | 'mid' | 'senior'

const LEVELS: Array<{ id: Level; label: string }> = [
  { id: 'junior', label: 'Junior' },
  { id: 'mid', label: 'Mid-level' },
  { id: 'senior', label: 'Senior' },
]

const DEFAULT_ROLE = 'software-engineer'

function isNotBuilt(e: unknown) {
  return isAppError(e) && e.status === 409
}

function safeUrl(url: string) {
  return /^https?:\/\//i.test(url) ? url : undefined
}

function humanize(key: string) {
  return key.replace(/_/g, ' ')
}

/* ---------- Small pieces ---------- */

function Relevance({ value }: { value: number }) {
  const v = Math.max(0, Math.min(1, value))
  return (
    <span className="rel" title="Relevance to this role">
      <span className="rel-bar" role="img" aria-label={`Relevance ${Math.round(v * 100)} percent`}>
        <i style={{ width: `${v * 100}%` }} />
      </span>
      <span aria-hidden="true">{Math.round(v * 100)}%</span>
    </span>
  )
}

function ItemList({ items, onOpen }: { items: PackItem[]; onOpen: (t: DocTarget) => void }) {
  return (
    <ul className="kit-list">
      {items.map((item) => (
        <li key={item.node_id} className="kit-item">
          <div className="kit-item-head">
            <button type="button" className="link-btn" onClick={() => onOpen(targetFromItem(item))}>
              {item.name}
            </button>
            <span className="kit-item-tags">
              <span className="badge badge-neutral">{item.kind}</span>
              <Relevance value={item.relevance} />
            </span>
          </div>
          <div className="kit-item-meta">
            <CitationChip citation={item.citation} onOpen={() => onOpen(targetFromItem(item))} />
            {item.language && <span className="muted">{item.language}</span>}
          </div>
          {item.reasons.length > 0 && (
            <ul className="reason-list" aria-label={`Why ${item.name} matters for this role`}>
              {item.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}

function SubsystemCard({ sub, onOpen }: { sub: PackSubsystem; onOpen: (t: DocTarget) => void }) {
  const [all, setAll] = useState(false)
  const shown = all ? sub.items : sub.items.slice(0, 3)
  return (
    <Card>
      <div className="row row-between row-start">
        <h3 style={{ fontSize: 18 }}>{sub.community.name}</h3>
        <Badge tone="neutral">{sub.community.size} nodes</Badge>
      </div>
      {sub.community.summary && <p className="muted mt-2" style={{ lineHeight: 1.55 }}>{sub.community.summary}</p>}
      <div className="mt-3" style={{ marginBottom: 12 }}>
        <div className="row row-between" style={{ fontSize: 12, marginBottom: 4 }}>
          <span>Relevance to this role</span>
          <b>{pct(sub.relevance)}</b>
        </div>
        <ProgressBar value={sub.relevance} />
      </div>
      {sub.items.length > 0 && (
        <>
          <p className="eyebrow">KEY ITEMS</p>
          <ItemList items={shown} onOpen={onOpen} />
          {sub.items.length > 3 && (
            <button type="button" className="btn btn-ghost" onClick={() => setAll((v) => !v)} aria-expanded={all}>
              {all ? 'Show fewer' : `Show ${sub.items.length - 3} more`}
            </button>
          )}
        </>
      )}
      {(sub.depends_on.length > 0 || sub.used_by.length > 0) && (
        <div className="kit-links mt-3">
          {sub.depends_on.length > 0 && (
            <div>
              <span className="muted">Depends on</span>
              <div>
                {sub.depends_on.map((d) => (
                  <span key={d} className="badge badge-info">
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}
          {sub.used_by.length > 0 && (
            <div>
              <span className="muted">Used by</span>
              <div>
                {sub.used_by.map((d) => (
                  <span key={d} className="badge badge-neutral">
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function GraphBanner({
  status,
  loading,
  isManager,
  building,
  onBuild,
  last,
  notBuilt,
}: {
  status?: GraphStatus
  loading: boolean
  isManager: boolean
  building: boolean
  onBuild: () => void
  last: GraphRebuildResult | null
  notBuilt: boolean
}) {
  const ready = status?.ready ?? !notBuilt
  const stats = useMemo(() => {
    if (last) {
      return [
        ['nodes', String(last.nodes)],
        ['edges', String(last.edges)],
        ['communities', String(last.communities)],
        ['imports resolved', pct(last.import_resolution_rate)],
        ['mentions linked', pct(last.mention_link_rate)],
        ['build time', `${last.seconds.toFixed(1)}s`],
      ] as Array<[string, string]>
    }
    return Object.entries(status?.build?.stats ?? {})
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 6)
      .map(([k, v]) => [humanize(k), /rate|ratio/.test(k) && (v as number) <= 1 ? pct(v as number) : String(v)] as [string, string])
  }, [last, status])

  return (
    <div className={`card-flat graph-banner${status?.stale ? ' stale' : ''}`}>
      <div className="row row-between row-wrap row-start">
        <div style={{ minWidth: 0 }}>
          <div className="row row-wrap" style={{ gap: 'var(--space-2)' }}>
            <b style={{ fontSize: 15 }}>Knowledge graph</b>
            {loading ? (
              <Badge tone="neutral">Checking…</Badge>
            ) : building ? (
              <Badge tone="warning">Building…</Badge>
            ) : status?.building ? (
              <Badge tone="warning">Building elsewhere…</Badge>
            ) : ready ? (
              <Badge tone="success">Ready</Badge>
            ) : (
              <Badge tone="danger">Not built</Badge>
            )}
            {status?.stale && ready && <Badge tone="warning">Out of date</Badge>}
          </div>
          <p className="muted mt-1">
            {status ? `${status.documents} indexed document${status.documents === 1 ? '' : 's'}` : ' '}
            {status?.build?.finished_at ? ` · built ${timeAgo(status.build.finished_at)}` : ''}
          </p>
        </div>
        {isManager && (
          <Button variant={ready ? 'secondary' : 'primary'} pending={building} disabled={status?.building && !building} onClick={onBuild}>
            {building ? 'Building… this can take a minute' : ready ? 'Rebuild knowledge graph' : 'Build knowledge graph'}
          </Button>
        )}
      </div>
      {status?.stale && ready && (
        <p className="stale-note" role="status">
          Sources have changed since this graph was built, so the kit and new roadmaps may miss recent files.{' '}
          {isManager ? 'Rebuild the graph to refresh them.' : 'Ask a manager to rebuild the graph.'}
        </p>
      )}
      {!ready && !loading && !isManager && <p className="muted" style={{ marginTop: 8 }}>A manager needs to build the knowledge graph before role kits are available.</p>}
      {stats.length > 0 && (
        <dl className="graph-stats">
          {stats.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

/* ---------- Page ---------- */

export function KnowledgePackPage() {
  const { user, userId, projectId, role } = useSessionStore()
  const isManager = role === 'manager'
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [pickedRole, setPickedRole] = useState<string | null>(null)
  const [level, setLevel] = useState<Level>('junior')
  const [tab, setTab] = useState<Tab>('graph')
  const [target, setTarget] = useState<DocTarget | null>(null)
  const [lastBuild, setLastBuild] = useState<GraphRebuildResult | null>(null)

  const roles = useQuery({ queryKey: ['role-profiles'], queryFn: listRoleProfiles, staleTime: 5 * 60_000 })
  const title = user?.role_title?.trim() || ''
  const match = useQuery({ queryKey: ['role-match', title], queryFn: () => matchRole(title), enabled: !!title, staleTime: 5 * 60_000, retry: false })
  const matchSettled = !title || match.isSuccess || match.isError

  const roleId = pickedRole ?? (match.data?.role_id || DEFAULT_ROLE)
  const roleList = roles.data?.roles ?? []
  const selectedProfile = roleList.find((r) => r.id === roleId)

  const status = useQuery({
    queryKey: ['graph-status', projectId],
    queryFn: () => getGraphStatus(projectId!),
    enabled: !!projectId,
    retry: false,
    refetchInterval: (q) => (q.state.data?.building ? 4000 : false),
  })
  const pack = useQuery({
    queryKey: ['knowledge-pack', projectId, roleId],
    queryFn: () => getKnowledgePack(projectId!, { role: roleId }),
    enabled: !!projectId && (pickedRole !== null || matchSettled),
    retry: false,
  })
  const notBuilt = isNotBuilt(pack.error)
  const graphReady = status.data ? status.data.ready : pack.isSuccess

  const build = useMutation({
    mutationFn: () => rebuildGraph(projectId!),
    onSuccess: (r) => {
      setLastBuild(r)
      toast(`Graph built: ${r.nodes} nodes, ${r.edges} edges, ${r.communities} communities`)
      qc.invalidateQueries({ queryKey: ['graph-status'] })
      qc.invalidateQueries({ queryKey: ['knowledge-pack'] })
    },
    onError: (e) => toast(errorMessage(e)),
  })

  const generate = useMutation({
    mutationFn: () =>
      createOnboarding({
        user_id: userId,
        project_id: projectId!,
        target_role: pack.data?.role.title ?? selectedProfile?.title ?? roleId,
        level,
        weeks: 4,
        hours_per_week: 8,
        engine: 'graph',
        role_id: roleId,
        quiz_questions: 5,
      }),
    onSuccess: (path) => {
      qc.invalidateQueries({ queryKey: ['paths'] })
      toast('Roadmap generated')
      navigate(`/paths/${path.id}`)
    },
    onError: (e) => toast(errorMessage(e)),
  })

  const startMine = useMutation({
    mutationFn: () => startRoleOnboarding({ user_id: userId, project_id: projectId!, role: roleId, level }),
    onSuccess: (path) => {
      qc.invalidateQueries({ queryKey: ['paths'] })
      qc.invalidateQueries({ queryKey: ['path'] })
      toast('You are enrolled in the onboarding path')
      navigate(`/paths/${path.id}`)
    },
    onError: (e) => toast(errorMessage(e)),
  })

  const data: KnowledgePack | undefined = pack.data
  const conceptName = useMemo(() => new Map((data?.concepts ?? []).map((c) => [c.id, c.name])), [data])

  const sections = useMemo(() => {
    if (!data) return []
    return [
      { id: 'kit-start', label: 'Start here', count: data.start_here.length },
      { id: 'kit-core', label: 'Core modules', count: data.core_modules.length },
      { id: 'kit-subsystems', label: 'Subsystems', count: data.subsystems.length },
      { id: 'kit-docs', label: 'Docs', count: data.docs.length },
      { id: 'kit-links', label: 'Linked resources', count: data.external_links.length },
      { id: 'kit-tech', label: 'Technologies', count: data.technologies.length },
      { id: 'kit-concepts', label: 'Concepts', count: data.concepts.length },
      { id: 'kit-glossary', label: 'Glossary', count: data.glossary.length },
    ].filter((s) => s.count > 0)
  }, [data])

  function jump(id: string) {
    const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    document.getElementById(id)?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  }

  if (!projectId) return null

  const openCitation = (citation: string) => setTarget(targetFromCitation(citation))
  const ctaDisabled = !graphReady || !data
  const roleTitle = data?.role.title ?? selectedProfile?.title ?? 'your role'

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">ONBOARDING KIT</p>
          <h1>Everything a new {roleTitle.toLowerCase()} needs to know.</h1>
          <p>
            Ranked from the knowledge graph of this project: the files, docs and concepts that matter most for the role, each with the reason it matters and a citation you can open.
          </p>
        </div>
      </div>

      <GraphBanner
        status={status.data}
        loading={status.isLoading}
        isManager={isManager}
        building={build.isPending}
        onBuild={() => build.mutate()}
        last={lastBuild}
        notBuilt={notBuilt}
      />

      <div className="card kit-controls section">
        <div className="kit-controls-grid">
          <div>
            <SelectField label="Role" value={roleId} onChange={(e) => setPickedRole(e.target.value)}>
              {!roleList.some((r) => r.id === roleId) && <option value={roleId}>{data?.role.title ?? roleId}</option>}
              {roleList.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </SelectField>
            {pickedRole === null && match.data && match.data.confidence > 0 && (
              <p className="muted" style={{ marginTop: 6 }}>
                Matched from your title "{title}" ({pct(match.data.confidence)} confidence). Pick another role to explore it.
              </p>
            )}
          </div>
          <div>
            <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-muted)', marginBottom: 8 }}>Level</p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {LEVELS.map((l) => (
                <button key={l.id} type="button" className="chip-toggle" aria-pressed={level === l.id} onClick={() => setLevel(l.id)}>
                  {l.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        {(data?.role.description || selectedProfile?.description) && <p className="muted" style={{ marginTop: 12, lineHeight: 1.55 }}>{data?.role.description || selectedProfile?.description}</p>}
        {selectedProfile?.first_contribution && (
          <p style={{ marginTop: 8, fontSize: 13 }}>
            <b>First contribution:</b> <span className="muted">{selectedProfile.first_contribution}</span>
          </p>
        )}
        <div className="kit-cta">
          {isManager && (
            <Button variant="primary" pending={generate.isPending} disabled={ctaDisabled || startMine.isPending} onClick={() => generate.mutate()}>
              {generate.isPending ? 'Building your roadmap…' : 'Generate my roadmap'}
            </Button>
          )}
          <Button variant={isManager ? 'secondary' : 'primary'} pending={startMine.isPending} disabled={ctaDisabled || generate.isPending} onClick={() => startMine.mutate()}>
            Start onboarding for my role
          </Button>
          {ctaDisabled && !pack.isLoading && <span className="muted">{isManager ? 'Build the knowledge graph first.' : 'Available once a manager builds the knowledge graph.'}</span>}
        </div>
        {(generate.isPending || startMine.isPending) && (
          <p className="muted" style={{ marginTop: 8 }}>
            Planning sections and quizzes from the graph. This can take a moment.
          </p>
        )}
      </div>

      {pack.isLoading || (!matchSettled && pickedRole === null) ? (
        <div className="section" style={{ display: 'grid', gap: 14 }}>
          <Skeleton height={140} />
          <Skeleton height={220} />
          <Skeleton height={220} />
        </div>
      ) : notBuilt ? (
        <div className="section card">
          <EmptyState
            title="The knowledge graph has not been built yet"
            description="The onboarding kit is generated from the graph of your indexed code and docs. Build it once and it stays available for every role."
            action={
              isManager ? (
                <Button variant="primary" pending={build.isPending} onClick={() => build.mutate()}>
                  Build knowledge graph
                </Button>
              ) : (
                <span className="muted">Ask a manager to build it from this page.</span>
              )
            }
          />
        </div>
      ) : pack.isError ? (
        <div className="section card">
          <ErrorState message={errorMessage(pack.error)} onRetry={() => pack.refetch()} />
        </div>
      ) : data ? (
        <>
          <div className="section" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <Tabs<Tab>
              value={tab}
              onChange={setTab}
              tabs={[
                { id: 'pack', label: 'Knowledge pack' },
                { id: 'graph', label: 'Role subgraph' },
              ]}
            />
            <span className="muted" style={{ marginBottom: 18 }}>
              {data.stats.files_ranked} files and {data.stats.docs_ranked} docs ranked · generated {timeAgo(data.generated_at)}
              {!data.signals.dense && ' · structure-only ranking'}
            </span>
          </div>

          {tab === 'graph' ? (
            <Card>
              <CardTitle title="Role subgraph" subtitle="The most relevant nodes for this role and how they connect" />
              <RoleSubgraph
                key={`${projectId}:${roleId}:${data.build_id}`}
                nodes={data.subgraph.nodes}
                edges={data.subgraph.edges}
                onOpenNode={(n) => setTarget({ title: n.name, node_id: n.id, path: n.path, reasons: [`${Math.round(n.relevance * 100)}% relevant to ${data.role.title}`] })}
              />
            </Card>
          ) : sections.length === 0 ? (
            <div className="card">
              <EmptyState title="Nothing ranked for this role yet" description="The graph exists but no files, docs or concepts matched. Try another role, or add more sources and rebuild the graph." />
            </div>
          ) : (
            <>
              <nav aria-label="Kit sections" className="kit-jump">
                {sections.map((s) => (
                  <button key={s.id} type="button" className="chip-toggle" onClick={() => jump(s.id)}>
                    {s.label} <span className="muted">{s.count}</span>
                  </button>
                ))}
              </nav>

              {data.start_here.length > 0 && (
                <div id="kit-start">
                  <Section eyebrow="ORIENTATION" title="Start here">
                    <Card>
                      <ItemList items={data.start_here} onOpen={setTarget} />
                    </Card>
                  </Section>
                </div>
              )}

              {data.core_modules.length > 0 && (
                <div id="kit-core">
                  <Section eyebrow="CODE THAT MATTERS" title="Core modules">
                    <Card>
                      <ItemList items={data.core_modules} onOpen={setTarget} />
                    </Card>
                  </Section>
                </div>
              )}

              {data.subsystems.length > 0 && (
                <div id="kit-subsystems">
                  <Section eyebrow="HOW IT FITS TOGETHER" title="Subsystems">
                    <div className="grid-2">
                      {data.subsystems.map((s) => (
                        <SubsystemCard key={s.community.id} sub={s} onOpen={setTarget} />
                      ))}
                    </div>
                  </Section>
                </div>
              )}

              {data.docs.length > 0 && (
                <div id="kit-docs">
                  <Section eyebrow="READ NEXT" title="Docs">
                    <Card>
                      <ItemList items={data.docs} onOpen={setTarget} />
                    </Card>
                  </Section>
                </div>
              )}

              {data.external_links.length > 0 && (
                <div id="kit-links">
                  <Section eyebrow="REFERENCED BY THE PROJECT" title="Linked resources">
                    <Card>
                      <ul className="kit-list">
                        {data.external_links.map((l) => {
                          const href = safeUrl(l.url)
                          return (
                            <li key={l.url} className="kit-item">
                              {href ? (
                                <a href={href} target="_blank" rel="noopener noreferrer">
                                  <b>{l.title || l.host} ↗</b>
                                </a>
                              ) : (
                                <b>{l.title || l.url}</b>
                              )}
                              <div className="kit-item-meta">
                                <span className="muted">{l.host}</span>
                                {l.found_in.slice(0, 3).map((c) => (
                                  <CitationChip key={c} citation={c} onOpen={() => openCitation(c)} label={`Open where this link appears: ${c}`} />
                                ))}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                    </Card>
                  </Section>
                </div>
              )}

              {data.technologies.length > 0 && (
                <div id="kit-tech">
                  <Section eyebrow="STACK" title="Technologies">
                    <div className="tech-grid">
                      {data.technologies.map((t) => (
                        <div key={t.id} className="card-flat tech-card">
                          <b>{t.name}</b>
                          <span className="muted">{t.category}</span>
                          <span className="muted">
                            {t.files} file{t.files === 1 ? '' : 's'}
                          </span>
                          {t.public && <Badge tone="info">Public docs available</Badge>}
                        </div>
                      ))}
                    </div>
                  </Section>
                </div>
              )}

              {data.concepts.length > 0 && (
                <div id="kit-concepts">
                  <Section eyebrow="LEARN IN THIS ORDER" title="Concepts to know">
                    <Card>
                      <ol className="kit-concepts">
                        {data.concepts.map((c) => (
                          <li key={c.id}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                              <b style={{ fontSize: 15 }}>{c.name}</b>
                              <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                <Badge tone="neutral">{c.area}</Badge>
                                <Relevance value={c.weight} />
                              </span>
                            </div>
                            {c.why && <p className="muted" style={{ marginTop: 4, lineHeight: 1.5 }}>{c.why}</p>}
                            {c.prereqs.length > 0 && (
                              <p style={{ fontSize: 12, marginTop: 4 }}>
                                <span className="muted">Builds on:</span> {c.prereqs.map((p) => conceptName.get(p) ?? p).join(', ')}
                              </p>
                            )}
                          </li>
                        ))}
                      </ol>
                    </Card>
                  </Section>
                </div>
              )}

              {data.glossary.length > 0 && (
                <div id="kit-glossary">
                  <Section eyebrow="IN THIS PROJECT'S WORDS" title="Glossary">
                    <Card>
                      <dl className="glossary">
                        {data.glossary.map((g) => (
                          <div key={g.term}>
                            <dt>{g.term}</dt>
                            <dd>
                              {g.definition}
                              {g.source && (
                                <span style={{ display: 'block', marginTop: 6 }}>
                                  <CitationChip citation={g.source} onOpen={() => openCitation(g.source)} />
                                </span>
                              )}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </Card>
                  </Section>
                </div>
              )}
            </>
          )}
        </>
      ) : null}

      <p className="muted section" style={{ textAlign: 'center' }}>
        Prefer to browse on your own? <Link to="/repository">Open the repository map</Link>
      </p>

      <DocumentDrawer target={target} onClose={() => setTarget(null)} />
    </div>
  )
}
