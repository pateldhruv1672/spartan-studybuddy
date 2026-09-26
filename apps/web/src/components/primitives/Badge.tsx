type Tone = 'success' | 'warning' | 'danger' | 'info' | 'coral' | 'neutral'

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: React.ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function statusTone(status: string): Tone {
  const s = status.toLowerCase()
  if (['indexed', 'completed', 'ready', 'online', 'active', 'success'].includes(s)) return 'success'
  if (['indexing', 'pending', 'in_progress', 'queued', 'running', 'warming'].includes(s)) return 'warning'
  if (['failed', 'error', 'offline'].includes(s)) return 'danger'
  return 'neutral'
}
