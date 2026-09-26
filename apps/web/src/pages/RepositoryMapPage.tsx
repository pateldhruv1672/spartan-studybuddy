import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { getProjectMap, hybridSearch, listDocuments } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { Card, CardTitle, StatCard } from '../components/primitives/Card'
import { EmptyState, Skeleton } from '../components/primitives/Feedback'
import { Drawer, KeyValue, Tabs } from '../components/primitives/Layout'
import { DocumentDrawer, type DocTarget } from '../features/graph/DocumentDrawer'
import { DependencyGraph } from '../features/repository/DependencyGraph'
import type { MapFile, MapSymbol } from '../api/types'

type View = 'overview' | 'files' | 'symbols' | 'graph'

// Common entry-point filenames across the languages this product indexes. A real, checkable signal
// (not a guess): if the repo has one of these, it's almost always where execution starts.
const ENTRY_RE = /^(main|index|app|cli|run|server|manage|__main__)\.[a-z0-9]+$/i

function lines(s: MapSymbol) {
  if (s.start_line == null) return '—'
  return s.end_line && s.end_line !== s.start_line ? `${s.start_line}–${s.end_line}` : String(s.start_line)
}

export function RepositoryMapPage() {
  const { projectId } = useSessionStore()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [view, setView] = useState<View>('overview')
  const [language, setLanguage] = useState<string | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [symbol, setSymbol] = useState<string | null>(params.get('symbol'))
  const [file, setFile] = useState<MapFile | null>(null)
  const [preview, setPreview] = useState<DocTarget | null>(null)
  const [symbolQuery, setSymbolQuery] = useState('')
  const [showExternal, setShowExternal] = useState(false)
  const [focusOnly, setFocusOnly] = useState(true)

  const map = useQuery({ queryKey: ['repository-map', projectId], queryFn: () => getProjectMap(projectId!), enabled: !!projectId })
  const docs = useQuery({ queryKey: ['documents', projectId], queryFn: () => listDocuments(projectId!), enabled: !!projectId })
  const search = useMutation({ mutationFn: (q: string) => hybridSearch({ project_id: projectId!, query: q, top_k: 12 }) })

  const docName = useMemo(() => new Map((docs.data || []).map((d) => [d.id, d.source_name])), [docs.data])
  const docId = useMemo(() => new Map((docs.data || []).map((d) => [d.source_name, d.id])), [docs.data])

  // Debounced search: 250ms after 2+ characters, replacing any in-flight query.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2 || !projectId) return
    const t = setTimeout(() => search.mutate(q), 250)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, projectId])

  useEffect(() => {
    const next = new URLSearchParams(params)
    if (symbol) next.set('symbol', symbol)
    else next.delete('symbol')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  const allFiles = map.data?.files || []
  const allSymbols = map.data?.symbols || []
  const allEdges = map.data?.edges || []
  const languages = Object.entries(map.data?.languages || {}).sort((a, b) => b[1] - a[1])
  const kinds = Array.from(new Set(allSymbols.map((s) => s.kind))).sort()
  const symbols = allSymbols.filter((s) => (!language || s.language === language) && (!kind || s.kind === kind) && (!symbolQuery || s.name.toLowerCase().includes(symbolQuery.toLowerCase())))
  const files = allFiles.filter((f) => !language || f.language === language)
  const visibleNames = new Set(symbols.map((s) => s.name))
  const edges = allEdges.filter((e) => (!language && !kind) || visibleNames.has(e.source_symbol))

  // A symbol only counts as "internal" if the repo actually defines it -- code_symbols only ever holds
  // real extracted definitions, so this is a fact about the indexed repo, not a fabricated category.
  // Anything an edge points at that isn't in this set is a builtin, stdlib call, or external library.
  const internalNames = useMemo(() => new Set(allSymbols.map((s) => s.name)), [allSymbols])
  const degreeBySymbol = useMemo(() => {
    const d = new Map<string, number>()
    for (const e of allEdges) {
      d.set(e.source_symbol, (d.get(e.source_symbol) || 0) + 1)
      d.set(e.target_symbol, (d.get(e.target_symbol) || 0) + 1)
    }
    return d
  }, [allEdges])
  const degreeByFile = useMemo(() => {
    const d = new Map<string, number>()
    for (const s of allSymbols) {
      const f = docName.get(s.document_id)
      if (!f) continue
      d.set(f, (d.get(f) || 0) + (degreeBySymbol.get(s.name) || 0))
    }
    return d
  }, [allSymbols, docName, degreeBySymbol])
  const symbolCountByFile = useMemo(() => {
    const d = new Map<string, number>()
    for (const s of allSymbols) {
      const f = docName.get(s.document_id)
      if (f) d.set(f, (d.get(f) || 0) + 1)
    }
    return d
  }, [allSymbols, docName])

  const importantFiles = useMemo(
    () => [...allFiles].filter((f) => (degreeByFile.get(f.source_name) || 0) > 0).sort((a, b) => (degreeByFile.get(b.source_name) || 0) - (degreeByFile.get(a.source_name) || 0)).slice(0, 8),
    [allFiles, degreeByFile]
  )
  const entryPoints = useMemo(() => allFiles.filter((f) => ENTRY_RE.test(f.source_name.split('/').pop() || '')), [allFiles])
  const majorSymbols = useMemo(
    () => [...allSymbols].filter((s) => (degreeBySymbol.get(s.name) || 0) > 0).sort((a, b) => (degreeBySymbol.get(b.name) || 0) - (degreeBySymbol.get(a.name) || 0)).slice(0, 10),
    [allSymbols, degreeBySymbol]
  )
  const subsystems = useMemo(() => {
    const groups = new Map<string, MapFile[]>()
    for (const f of allFiles) {
      const dir = f.source_name.includes('/') ? f.source_name.slice(0, f.source_name.lastIndexOf('/')) : '(root)'
      groups.set(dir, [...(groups.get(dir) || []), f])
    }
    return Array.from(groups.entries()).sort((a, b) => b[1].length - a[1].length)
  }, [allFiles])

  const tree = useMemo(() => {
    const groups = new Map<string, MapFile[]>()
    for (const f of files) {
      const dir = f.source_name.includes('/') ? f.source_name.slice(0, f.source_name.lastIndexOf('/')) : '(root)'
      groups.set(dir, [...(groups.get(dir) || []), f])
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [files])

  const internalEdgeCount = edges.filter((e) => internalNames.has(e.source_symbol) && internalNames.has(e.target_symbol)).length
  const graphEdges = useMemo(() => {
    let e = showExternal ? edges : edges.filter((x) => internalNames.has(x.source_symbol) && internalNames.has(x.target_symbol))
    if (symbol && focusOnly) e = e.filter((x) => x.source_symbol === symbol || x.target_symbol === symbol)
    return e
  }, [edges, internalNames, showExternal, symbol, focusOnly])

  const selectedSymbol = allSymbols.find((s) => s.name === symbol)
  const outgoing = allEdges.filter((e) => e.source_symbol === symbol)
  const incoming = allEdges.filter((e) => e.target_symbol === symbol)
  const fileSymbols = file ? allSymbols.filter((s) => docName.get(s.document_id) === file.source_name) : []

  if (!projectId) return null

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">REPOSITORY INTELLIGENCE</p>
          <h1>The codebase, made navigable.</h1>
          <p>Files, symbols and their dependencies, extracted at symbol boundaries. Every search hit cites its file and line range.</p>
        </div>
      </div>

      {map.isLoading ? (
        <Skeleton height={100} />
      ) : (
        <div className="grid-4">
          <StatCard label="Indexed files" value={String(map.data?.documents ?? 0)} />
          <StatCard label="Symbols" value={String(map.data?.symbols.length ?? 0)} />
          <StatCard label="Dependencies" value={String(map.data?.edges.length ?? 0)} />
          <StatCard label="Languages" value={String(languages.length)} />
        </div>
      )}

      <div className="section" style={{ display: 'flex', gap: 8 }}>
        <input
          aria-label="Search the repository"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && query.trim() && search.mutate(query.trim())}
          placeholder="Search functions, classes, docs, architecture decisions…"
          style={{ flex: 1, border: '1px solid var(--border)', borderRadius: 14, padding: '14px 16px', background: 'var(--surface)', fontSize: 15 }}
        />
        {query && (
          <button
            className="btn btn-secondary"
            onClick={() => {
              setQuery('')
              search.reset()
            }}
          >
            Clear
          </button>
        )}
      </div>

      {search.isPending && <div style={{ marginTop: 14 }}><Skeleton height={80} /></div>}
      {search.isError && <p style={{ color: 'var(--danger-ink)', marginTop: 12 }}>{errorMessage(search.error)}</p>}
      {search.data && query.trim().length >= 2 && (
        <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
          <p className="muted">
            {search.data.results.length} result{search.data.results.length === 1 ? '' : 's'} for <b>{query}</b>
          </p>
          {search.data.results.map((hit, i) => (
            <div key={i} className="card-flat">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                <b style={{ fontSize: 14 }}>{hit.source_name}</b>
                {hit.citation && <span className="mono" style={{ fontSize: 11, color: 'var(--primary)' }}>{hit.citation}</span>}
              </div>
              <pre className="mono" style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'pre-wrap', maxHeight: 150, overflow: 'hidden', margin: 0 }}>
                {(hit.content || '').slice(0, 700)}
              </pre>
            </div>
          ))}
        </div>
      )}

      <div className="section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Tabs<View>
            value={view}
            onChange={setView}
            tabs={[
              { id: 'overview', label: 'Overview' },
              { id: 'files', label: 'Files' },
              { id: 'symbols', label: 'Symbols' },
              { id: 'graph', label: 'Graph' },
            ]}
          />
          {(view === 'files' || view === 'symbols') && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
              {languages.map(([l]) => (
                <button key={l} className="chip-toggle" aria-pressed={language === l} onClick={() => setLanguage(language === l ? null : l)}>
                  {l}
                </button>
              ))}
              {view === 'symbols' &&
                kinds.map((k) => (
                  <button key={k} className="chip-toggle" aria-pressed={kind === k} onClick={() => setKind(kind === k ? null : k)}>
                    {k}
                  </button>
                ))}
            </div>
          )}
        </div>

        {map.isLoading ? (
          <div className="card"><Skeleton height={260} /></div>
        ) : (map.data?.documents ?? 0) === 0 ? (
          <div className="card">
            <EmptyState title="Nothing indexed yet" description="Connect a repository or upload documents to build the map." action={<Link className="btn btn-primary" to="/sources">Add knowledge</Link>} />
          </div>
        ) : view === 'overview' ? (
          <div className="split">
            <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
              <Card>
                <CardTitle title="Subsystems" subtitle="Top-level directories, by how many files they hold" />
                <div className="row-list">
                  {subsystems.slice(0, 10).map(([dir, entries]) => (
                    <button
                      key={dir}
                      className="row-btn"
                      onClick={() => {
                        setLanguage(null)
                        setView('files')
                      }}
                    >
                      <b className="mono" style={{ fontSize: 13 }}>{dir}/</b>
                      <span className="muted">{entries.length} file{entries.length === 1 ? '' : 's'}</span>
                    </button>
                  ))}
                </div>
              </Card>
              <Card>
                <CardTitle title="Where to start" subtitle="Likely entry points, by filename convention" />
                {entryPoints.length === 0 ? (
                  <p className="muted">No conventional entry-point filename (main, index, app, cli, run, server) found.</p>
                ) : (
                  <div className="row-list">
                    {entryPoints.map((f) => (
                      <button key={f.source_name} className="row-btn" onClick={() => setFile(f)}>
                        <b className="mono" style={{ fontSize: 13 }}>{f.source_name}</b>
                        <span className="badge badge-neutral">{f.language || f.source_type}</span>
                      </button>
                    ))}
                  </div>
                )}
              </Card>
            </div>
            <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
              <Card>
                <CardTitle title="Most-connected files" subtitle="Ranked by dependency edges touching their symbols" />
                {importantFiles.length === 0 ? (
                  <p className="muted">No dependency edges extracted yet.</p>
                ) : (
                  <div className="row-list">
                    {importantFiles.map((f) => (
                      <button key={f.source_name} className="row-btn" onClick={() => setFile(f)}>
                        <b className="mono" style={{ fontSize: 13 }}>{f.source_name}</b>
                        <span className="muted">{degreeByFile.get(f.source_name) || 0} connections</span>
                      </button>
                    ))}
                  </div>
                )}
              </Card>
              <Card>
                <CardTitle title="Major symbols" subtitle="Most-referenced functions, classes and methods" />
                {majorSymbols.length === 0 ? (
                  <p className="muted">No dependency edges extracted yet.</p>
                ) : (
                  <div className="row-list">
                    {majorSymbols.map((s, i) => (
                      <button key={`${s.name}-${i}`} className="row-btn" onClick={() => setSymbol(s.name)}>
                        <span className="mono" style={{ fontWeight: 700, fontSize: 13 }}>{s.name}</span>
                        <span className="muted">{s.kind} · {degreeBySymbol.get(s.name) || 0}</span>
                      </button>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          </div>
        ) : (
          <div className="card">
            {view === 'files' ? (
              <div style={{ display: 'grid', gap: 14 }}>
                {tree.map(([dir, entries]) => (
                  <div key={dir}>
                    <p className="mono" style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 4 }}>
                      {dir}/
                    </p>
                    <div className="row-list">
                      {entries.map((f) => (
                        <button key={f.source_name} className="row-btn" onClick={() => setFile(f)}>
                          <b className="mono" style={{ fontSize: 13 }}>
                            {f.source_name.split('/').pop()}
                          </b>
                          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                            <span className="muted" style={{ fontSize: 11 }}>
                              {symbolCountByFile.get(f.source_name) || 0} symbols · {degreeByFile.get(f.source_name) || 0} conn.
                            </span>
                            <span className="badge badge-neutral">{f.language || f.source_type}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : view === 'symbols' ? (
              <>
                <input
                  aria-label="Filter symbols by name"
                  value={symbolQuery}
                  onChange={(e) => setSymbolQuery(e.target.value)}
                  placeholder="Filter symbols by name…"
                  style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 10, padding: '9px 12px', background: 'var(--surface)', fontSize: 13, marginBottom: 12 }}
                />
                {symbols.length === 0 ? (
                  <p className="muted">No symbols match these filters.</p>
                ) : (
                  <table className="table">
                    <caption>{symbols.length} indexed symbols</caption>
                    <thead>
                      <tr>
                        <th scope="col">Name</th>
                        <th scope="col">Kind</th>
                        <th scope="col">File</th>
                        <th scope="col">Lines</th>
                        <th scope="col">Connections</th>
                      </tr>
                    </thead>
                    <tbody>
                      {symbols.slice(0, 200).map((s, i) => (
                        <tr key={`${s.name}-${i}`}>
                          <td>
                            <button className="btn-ghost mono" style={{ border: 0, background: 'none', color: 'var(--primary)', cursor: 'pointer', fontWeight: 700 }} onClick={() => setSymbol(s.name)}>
                              {s.name}
                            </button>
                          </td>
                          <td>{s.kind}</td>
                          <td className="mono" style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
                            {docName.get(s.document_id) ?? '—'}
                          </td>
                          <td className="mono" style={{ fontSize: 12 }}>
                            {lines(s)}
                          </td>
                          <td className="mono" style={{ fontSize: 12 }}>
                            {degreeBySymbol.get(s.name) || 0}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : (
              <div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
                  {symbol && (
                    <button className="chip-toggle" aria-pressed={focusOnly} onClick={() => setFocusOnly((v) => !v)}>
                      Focused on {symbol}
                    </button>
                  )}
                  <button className="chip-toggle" aria-pressed={showExternal} onClick={() => setShowExternal((v) => !v)}>
                    Show external & builtin references
                  </button>
                  {!showExternal && (
                    <span className="muted" style={{ fontSize: 12 }}>
                      Showing internal project relationships ({internalEdgeCount} of {edges.length}). Builtins, stdlib calls and external libraries are hidden by default.
                    </span>
                  )}
                </div>
                <DependencyGraph edges={graphEdges} selected={symbol} onSelect={setSymbol} />
              </div>
            )}
          </div>
        )}
      </div>

      <Drawer open={!!symbol} onClose={() => setSymbol(null)} title={symbol ?? ''}>
        {symbol && (
          <div style={{ display: 'grid', gap: 20 }}>
            <KeyValue
              rows={[
                ['Kind', selectedSymbol?.kind ?? 'referenced symbol'],
                ['File', selectedSymbol ? docName.get(selectedSymbol.document_id) : 'Outside the indexed code'],
                ['Lines', selectedSymbol ? lines(selectedSymbol) : '—'],
                ['Language', selectedSymbol?.language],
              ]}
            />
            <div>
              <p className="eyebrow">USES ({outgoing.length})</p>
              {outgoing.length === 0 ? <p className="muted">None found.</p> : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {outgoing.map((e, i) => (
                    <button key={i} className="citation-chip" onClick={() => setSymbol(e.target_symbol)}>
                      {e.edge_type} → {e.target_symbol}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="eyebrow">USED BY ({incoming.length})</p>
              {incoming.length === 0 ? <p className="muted">None found.</p> : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {incoming.map((e, i) => (
                    <button key={i} className="citation-chip" onClick={() => setSymbol(e.source_symbol)}>
                      {e.source_symbol} → {e.edge_type}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Link
                className="btn btn-primary"
                to={`/assistant?mode=qa&q=${encodeURIComponent(`What does ${symbol} do${selectedSymbol ? ` in ${docName.get(selectedSymbol.document_id) ?? 'the codebase'}` : ''}?`)}`}
              >
                Ask StudyBuddy about this
              </Link>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setQuery(symbol)
                  setSymbol(null)
                }}
              >
                Search mentions
              </button>
              {(outgoing.length > 0 || incoming.length > 0) && (
                <button className="btn btn-secondary" onClick={() => { setFocusOnly(true); setShowExternal(false); setView('graph') }}>
                  Focused graph
                </button>
              )}
            </div>
            <button className="btn btn-secondary" disabled={!selectedSymbol} onClick={() => { if (selectedSymbol) setPreview({ title: selectedSymbol.name, document_id: selectedSymbol.document_id, start_line: selectedSymbol.start_line, end_line: selectedSymbol.end_line }) }}>Preview code</button>
          </div>
        )}
      </Drawer>

      <Drawer open={!!file} onClose={() => setFile(null)} title={file?.source_name.split('/').pop() ?? ''}>
        {file && (
          <div style={{ display: 'grid', gap: 20 }}>
            <KeyValue
              rows={[
                ['Path', <span className="mono" key="p">{file.source_name}</span>],
                ['Type', file.source_type],
                ['Language', file.language],
                ['Symbols', String(symbolCountByFile.get(file.source_name) || 0)],
                ['Connections', String(degreeByFile.get(file.source_name) || 0)],
              ]}
            />
            <div>
              <p className="eyebrow">SYMBOLS IN THIS FILE ({fileSymbols.length})</p>
              {fileSymbols.length === 0 ? (
                <p className="muted">No code symbols — this is likely documentation.</p>
              ) : (
                <div className="row-list">
                  {fileSymbols.map((s, i) => (
                    <button key={i} className="row-btn" onClick={() => { setFile(null); setSymbol(s.name) }}>
                      <b className="mono" style={{ fontSize: 13 }}>{s.name}</b>
                      <span className="muted">{s.kind} · {lines(s)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="btn btn-secondary" onClick={() => setPreview({ title: file.source_name, document_id: docId.get(file.source_name), path: file.source_name })}>Preview file</button>
          </div>
        )}
      </Drawer>
      <DocumentDrawer target={preview} onClose={() => setPreview(null)} />
    </div>
  )
}
