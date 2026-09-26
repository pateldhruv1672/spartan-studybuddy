import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ingestSource, listDocuments, listSources, uploadSource } from '../api/endpoints'
import { errorMessage } from '../api/client'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { Button } from '../components/primitives/Button'
import { Badge, statusTone } from '../components/primitives/Badge'
import { TextField } from '../components/primitives/Field'
import { EmptyState, Skeleton } from '../components/primitives/Feedback'
import { Drawer, KeyValue, NeedsBackend, Section, Tabs, timeAgo } from '../components/primitives/Layout'
import type { SourceRecord } from '../api/types'

type AddTab = 'github' | 'upload' | 'web' | 'gdrive'
type UploadState = { name: string; status: 'queued' | 'uploading' | 'indexed' | 'failed'; error?: string }

const KIND_LABEL: Record<string, string> = {
  github: 'GitHub repository',
  web: 'Web page',
  gdrive: 'Google Drive',
  upload: 'Uploaded file',
  auto: 'Link',
}
const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.txt,.md,.markdown,.html,.htm,.json,.yaml,.yml,.ipynb,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.h,.cs,.rb,.php,.sql,.sh,.scala,.kt,.swift'
const MAX_PARALLEL = 3

/** Never display credentials that may be embedded in a URI (https://user:token@host/...). */
function safeUri(uri?: string | null) {
  if (!uri) return 'Local upload'
  try {
    const u = new URL(uri)
    u.username = ''
    u.password = ''
    return u.protocol === 'file:' ? 'Local upload' : u.toString()
  } catch {
    return uri
  }
}

function validRepoUrl(url: string) {
  return /^https:\/\/[\w.-]+\/[\w.-]+\/[\w.-]+/.test(url) || /^git@[\w.-]+:[\w.-]+\/[\w.-]+/.test(url) || /^ssh:\/\//.test(url)
}

export function SourcesPage() {
  const { userId, projectId } = useSessionStore()
  const qc = useQueryClient()
  const [tab, setTab] = useState<AddTab>('github')
  const [uri, setUri] = useState('')
  const [branch, setBranch] = useState('')
  const [token, setToken] = useState('')
  const [uploads, setUploads] = useState<UploadState[]>([])
  const [filter, setFilter] = useState<string | null>(null)
  const [selected, setSelected] = useState<SourceRecord | null>(null)
  const [listTab, setListTab] = useState<'sources' | 'documents'>('sources')

  const sources = useQuery({ queryKey: ['sources', projectId], queryFn: () => listSources(projectId!), enabled: !!projectId })
  const documents = useQuery({ queryKey: ['documents', projectId], queryFn: () => listDocuments(projectId!), enabled: !!projectId })

  const refreshKnowledge = () => {
    for (const key of [['sources', projectId], ['documents', projectId], ['repository-map', projectId]]) qc.invalidateQueries({ queryKey: key })
  }

  const ingest = useMutation({
    mutationFn: () =>
      ingestSource({
        user_id: userId,
        project_id: projectId!,
        uri: uri.trim(),
        kind: tab === 'upload' ? 'auto' : tab,
        branch: tab === 'github' ? branch || null : null,
        access_token: token || null,
      }),
    onSuccess: (r) => {
      toast(`Connected and indexed ${r.files ?? 1} file(s)`)
      setUri('')
      setBranch('')
      refreshKnowledge()
    },
    onError: (e) => toast(errorMessage(e)),
    // The token is single-use: clear it whether the request succeeded or failed.
    onSettled: () => setToken(''),
  })

  async function uploadFiles(list: FileList) {
    const files = Array.from(list)
    setUploads(files.map((f) => ({ name: f.name, status: 'queued' })))
    const setStatus = (i: number, patch: Partial<UploadState>) => setUploads((u) => u.map((x, j) => (j === i ? { ...x, ...patch } : x)))
    let next = 0
    async function worker() {
      while (next < files.length) {
        const i = next++
        setStatus(i, { status: 'uploading' })
        try {
          await uploadSource(projectId!, files[i])
          setStatus(i, { status: 'indexed' })
          refreshKnowledge()
        } catch (e) {
          setStatus(i, { status: 'failed', error: errorMessage(e) })
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL, files.length) }, worker))
  }

  const repoInvalid = tab === 'github' && uri.trim().length > 0 && !validRepoUrl(uri.trim())
  const kinds = Array.from(new Set((sources.data || []).map((s) => s.kind)))
  const shown = (sources.data || []).filter((s) => !filter || s.kind === filter)
  const docsForSelected = selected ? (documents.data || []).filter((d) => d.source_id === selected.id) : []

  if (!projectId) return null

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">KNOWLEDGE</p>
          <h1>Everything the team knows, grounded in source.</h1>
          <p>Connect private repositories, documents, Drive files and web pages. Access tokens are used once for the request and never stored or shown.</p>
        </div>
      </div>

      <div className="card">
        <Tabs<AddTab>
          value={tab}
          onChange={(t) => {
            setTab(t)
            setUri('')
            setToken('')
          }}
          tabs={[
            { id: 'github', label: 'GitHub repository' },
            { id: 'upload', label: 'Upload files' },
            { id: 'web', label: 'Web page or PDF link' },
            { id: 'gdrive', label: 'Google Drive' },
          ]}
        />

        {tab === 'upload' ? (
          <div style={{ display: 'grid', gap: 14 }}>
            <label
              style={{ display: 'block', border: '1.5px dashed var(--border)', borderRadius: 16, padding: 32, textAlign: 'center', cursor: 'pointer', background: 'var(--bg)' }}
            >
              <input type="file" multiple accept={ACCEPT} style={{ display: 'none' }} onChange={(e) => e.target.files?.length && uploadFiles(e.target.files)} />
              <b style={{ display: 'block', fontSize: 16, marginBottom: 6 }}>Choose files to upload</b>
              <span className="muted">PDF, DOCX, PPTX, XLSX, TXT, Markdown, HTML, JSON, YAML, notebooks (.ipynb) and source code</span>
            </label>
            {uploads.length > 0 && (
              <div className="row-list" aria-live="polite">
                {uploads.map((u, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13 }}>
                    <span className="mono">{u.name}</span>
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {u.error && <span style={{ color: 'var(--danger-ink)', fontSize: 12 }}>{u.error}</span>}
                      <Badge tone={u.status === 'indexed' ? 'success' : u.status === 'failed' ? 'danger' : u.status === 'uploading' ? 'warning' : 'neutral'}>{u.status}</Badge>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (!repoInvalid && uri.trim()) ingest.mutate()
            }}
            style={{ display: 'grid', gap: 14 }}
          >
            <TextField
              label={tab === 'github' ? 'Repository URL' : tab === 'gdrive' ? 'Drive, Docs, Slides or Sheets link' : 'Page or PDF URL'}
              value={uri}
              onChange={(e) => setUri(e.target.value)}
              placeholder={tab === 'github' ? 'https://github.com/org/repo  or  git@github.com:org/repo.git' : tab === 'gdrive' ? 'https://docs.google.com/document/d/…' : 'https://docs.example.com/architecture'}
              aria-invalid={repoInvalid}
              hint={repoInvalid ? 'Use an HTTPS or SSH repository URL.' : undefined}
            />
            {tab === 'github' && <TextField label="Branch (optional)" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />}
            {tab !== 'web' && (
              <TextField
                label={tab === 'github' ? 'Access token for private repositories (optional)' : 'Access token (needed for folders and private files)'}
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                hint="Used for this request only. Never stored, logged or shown again."
              />
            )}
            <div>
              <Button type="submit" variant="primary" pending={ingest.isPending} disabled={!uri.trim() || repoInvalid}>
                {ingest.isPending ? 'Indexing…' : 'Connect and index'}
              </Button>
            </div>
          </form>
        )}
      </div>

      <Section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <Tabs<'sources' | 'documents'>
            value={listTab}
            onChange={setListTab}
            tabs={[
              { id: 'sources', label: `Sources (${sources.data?.length ?? 0})` },
              { id: 'documents', label: `Indexed documents (${documents.data?.length ?? 0})` },
            ]}
          />
          {listTab === 'sources' && kinds.length > 1 && (
            <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
              {kinds.map((k) => (
                <button key={k} className="chip-toggle" aria-pressed={filter === k} onClick={() => setFilter(filter === k ? null : k)}>
                  {KIND_LABEL[k] || k}
                </button>
              ))}
            </div>
          )}
        </div>

        {listTab === 'sources' ? (
          sources.isLoading ? (
            <Skeleton height={120} />
          ) : shown.length === 0 ? (
            <EmptyState title="No sources connected" description="Add a GitHub repository, upload files, or paste a link above." />
          ) : (
            <div className="grid-2">
              {shown.map((s) => (
                <button key={s.id} className="card-flat" style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => setSelected(s)}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <span className="eyebrow" style={{ margin: 0 }}>
                      {KIND_LABEL[s.kind] || s.kind}
                    </span>
                    <Badge tone={statusTone(s.status)}>{s.status}</Badge>
                  </div>
                  <h3 style={{ fontSize: 16, margin: '8px 0 4px' }}>{s.name}</h3>
                  <p className="muted mono" style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {safeUri(s.uri)}
                  </p>
                </button>
              ))}
            </div>
          )
        ) : documents.isLoading ? (
          <Skeleton height={120} />
        ) : (documents.data?.length ?? 0) === 0 ? (
          <EmptyState title="No documents indexed" description="Indexed files appear here after a source is connected." />
        ) : (
          <div className="card">
            <table className="table">
              <caption>Documents in the search index</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">Language</th>
                  <th scope="col">Indexed</th>
                </tr>
              </thead>
              <tbody>
                {documents.data!.map((d) => (
                  <tr key={d.id}>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {d.source_name} {d.metadata?.demo ? <span className="badge badge-warning">Demo data</span> : null}
                    </td>
                    <td>{d.source_type}</td>
                    <td>{d.language || '—'}</td>
                    <td className="muted">{timeAgo(d.indexed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ''}>
        {selected && (
          <div style={{ display: 'grid', gap: 20 }}>
            <KeyValue
              rows={[
                ['Type', KIND_LABEL[selected.kind] || selected.kind],
                ['Status', <Badge key="s" tone={statusTone(selected.status)}>{selected.status}</Badge>],
                ['Address', <span key="u" className="mono" style={{ fontSize: 12 }}>{safeUri(selected.uri)}</span>],
                ['Connected', selected.created_at ? new Date(selected.created_at).toLocaleString() : '—'],
                ['Commit', (selected.metadata as Record<string, string> | undefined)?.commit],
                ['Error', (selected.metadata as Record<string, string> | undefined)?.error],
              ]}
            />
            <div>
              <p className="eyebrow">INDEXED DOCUMENTS ({docsForSelected.length})</p>
              {docsForSelected.length === 0 ? (
                <p className="muted">None linked to this source.</p>
              ) : (
                <div className="row-list">
                  {docsForSelected.slice(0, 50).map((d) => (
                    <div key={d.id} className="mono" style={{ fontSize: 12 }}>
                      {d.source_name}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <NeedsBackend endpoint={`POST /api/sources/${selected.id}/reindex`}>Re-indexing a failed or out-of-date source.</NeedsBackend>
            <NeedsBackend endpoint={`DELETE /api/sources/${selected.id}`}>Removing this source and its indexed chunks and symbols.</NeedsBackend>
          </div>
        )}
      </Drawer>
    </div>
  )
}
