import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCompetition, getHealth, getTraces } from '../api/endpoints'
import { Badge } from '../components/primitives/Badge'
import { Button } from '../components/primitives/Button'
import { Card, CardTitle, StatCard } from '../components/primitives/Card'
import { Skeleton } from '../components/primitives/Feedback'
import { Drawer, KeyValue, NeedsBackend, Section, timeAgo } from '../components/primitives/Layout'
import type { AgentTrace, CompetitionSummary } from '../api/types'

const NOT_MEASURED = <span className="muted">Not measured yet</span>

function num(v: number | null | undefined, digits = 2, suffix = '') {
  return v == null ? NOT_MEASURED : `${Number(v).toFixed(digits)}${suffix}`
}
function rate(v: number | null | undefined) {
  return v == null ? NOT_MEASURED : `${(Number(v) * 100).toFixed(1)}%`
}
function change(v: number | null | undefined, higherIsBetter: boolean) {
  if (v == null) return NOT_MEASURED
  const good = higherIsBetter ? v > 0 : v < 0
  return <b style={{ color: good ? 'var(--success-ink)' : 'var(--danger-ink)' }}>{`${v > 0 ? '+' : ''}${Number(v).toFixed(1)}%`}</b>
}
function percentile(sorted: number[], p: number) {
  if (!sorted.length) return null
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))]
}

export function EngineeringLabPage() {
  const [trace, setTrace] = useState<AgentTrace | null>(null)
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 20000 })
  const competition = useQuery({ queryKey: ['competition'], queryFn: getCompetition })
  const traces = useQuery({ queryKey: ['traces'], queryFn: () => getTraces(200), refetchInterval: 15000 })

  const s: CompetitionSummary = competition.data?.summary ?? competition.data ?? {}
  const measured = competition.data?.available !== false && !!(s.socratic_quality || s.speculative_decoding || s.serving_base_vs_tuned)
  const q = s.socratic_quality
  const sv = s.serving_base_vs_tuned
  const sp = s.speculative_decoding

  const agg = useMemo(() => {
    const rows = traces.data || []
    const lat = rows.map((t) => t.latency_ms).filter((v): v is number => v != null).sort((a, b) => a - b)
    const ttft = rows.map((t) => t.ttft_ms).filter((v): v is number => v != null).sort((a, b) => a - b)
    const ok = rows.filter((t) => t.success === 1 || t.success === true).length
    return {
      count: rows.length,
      successRate: rows.length ? ok / rows.length : null,
      p50: percentile(lat, 50),
      p95: percentile(lat, 95),
      ttftP50: percentile(ttft, 50),
      tokensIn: rows.reduce((a, t) => a + (t.input_tokens || 0), 0),
      tokensOut: rows.reduce((a, t) => a + (t.output_tokens || 0), 0),
      routes: Array.from(new Set(rows.map((t) => t.route).filter(Boolean))) as string[],
    }
  }, [traces.data])

  const grafana = `${location.protocol}//${location.hostname}:3001`

  return (
    <div className="view">
      <div className="page-head">
        <div>
          <p className="eyebrow">ENGINEERING LAB</p>
          <h1>Prove the model. Prove the system.</h1>
          <p>Fine-tuning quality, serving speed and agent traces, measured on the DGX Spark. A value that hasn't been measured says so — nothing is estimated.</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <a className="btn btn-secondary" href={grafana} target="_blank" rel="noopener noreferrer">
            Grafana ↗
          </a>
          <a className="btn btn-secondary" href="/metrics" target="_blank" rel="noopener noreferrer">
            Prometheus ↗
          </a>
        </div>
      </div>

      <Section eyebrow="SERVICE HEALTH" action={<Button onClick={() => health.refetch()} pending={health.isFetching}>Refresh</Button>}>
        {health.isLoading ? (
          <Skeleton height={80} />
        ) : (
          <div className="grid-4" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
            <div className="card-flat">
              <span className="muted">PostgreSQL + pgvector</span>
              <div style={{ marginTop: 8 }}>
                <Badge tone={health.data?.ok ? 'success' : 'danger'}>{health.data?.ok ? 'Healthy' : 'Down'}</Badge>
              </div>
            </div>
            {Object.entries(health.data?.model_endpoints || {}).map(([name, ok]) => (
              <div key={name} className="card-flat">
                <span className="muted" style={{ textTransform: 'capitalize' }}>
                  {name} model
                </span>
                <div style={{ marginTop: 8 }}>
                  <Badge tone={ok ? 'success' : 'warning'}>{ok ? 'Online' : 'Offline'}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {!measured && !competition.isLoading && (
        <div className="card-flat section">
          <b>No competition results yet.</b>
          <p className="muted" style={{ margin: '6px 0 10px' }}>
            {competition.data?.message || 'Run the full pipeline on the DGX Spark to fill the tables below.'}
          </p>
          <code style={{ background: 'var(--surface-alt)', padding: '8px 12px', borderRadius: 8, display: 'inline-block' }}>make competition</code>
        </div>
      )}

      <div className="split section">
        <Card>
          <CardTitle title="Tutor quality: base vs fine-tuned" subtitle="Held-out evaluation set, never used in training" />
          <table className="table">
            <caption>Spec §13 evaluation metrics</caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Base</th>
                <th scope="col">Tuned</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Socratic behavior score</td>
                <td>{num(q?.base_score, 1)}</td>
                <td>
                  <b>{num(q?.tuned_score, 1)}</b>
                </td>
              </tr>
              <tr>
                <td>Answer leakage in Socratic mode (lower is better)</td>
                <td>{rate(q?.base_answer_leak_rate)}</td>
                <td>
                  <b>{rate(q?.tuned_answer_leak_rate)}</b>
                </td>
              </tr>
              <tr>
                <td>Probing-question rate</td>
                <td>{rate(q?.base_question_rate)}</td>
                <td>
                  <b>{rate(q?.tuned_question_rate)}</b>
                </td>
              </tr>
              {['Correct direct answers in Direct mode', 'Hint quality', 'Groundedness', 'Code-teaching quality', 'Concision'].map((m) => (
                <tr key={m}>
                  <td>{m}</td>
                  <td>{NOT_MEASURED}</td>
                  <td>{NOT_MEASURED}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {q?.score_delta_points != null && (
            <p style={{ marginTop: 12 }}>
              Fine-tuning changed the Socratic score by <b>{q.score_delta_points > 0 ? '+' : ''}{q.score_delta_points.toFixed(1)} points</b>.
            </p>
          )}
        </Card>

        <Card>
          <CardTitle title="Serving speed: base vs tuned" subtitle="p50 over the benchmark workload" />
          <table className="table">
            <caption>vLLM serving benchmark</caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Base</th>
                <th scope="col">Tuned</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Time to first token</td>
                <td>{num(sv?.base_ttft_p50_s, 2, ' s')}</td>
                <td>{num(sv?.tuned_ttft_p50_s, 2, ' s')}</td>
              </tr>
              <tr>
                <td>Decode speed</td>
                <td>{num(sv?.base_decode_tok_s_p50, 1, ' tok/s')}</td>
                <td>{num(sv?.tuned_decode_tok_s_p50, 1, ' tok/s')}</td>
              </tr>
              <tr>
                <td>Aggregate throughput</td>
                <td>{num(sv?.base_aggregate_tok_s, 1, ' tok/s')}</td>
                <td>{num(sv?.tuned_aggregate_tok_s, 1, ' tok/s')}</td>
              </tr>
            </tbody>
          </table>
        </Card>
      </div>

      <Card style={{ marginTop: 14 }}>
        <CardTitle title="Speculative decoding" subtitle="Speculation is only chosen if it measurably wins on the Spark" />
        <table className="table">
          <caption>Standard decoding vs speculative methods</caption>
          <thead>
            <tr>
              <th scope="col">Method</th>
              <th scope="col">TTFT p50</th>
              <th scope="col">Decode tok/s p50</th>
              <th scope="col">TTFT change</th>
              <th scope="col">Decode change</th>
              <th scope="col">Aggregate change</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <b>Standard</b> <span className="muted">{sp?.baseline_profile ?? ''}</span>
              </td>
              <td>{num(sp?.baseline_ttft_p50_s, 2, ' s')}</td>
              <td>{num(sp?.baseline_decode_tok_s_p50, 1)}</td>
              <td className="muted">baseline</td>
              <td className="muted">baseline</td>
              <td className="muted">baseline</td>
            </tr>
            <tr>
              <td>
                <b>Speculative</b> <span className="muted">{sp?.spec_profile ?? '(n-gram or Eagle-3)'}</span>
              </td>
              <td>{num(sp?.spec_ttft_p50_s, 2, ' s')}</td>
              <td>{num(sp?.spec_decode_tok_s_p50, 1)}</td>
              <td>{change(sp?.ttft_change_pct, false)}</td>
              <td>{change(sp?.decode_tok_s_change_pct, true)}</td>
              <td>{change(sp?.aggregate_tok_s_change_pct, true)}</td>
            </tr>
          </tbody>
        </table>
        <div className="grid-2" style={{ marginTop: 14 }}>
          <NeedsBackend endpoint="GET /api/admin/serving-profile">The selected profile from recommended_serving.env, with n-gram and Eagle-3 compared side by side and draft acceptance rates.</NeedsBackend>
          <NeedsBackend endpoint="GET /api/admin/competition">Currently reads experiments/results/comparison.json, but the pipeline writes summary.json — results won't show until one side is aligned.</NeedsBackend>
        </div>
      </Card>

      <Section eyebrow="LIVE TRAFFIC" title="Requests through the model router">
        {traces.isLoading ? (
          <Skeleton height={100} />
        ) : (
          <div className="grid-4">
            <StatCard label={`Requests (last ${agg.count})`} value={String(agg.count)} />
            <StatCard label="Success rate" value={agg.successRate == null ? '—' : `${(agg.successRate * 100).toFixed(0)}%`} />
            <StatCard label="Latency p50 / p95" value={agg.p50 == null ? '—' : `${(agg.p50 / 1000).toFixed(1)}s / ${((agg.p95 ?? 0) / 1000).toFixed(1)}s`} />
            <StatCard label="Tokens in / out" value={`${agg.tokensIn} / ${agg.tokensOut}`} />
          </div>
        )}
        <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          Calculated from the most recent traces in the local store. Full Prometheus time series are in Grafana.
        </p>
      </Section>

      <Card style={{ marginTop: 14 }}>
        <CardTitle title="Agent traces" subtitle="Prompts and responses are truncated previews" />
        {(traces.data?.length ?? 0) === 0 ? (
          <p className="muted">No traces yet — ask StudyBuddy a question to create one.</p>
        ) : (
          <table className="table">
            <caption>Most recent first</caption>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Agent</th>
                <th scope="col">Route</th>
                <th scope="col">Latency</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {traces.data!.slice(0, 40).map((t, i) => (
                <tr key={t.id ?? i}>
                  <td className="muted">{timeAgo(t.created_at)}</td>
                  <td>
                    <button className="btn-ghost" style={{ border: 0, background: 'none', padding: 0, fontWeight: 700, color: 'var(--primary)', cursor: 'pointer' }} onClick={() => setTrace(t)}>
                      {t.agent}
                    </button>
                  </td>
                  <td>{t.route || '—'}</td>
                  <td>{t.latency_ms != null ? `${(t.latency_ms / 1000).toFixed(2)}s` : '—'}</td>
                  <td>
                    <Badge tone={t.success === 1 || t.success === true ? 'success' : 'danger'}>{t.success === 1 || t.success === true ? 'OK' : 'Failed'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Drawer open={!!trace} onClose={() => setTrace(null)} title={trace?.agent ?? ''}>
        {trace && (
          <div style={{ display: 'grid', gap: 18 }}>
            <KeyValue
              rows={[
                ['When', trace.created_at ? new Date(trace.created_at).toLocaleString() : '—'],
                ['Result', trace.success === 1 || trace.success === true ? 'Success' : 'Failed'],
                ['Route', trace.route],
                ['Model', <span key="m" className="mono">{trace.model}</span>],
                ['User', <span key="u" className="mono">{trace.user_id}</span>],
                ['Latency', trace.latency_ms != null ? `${(trace.latency_ms / 1000).toFixed(2)} s` : null],
                ['First token', trace.ttft_ms != null ? `${(trace.ttft_ms / 1000).toFixed(2)} s` : null],
                ['Tokens in / out', `${trace.input_tokens ?? '—'} / ${trace.output_tokens ?? '—'}`],
                ['Speed', trace.tokens_per_second != null ? `${trace.tokens_per_second.toFixed(1)} tok/s` : null],
              ]}
            />
            <div>
              <p className="eyebrow">RETRIEVED EVIDENCE ({trace.retrieved?.length ?? 0})</p>
              {(trace.retrieved?.length ?? 0) === 0 ? (
                <p className="muted">None.</p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {trace.retrieved!.map((r, i) => (
                    <span key={i} className="citation-chip">
                      {r.citation || r.source}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="eyebrow">PROMPT PREVIEW</p>
              <pre className="mono" style={{ fontSize: 12, whiteSpace: 'pre-wrap', background: 'var(--surface-alt)', padding: 12, borderRadius: 8, margin: 0 }}>
                {trace.prompt_preview || '—'}
              </pre>
            </div>
            <div>
              <p className="eyebrow">RESPONSE PREVIEW</p>
              <pre className="mono" style={{ fontSize: 12, whiteSpace: 'pre-wrap', background: 'var(--surface-alt)', padding: 12, borderRadius: 8, margin: 0 }}>
                {trace.response_preview || '—'}
              </pre>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}
