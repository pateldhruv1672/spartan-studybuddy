import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { getProjectMap, hybridSearch, listDocuments } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { StatCard } from '../components/primitives/Card'
import { EmptyState, Skeleton } from '../components/primitives/Feedback'
import { Drawer, KeyValue, Tabs } from '../components/primitives/Layout'
import { DocumentDrawer, type DocTarget } from '../features/graph/DocumentDrawer'
import { DependencyGraph } from '../features/repository/DependencyGraph'
import type { MapFile, MapSymbol } from '../api/types'

type View = 'graph' | 'files' | 'symbols'

function lines(s: MapSymbol) {
  if (s.start_line == null) return '—'
  return s.end_line && s.end_line !== s.start_line ? `${s.start_line}–${s.end_line}` : String(s.start_line)
}

export function RepositoryMapPage() {
  const { projectId } = useSessionStore()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [view, setView] = useState<View>('graph')
  const [language, setLanguage] = useState<string | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [symbol, setSymbol] = useState<string | null>(params.get('symbol'))
  const [file, setFile] = useState<MapFile | null>(null)
  const [preview, setPreview] = useState<DocTarget | null>(null)

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

  const languages = Object.entries(map.data?.languages || {}).sort((a, b) => b[1] - a[1])
  const kinds = Array.from(new Set((map.data?.symbols || []).map((s) => s.kind))).sort()
  const symbols = (map.data?.symbols || []).filter((s) => (!language || s.language === language) && (!kind || s.kind === kind))
  const files = (map.data?.files || []).filter((f) => !language || f.language === language)
  const visibleNames = new Set(symbols.map((s) => s.name))
  const edges = (map.data?.edges || []).filter((e) => (!language && !kind) || visibleNames.has(e.source_symbol))

  const tree = useMemo(() => {
    const groups = new Map<string, MapFile[]>()
    for (const f of files) {
      const dir = f.source_name.includes('/') ? f.source_name.slice(0, f.source_name.lastIndexOf('/')) : '(root)'
      groups.set(dir, [...(groups.get(dir) || []), f])
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [files])

  const selectedSymbol = (map.data?.symbols || []).find((s) => s.name === symbol)
  const outgoing = (map.data?.edges || []).filter((e) => e.source_symbol === symbol)
  const incoming = (map.data?.edges || []).filter((e) => e.target_symbol === symbol)
  const fileSymbols = file ? (map.data?.symbols || []).filter((s) => docName.get(s.document_id) === file.source_name) : []

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
              { id: 'graph', label: 'Dependency graph' },
              { id: 'files', label: 'Files' },
              { id: 'symbols', label: 'Symbols' },
            ]}
          />
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
            {languages.map(([l]) => (
              <button key={l} className="chip-toggle" aria-pressed={language === l} onClick={() => setLanguage(language === l ? null : l)}>
                {l}
              </button>
            ))}
            {kinds.map((k) => (
              <button key={k} className="chip-toggle" aria-pressed={kind === k} onClick={() => setKind(kind === k ? null : k)}>
                {k}
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          {map.isLoading ? (
            <Skeleton height={260} />
          ) : (map.data?.documents ?? 0) === 0 ? (
            <EmptyState title="Nothing indexed yet" description="Connect a repository or upload documents to build the map." action={<Link className="btn btn-primary" to="/sources">Add knowledge</Link>} />
          ) : view === 'graph' ? (
            <DependencyGraph edges={edges} selected={symbol} onSelect={setSymbol} />
          ) : view === 'files' ? (
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
                        <span className="badge badge-neutral">{f.language || f.source_type}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : symbols.length === 0 ? (
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
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
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
