import { Card, CardTitle } from '../components/primitives/Card'
import { Section } from '../components/primitives/Layout'

type IconKind = 'browser' | 'script' | 'worker' | 'server' | 'index' | 'search' | 'graph' | 'curriculum' | 'gpu' | 'db' | 'shield' | 'path' | 'robot' | 'chrome' | 'globe'

/** Small self-contained glyphs -- native SVG shapes only, no images, so the diagram stays a single
 * inline fragment and themes correctly via currentColor (see artifact-diagramming skill). */
function Icon({ kind, x, y, size = 15 }: { kind: IconKind; x: number; y: number; size?: number }) {
  const s = size
  const c = { stroke: 'currentColor', strokeWidth: 1.2, fill: 'none' } as const
  const dot = (cx: number, cy: number, r = 1.3) => <circle cx={cx} cy={cy} r={r} fill="currentColor" stroke="none" />
  return (
    <g transform={`translate(${x},${y})`} opacity={0.8}>
      {kind === 'browser' && (
        <>
          <rect x={0} y={0} width={s} height={s} rx={2} {...c} />
          <line x1={0} y1={s * 0.3} x2={s} y2={s * 0.3} {...c} />
          {dot(s * 0.22, s * 0.15, 0.9)}
        </>
      )}
      {kind === 'script' && (
        <>
          <rect x={1.5} y={0} width={s - 5} height={s} rx={1.5} {...c} />
          <line x1={3.5} y1={s * 0.3} x2={s - 5.5} y2={s * 0.3} {...c} />
          <line x1={3.5} y1={s * 0.55} x2={s - 5.5} y2={s * 0.55} {...c} />
          <line x1={3.5} y1={s * 0.8} x2={s - 8} y2={s * 0.8} {...c} />
        </>
      )}
      {kind === 'worker' && (
        <>
          <rect x={0} y={2} width={s} height={s - 6} rx={2} {...c} />
          {dot(s * 0.3, s * 0.5)}
          {dot(s * 0.7, s * 0.5)}
        </>
      )}
      {kind === 'server' && (
        <>
          <rect x={0} y={0} width={s} height={s * 0.42} rx={1.5} {...c} />
          <rect x={0} y={s * 0.56} width={s} height={s * 0.42} rx={1.5} {...c} />
          {dot(s * 0.2, s * 0.21, 0.9)}
          {dot(s * 0.2, s * 0.77, 0.9)}
        </>
      )}
      {kind === 'index' && (
        <>
          <rect x={0} y={0} width={s} height={s} rx={2} {...c} />
          <line x1={3} y1={4} x2={s - 3} y2={4} {...c} strokeWidth={1} />
          <line x1={3} y1={7.5} x2={s - 3} y2={7.5} {...c} strokeWidth={1} />
          <line x1={3} y1={11} x2={s - 6} y2={11} {...c} strokeWidth={1} />
        </>
      )}
      {kind === 'search' && (
        <>
          <circle cx={s * 0.42} cy={s * 0.42} r={s * 0.32} {...c} />
          <line x1={s * 0.66} y1={s * 0.66} x2={s * 0.95} y2={s * 0.95} {...c} />
        </>
      )}
      {kind === 'graph' && (
        <>
          {dot(2, 2)}
          {dot(s - 2, 4)}
          {dot(s / 2, s - 2)}
          <line x1={2} y1={2} x2={s - 2} y2={4} {...c} strokeWidth={1} />
          <line x1={2} y1={2} x2={s / 2} y2={s - 2} {...c} strokeWidth={1} />
          <line x1={s - 2} y1={4} x2={s / 2} y2={s - 2} {...c} strokeWidth={1} />
        </>
      )}
      {kind === 'curriculum' && (
        <>
          <rect x={0} y={1.5} width={s - 3} height={s - 3} rx={1.5} {...c} />
          <rect x={3} y={4.5} width={s - 3} height={s - 3} rx={1.5} fill="var(--surface,#fdfbf7)" stroke="currentColor" strokeWidth={1.2} />
        </>
      )}
      {kind === 'gpu' && (
        <>
          <rect x={2} y={2} width={s - 4} height={s - 4} rx={1.5} {...c} />
          {[3.5, 7, 10.5].map((p) => (
            <line key={`t${p}`} x1={p} y1={0} x2={p} y2={2} {...c} strokeWidth={1} />
          ))}
          {[3.5, 7, 10.5].map((p) => (
            <line key={`b${p}`} x1={p} y1={s - 2} x2={p} y2={s} {...c} strokeWidth={1} />
          ))}
        </>
      )}
      {kind === 'db' && (
        <>
          <ellipse cx={s / 2} cy={2.3} rx={s / 2 - 1} ry={1.9} {...c} />
          <path d={`M1,2.3 L1,${s - 2.3} A${s / 2 - 1},1.9 0 0 0 ${s - 1},${s - 2.3} L${s - 1},2.3`} {...c} />
        </>
      )}
      {kind === 'shield' && <path d={`M${s / 2},0 L${s - 1},3 V${s * 0.55} Q${s - 1},${s - 1} ${s / 2},${s} Q1,${s - 1} 1,${s * 0.55} V3 Z`} {...c} />}
      {kind === 'path' && (
        <>
          {dot(2, s - 2)}
          {dot(s - 2, 2)}
          <path d={`M2,${s - 2} Q${s / 2},${s - 2} ${s - 2},2`} {...c} />
        </>
      )}
      {kind === 'robot' && (
        <>
          <rect x={1} y={3.5} width={s - 2} height={s - 5.5} rx={2} {...c} />
          {dot(s * 0.32, s * 0.6, 1.1)}
          {dot(s * 0.68, s * 0.6, 1.1)}
          <line x1={s / 2} y1={3.5} x2={s / 2} y2={1} {...c} strokeWidth={1} />
          {dot(s / 2, 0.6, 0.8)}
        </>
      )}
      {kind === 'chrome' && (
        <>
          <circle cx={s / 2} cy={s / 2} r={s / 2 - 1} {...c} />
          <circle cx={s / 2} cy={s / 2} r={s * 0.22} {...c} />
          <line x1={s / 2} y1={1} x2={s / 2} y2={s * 0.28} {...c} strokeWidth={1} />
          <line x1={s / 2} y1={s * 0.72} x2={s / 2} y2={s - 1} {...c} strokeWidth={1} />
        </>
      )}
      {kind === 'globe' && (
        <>
          <circle cx={s / 2} cy={s / 2} r={s / 2 - 1} {...c} />
          <ellipse cx={s / 2} cy={s / 2} rx={s * 0.22} ry={s / 2 - 1} {...c} />
          <line x1={1} y1={s / 2} x2={s - 1} y2={s / 2} {...c} strokeWidth={1} />
        </>
      )}
    </g>
  )
}

function Boundary({ x, y, w, h, label, icon, accent }: { x: number; y: number; w: number; h: number; label: string; icon: IconKind; accent?: boolean }) {
  const color = accent ? '#c8632f' : 'currentColor'
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={16} fill="none" stroke={color} strokeOpacity={accent ? 0.9 : 0.35} strokeWidth={accent ? 2 : 1.5} strokeDasharray="6 5" />
      <g style={{ color }}>
        <Icon kind={icon} x={x + 14} y={y - 21} size={13} />
      </g>
      <text x={x + 34} y={y - 10} fontSize={12.5} fontWeight={700} letterSpacing={0.4} fill={color} opacity={accent ? 1 : 0.6} style={{ textTransform: 'uppercase' }}>
        {label}
      </text>
    </g>
  )
}

function Box({ x, y, w, h, title, lines, icon, fill }: { x: number; y: number; w: number; h: number; title: string; lines?: string[]; icon: IconKind; fill?: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill={fill || 'currentColor'} fillOpacity={fill ? 1 : 0.06} stroke="currentColor" strokeOpacity={0.5} strokeWidth={1.25} />
      <Icon kind={icon} x={x + 10} y={y + 9} />
      <text x={x + w / 2 + 8} y={y + (lines?.length ? 22 : h / 2 + 5)} textAnchor="middle" fontSize={13} fontWeight={700} fill="currentColor">
        {title}
      </text>
      {(lines || []).map((l, i) => (
        <text key={i} x={x + w / 2} y={y + 40 + i * 15} textAnchor="middle" fontSize={10.5} fill="currentColor" opacity={0.7}>
          {l}
        </text>
      ))}
    </g>
  )
}

function Arrow({ x1, y1, x2, y2, label, dashed, curve }: { x1: number; y1: number; x2: number; y2: number; label?: string; dashed?: boolean; curve?: boolean }) {
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  const path = curve ? `M${x1},${y1} Q${mx},${y1} ${x2},${y2}` : `M${x1},${y1} L${x2},${y2}`
  return (
    <g>
      <path d={path} fill="none" stroke="currentColor" strokeOpacity={0.55} strokeWidth={1.5} strokeDasharray={dashed ? '4 4' : undefined} markerEnd="url(#arrow)" />
      {label && (
        <text x={curve ? mx : mx} y={(curve ? y1 : my) - 6} textAnchor="middle" fontSize={10} fill="currentColor" opacity={0.8}>
          {label}
        </text>
      )}
    </g>
  )
}

export function ArchitecturePage() {
  return (
    <div className="view">
      <Section eyebrow="SYSTEM DESIGN" title="Architecture">
        <p className="muted" style={{ maxWidth: 760 }}>
          The mechanism, not just the components: where a request actually goes, which hop is a poll versus a push, and why browser
          automation runs on the learner's own Mac instead of the GPU box. Every arrow below is a real call in the code, not a decoration.
        </p>
      </Section>

      <Card>
        <CardTitle title="Component &amp; data-flow diagram" subtitle="Presentation-ready — screen-share this page directly" />
        <figure style={{ margin: 0, width: '100%', overflowX: 'auto' }}>
          <svg viewBox="0 0 1420 720" style={{ width: '100%', minWidth: 980, height: 'auto', color: 'var(--ink, #26231d)' }} role="img" aria-label="Spartan StudyBuddy architecture: the learner's browser and the Mac bridge both talk to the ZGX Nano's FastAPI backend, which owns auth, the job queue, the knowledge pipeline, Postgres+pgvector and the local vLLM model stack; the Mac bridge polls for jobs, drives Chrome over CDP to scout the public web, and routes its own LLM calls back through the backend's proxy so all inference stays on the ZGX Nano.">
            <defs>
              <marker id="arrow" markerWidth="9" markerHeight="8" refX="8" refY="4" orient="auto">
                <polygon points="0 0, 9 4, 0 8" fill="currentColor" fillOpacity={0.6} />
              </marker>
            </defs>

            {/* Boundaries */}
            <Boundary x={20} y={40} w={300} h={260} label="Learner's browser" icon="browser" />
            <Boundary x={360} y={40} w={660} h={640} label="ZGX Nano — GPU box" icon="gpu" />
            <Boundary x={1060} y={40} w={340} h={300} label="Mac — remote, over Tailscale" icon="robot" accent />
            <Boundary x={1060} y={400} w={340} h={120} label="Public internet" icon="globe" />

            {/* Learner's browser */}
            <Box x={40} y={70} w={260} h={60} title="Web App" lines={['React + Vite SPA']} icon="browser" />
            <Box x={40} y={160} w={110} h={60} title="Content script" lines={['reads DOM, tracks', 'progress on any page']} icon="script" />
            <Box x={190} y={160} w={110} h={60} title="Service worker" lines={['MV3 background', '+ alarms keepalive']} icon="worker" />
            <Arrow x1={150} y1={190} x2={190} y2={190} label="runtime.sendMessage" />
            <Arrow x1={170} y1={130} x2={170} y2={160} />

            {/* ZGX Nano internals */}
            <Box
              x={380}
              y={70}
              w={620}
              h={90}
              title="FastAPI Backend"
              lines={['REST API · WebSocket hub (job / session push)', 'JWT auth (HMAC, persisted secret) · Job queue']}
              icon="server"
            />
            <Box x={380} y={190} w={140} h={60} title="Indexer" lines={['chunks + embeds', 'the repo']} icon="index" />
            <Box x={540} y={190} w={140} h={60} title="Hybrid retrieval" lines={['lexical + vector', 'rerank']} icon="search" />
            <Box x={700} y={190} w={140} h={60} title="Knowledge graph" lines={['concepts, files,', 'symbols, edges']} icon="graph" />
            <Box x={860} y={190} w={140} h={60} title="Curriculum builder" lines={['modules, quizzes,', 'topic → concept map']} icon="curriculum" />
            <Arrow x1={520} y1={220} x2={540} y2={220} />
            <Arrow x1={680} y1={220} x2={700} y2={220} />
            <Arrow x1={840} y1={220} x2={860} y2={220} />

            <Box x={380} y={290} w={200} h={70} title="studybuddy-mtp" lines={['27B — reasoning /', 'Socratic teacher']} icon="gpu" />
            <Box x={600} y={290} w={200} h={70} title="studybuddy-light8b" lines={['8B — fast scout', '/agent-llm proxy target']} icon="gpu" />
            <Box x={820} y={290} w={180} h={70} title="embeddings" lines={['Qwen3-Embedding', 'pgvector writes']} icon="gpu" />

            <Box x={380} y={400} w={620} h={70} title="PostgreSQL + pgvector" lines={['users · paths · path_resources (+ screenshots) · events · vectors']} icon="db" />

            <Box x={380} y={510} w={300} h={70} title="Resource validation" lines={['topic membership · lexical match', 'real-YouTube-ID shape check']} icon="shield" />
            <Box x={700} y={510} w={300} h={70} title="Onboarding paths" lines={['graph engine (indexed repo) or', 'LLM engine (no repo) → modules']} icon="path" />

            {/* Mac */}
            <Box x={1080} y={70} w={300} h={80} title="Mac Bridge" lines={['browser-use agent per topic', 'search + click only — no typed URLs']} icon="robot" />
            <Box x={1080} y={180} w={300} h={70} title="Chrome (headless)" lines={['driven over CDP, one tab', 'per concurrent scout (max 3)']} icon="chrome" />
            <text x={1080} y={280} fontSize={10.5} fill="currentColor" opacity={0.65}>
              loop: poll → claim job → run scout(s) → capture screenshot + real duration → report
            </text>

            {/* Public internet */}
            <Box x={1080} y={430} w={300} h={70} title="Public web" lines={['YouTube · docs · blogs', 'oEmbed / HTTP verified before storing']} icon="globe" />

            {/* Cross-boundary arrows */}
            <Arrow x1={170} y1={70} x2={520} y2={160} label="HTTPS + JWT" curve />
            <Arrow x1={245} y1={190} x2={380} y2={130} label="REST: events, resource/session" curve />
            <Arrow x1={380} y1={110} x2={245} y2={190} label="WebSocket: job / session push" dashed curve />

            <Arrow x1={1000} y1={115} x2={1080} y2={100} label="claim / complete job — HTTP poll, 2s" />
            <Arrow x1={1080} y1={130} x2={1000} y2={140} label="/agent-llm proxy — chat completions" dashed />
            <Arrow x1={1230} y1={150} x2={1230} y2={180} label="CDP :9222" />
            <Arrow x1={1230} y1={250} x2={1230} y2={430} label="search + click" dashed />

            <Arrow x1={690} y1={160} x2={690} y2={190} />
            <Arrow x1={690} y1={250} x2={690} y2={290} label="module topics" />
            <Arrow x1={690} y1={360} x2={690} y2={400} label="embeddings, graph nodes" />
            <Arrow x1={530} y1={470} x2={530} y2={510} />
            <Arrow x1={680} y1={545} x2={700} y2={545} label="accepted resources" />
            <Arrow x1={850} y1={580} x2={850} y2={620} />
            <Arrow x1={850} y1={620} x2={690} y2={70} label="curriculum + resources" dashed curve />
          </svg>
          <figcaption className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            The learner's browser and the Mac both talk only to the ZGX Nano's backend — never to each other or to the model stack
            directly. The Mac bridge polls rather than being pushed to (it has no public inbound port), and every one of its own LLM
            calls is routed back through the backend's <code>/agent-llm</code> proxy so all inference stays on the ZGX Nano's GPU.
          </figcaption>
        </figure>
      </Card>

      <Card>
        <CardTitle title="Key flows" />
        <div className="row-list">
          <div className="card-flat">
            <b>Onboarding path generation</b>
            <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              Manager picks a role → the graph engine (if the repo is indexed) or the LLM engine builds a curriculum → topics are
              sanitized and dispatched as a <code>resource_scout</code> job on the queue.
            </p>
          </div>
          <div className="card-flat">
            <b>Resource scouting</b>
            <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              The Mac bridge claims the job and runs one small browser-use agent per topic — search and click only, never a free-typed
              URL — up to 3 concurrently, spaced to avoid colliding on Chrome's single CDP connection. Each result is validated
              (topic match, real YouTube ID shape, live URL check) before it's stored with a real screenshot and captured video
              duration.
            </p>
          </div>
          <div className="card-flat">
            <b>Learning &amp; memory</b>
            <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              The Chrome extension's content script tracks reading/watch progress on any resource the learner opens and syncs it
              through the service worker to the same resource-session store the dashboard's resume feed reads from — one shared
              memory, not separate silos per surface.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}
