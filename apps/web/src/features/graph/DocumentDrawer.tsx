import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getDocumentContent, getGraphNode, listDocuments } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'
import { Skeleton } from '../../components/primitives/Feedback'
import { Drawer, KeyValue } from '../../components/primitives/Layout'
import type { NodeRef, PackItem } from '../../api/types'

/** Something the learner can open: a graph node, a cited range, or a bare document. */
export interface DocTarget {
  title: string
  document_id?: string | null
  node_id?: string | null
  path?: string | null
  start_line?: number | null
  end_line?: number | null
  citation?: string | null
  reasons?: string[]
}

/** Splits "path/to/file.py:12-40" into its parts. Lines are optional. */
export function parseCitation(citation: string): { path: string; start?: number; end?: number } {
  const m = /^(.*?):(\d+)(?:-(\d+))?$/.exec(citation.trim())
  if (!m) return { path: citation.trim() }
  const start = Number(m[2])
  return { path: m[1], start, end: m[3] ? Number(m[3]) : start }
}

export function targetFromItem(item: PackItem): DocTarget {
  return {
    title: item.name,
    document_id: item.document_id,
    node_id: item.node_id,
    path: item.path,
    start_line: item.start_line,
    end_line: item.end_line,
    citation: item.citation,
    reasons: item.reasons,
  }
}

export function targetFromRef(ref: NodeRef): DocTarget {
  return {
    title: ref.name,
    document_id: ref.document_id,
    node_id: ref.node_id,
    path: ref.path,
    start_line: ref.start_line,
    end_line: ref.end_line,
    citation: ref.citation,
    reasons: ref.reasons,
  }
}

export function targetFromCitation(citation: string, path?: string | null, start?: number | null, end?: number | null): DocTarget {
  const parsed = parseCitation(citation)
  return {
    title: (path || parsed.path).split('/').pop() || citation,
    path: path || parsed.path,
    start_line: start ?? parsed.start,
    end_line: end ?? parsed.end,
    citation,
  }
}

function rangeLabel(start?: number | null, end?: number | null) {
  if (start == null) return null
  return end != null && end !== start ? `${start}–${end}` : String(start)
}

function DocBody({ target }: { target: DocTarget }) {
  const { projectId } = useSessionStore()
  const needsLookup = !target.document_id

  const node = useQuery({
    queryKey: ['graph-node', projectId, target.node_id],
    queryFn: () => getGraphNode(projectId!, target.node_id!),
    enabled: needsLookup && !!projectId && !!target.node_id,
    retry: false,
  })
  const docs = useQuery({
    queryKey: ['documents', projectId],
    queryFn: () => listDocuments(projectId!),
    enabled: needsLookup && !!projectId && !!target.path,
  })

  const documentId = useMemo(() => {
    if (target.document_id) return target.document_id
    const fromNode = node.data?.node.document_id
    if (fromNode) return fromNode
    if (!target.path || !docs.data) return null
    const path = target.path
    return (docs.data.find((d) => d.source_name === path) ?? docs.data.find((d) => d.source_name.endsWith(`/${path}`) || path.endsWith(`/${d.source_name}`)))?.id ?? null
  }, [target.document_id, target.path, node.data, docs.data])

  const start = target.start_line ?? node.data?.node.start_line ?? null
  const end = target.end_line ?? node.data?.node.end_line ?? null
  const resolving = needsLookup && !documentId && (node.isLoading || docs.isLoading)

  const content = useQuery({
    queryKey: ['document-content', documentId, start, end],
    queryFn: () => getDocumentContent(documentId!, { start_line: start, end_line: end }),
    enabled: !!documentId,
    retry: false,
  })

  const path = content.data?.path ?? target.path ?? node.data?.node.path ?? undefined
  const lines = content.data ? content.data.content.split('\n') : []
  const firstLine = content.data?.start_line ?? start ?? 1
  const askPrompt = `Explain ${path ?? target.title}${rangeLabel(start, end) ? ` (lines ${rangeLabel(start, end)})` : ''} and how it fits into this codebase.`

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <KeyValue
        rows={[
          ['Path', path ? <span className="mono" key="p">{path}</span> : undefined],
          ['Lines', rangeLabel(content.data?.start_line ?? start, content.data?.end_line ?? end) ?? 'whole file'],
          ['Language', content.data?.language ?? undefined],
        ]}
      />

      {(target.reasons?.length ?? 0) > 0 && (
        <div>
          <p className="eyebrow">WHY IT MATTERS</p>
          <ul className="reason-list">
            {target.reasons!.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="eyebrow">SOURCE</p>
        {resolving || content.isLoading ? (
          <Skeleton height={160} />
        ) : !documentId ? (
          <p className="muted">This reference is not linked to an indexed document, so there is no preview. Try searching for it in the repository map.</p>
        ) : content.isError ? (
          <p role="alert" style={{ color: 'var(--danger-ink)', fontSize: 13 }}>
            {errorMessage(content.error)}
          </p>
        ) : (
          <>
            <pre className="code-view" tabIndex={0} aria-label={`Source of ${path ?? target.title}`}>
              <code>
                {lines.map((line, i) => (
                  <span key={i} className="code-line">
                    <i aria-hidden="true">{firstLine + i}</i>
                    {line || ' '}
                    {'\n'}
                  </span>
                ))}
              </code>
            </pre>
            {content.data?.truncated && <p className="muted" style={{ marginTop: 6 }}>Preview truncated at 400 lines. Open the repository map for the rest.</p>}
          </>
        )}
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <Link className="btn btn-primary" to={`/assistant?mode=explain&q=${encodeURIComponent(askPrompt)}`}>
          Ask StudyBuddy about this
        </Link>
        <Link className="btn btn-secondary" to={`/repository?q=${encodeURIComponent(path ?? target.title)}`}>
          Find in repository
        </Link>
        {documentId && !content.isLoading && !content.isError && (
          content.data?.external_url ? (
            <a className="btn btn-secondary" href={content.data.external_url} target="_blank" rel="noopener noreferrer">
              Open source ↗
            </a>
          ) : (
            <span className="btn btn-secondary" aria-disabled="true" title="This source has no public location — it was uploaded or indexed from a local workspace" style={{ opacity: 0.5, cursor: 'not-allowed', pointerEvents: 'none' }}>
              Open source (unavailable)
            </span>
          )
        )}
      </div>
    </div>
  )
}

/** Side drawer that shows the cited lines of a document, resolving node ids or paths to a document when needed. */
export function DocumentDrawer({ target, onClose }: { target: DocTarget | null; onClose: () => void }) {
  return (
    <Drawer open={!!target} onClose={onClose} title={target?.title ?? ''}>
      {target && <DocBody key={`${target.node_id ?? ''}|${target.document_id ?? ''}|${target.citation ?? target.path ?? ''}`} target={target} />}
    </Drawer>
  )
}
