import { useQuery } from '@tanstack/react-query'
import { getEvents } from '../api/endpoints'
import { useSessionStore } from '../app/sessionStore'
import { toast } from '../app/uiStore'
import { Badge } from '../components/primitives/Badge'
import { Card, CardTitle } from '../components/primitives/Card'
import { timeAgo } from '../components/primitives/Layout'
import type { LearningEvent } from '../api/types'

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr auto', gap: 10, alignItems: 'center', fontSize: 13 }}>
      <span className="muted">{label}</span>
      <code style={{ background: 'var(--surface-alt)', padding: '8px 10px', borderRadius: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</code>
      <button
        className="btn btn-secondary"
        style={{ padding: '6px 12px', minHeight: 34, fontSize: 12 }}
        onClick={() => {
          navigator.clipboard?.writeText(value).catch(() => {})
          toast(`${label} copied`)
        }}
      >
        Copy
      </button>
    </div>
  )
}

function lastFrom(events: LearningEvent[] | undefined, source: string) {
  return events?.find((e) => e.source === source)
}

export function IntegrationsPage() {
  const { userId, projectId, token } = useSessionStore()
  const events = useQuery({ queryKey: ['activity', userId, projectId, 'integrations'], queryFn: () => getEvents(userId, projectId ?? undefined, 200), enabled: !!projectId })
  const chrome = lastFrom(events.data, 'browser')
  const vscode = lastFrom(events.data, 'vscode')
  const api = location.origin

  const vscodeSettings = JSON.stringify({ 'spartan.api': api, 'spartan.projectId': projectId, 'spartan.userId': userId, 'spartan.authToken': token, 'spartan.indexOnSave': true }, null, 2)

  return (
    <div className="view view-narrow">
      <div className="page-head page-head-center">
        <div>
          <p className="eyebrow">CONNECT</p>
          <h1>Bring StudyBuddy into Chrome and VS Code.</h1>
          <p>Both extensions write to the same memory as this web app, so progress, hints and resume cards follow you everywhere.</p>
        </div>
      </div>

      <Card>
        <CardTitle title="Your connection details" subtitle="Paste these into each extension" />
        <div style={{ display: 'grid', gap: 10 }}>
          <CopyRow label="Backend URL" value={api} />
          <CopyRow label="Project ID" value={projectId ?? ''} />
          <CopyRow label="User ID" value={userId} />
        </div>
          <CopyRow label="Login token" value={token ?? ''} />
      </Card>

      <div className="grid-2 section">
        <Card>
          <CardTitle
            title="Chrome extension"
            subtitle="Tracks videos, articles and papers you study"
            action={chrome ? <Badge tone="success">Active</Badge> : <Badge tone="neutral">Not seen yet</Badge>}
          />
          <p className="muted" style={{ marginBottom: 12 }}>
            {chrome ? `Last activity ${timeAgo(chrome.created_at)}.` : 'No browser activity from this account yet.'}
          </p>
          <ol style={{ paddingLeft: 18, margin: 0, display: 'grid', gap: 8, fontSize: 14 }}>
            <li>
              Run <code>make extensions-package</code> on the Spark.
            </li>
            <li>
              Unzip <code>dist/extensions/spartan-studybuddy-chrome.zip</code>.
            </li>
            <li>
              Chrome → Extensions → <b>Developer mode</b> → <b>Load unpacked</b>.
            </li>
            <li>Open the extension popup and paste the four values above. Treat the login token like a password.</li>
          </ol>
        </Card>
        <Card>
          <CardTitle
            title="VS Code extension"
            subtitle="Hints, explanations and indexing inside your editor"
            action={vscode ? <Badge tone="success">Active</Badge> : <Badge tone="neutral">Not seen yet</Badge>}
          />
          <p className="muted" style={{ marginBottom: 12 }}>
            {vscode ? `Last activity ${timeAgo(vscode.created_at)}.` : 'No editor activity from this account yet.'}
          </p>
          <p style={{ fontSize: 14, marginBottom: 8 }}>
            Add this to your VS Code <b>settings.json</b>:
          </p>
          <pre className="mono" style={{ fontSize: 12, background: 'var(--surface-alt)', padding: 12, borderRadius: 8, overflow: 'auto', margin: 0 }}>
            {vscodeSettings}
          </pre>
          <button
            className="btn btn-secondary"
            style={{ marginTop: 10 }}
            onClick={() => {
              navigator.clipboard?.writeText(vscodeSettings).catch(() => {})
              toast('VS Code settings copied')
            }}
          >
            Copy settings
          </button>
        </Card>
      </div>

      <p className="muted section" style={{ textAlign: 'center' }}>
        Private code stays on this infrastructure. Extensions talk only to your StudyBuddy backend, never to a third-party AI service.
      </p>
    </div>
  )
}
