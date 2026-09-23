# Shared Contracts — Do Not Drift Without Coordination

## Identity defaults for hackathon

- demo org: `demo-company`
- demo user: `demo-spartan`
- API: `http://<DGX-IP>:8000`
- Web app: same FastAPI origin

## Core API contracts

### Projects
- `GET /api/projects?org_id=...`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/map`

### Knowledge ingestion
- `POST /api/sources/ingest`
  - `{project_id, uri, kind:auto|github|web|gdrive, branch?, access_token?}`
- `POST /api/sources/upload` multipart: `project_id`, `file`
- `POST /api/index/text`
- `GET /api/projects/{project_id}/documents`
- `POST /api/search` → `{results:[...]}`

Every search result consumed by a UI should preserve, when present:
- `document_id`
- `source_name`
- `source_uri`
- `path/file`
- `line_start`
- `line_end`
- retrieval score

### Unified assistant
`POST /api/ask`

```json
{
  "user_id": "demo-spartan",
  "project_id": "...",
  "question": "...",
  "mode": "auto|qa|socratic|explain|code|research",
  "current_code": "optional",
  "file_path": "optional",
  "hint_level": 1,
  "allow_final_answer": false
}
```

Behavior contract:
- `qa`: direct grounded answer.
- `socratic`: guided questions/hints; final answer off by default.
- `explain`: simple first-principles explanation.
- `code`: repository/current-editor-aware reasoning.
- `research`: public research flow.
- `auto`: backend decides.

### Onboarding/gamification
- `POST /api/onboarding`
- `GET /api/onboarding/{project_id}`
- `GET /api/onboarding/path/{path_id}`
- `POST /api/onboarding/path/{path_id}/join`
- `POST /api/onboarding/path/{path_id}/progress`

Roadmap progress updates are the source of truth for XP/leaderboard behavior. Clients must not invent leaderboard scores.

### Learning memory
- `POST /api/events`
- `GET /api/events/{user_id}`
- `GET /api/learner/{user_id}/{project_id}`
- `POST /api/resource/session`
- `GET /api/resource/resume/{user_id}`
- websocket `/ws/{user_id}`

### Browser agent jobs
- `POST /api/agent/jobs`
- `GET /api/agent/jobs`
- `POST /api/agent/jobs/claim`
- `GET /api/agent/jobs/{job_id}`
- `POST /api/agent/jobs/{job_id}/complete`

Supported job kinds:
- `resource_scout`
- `web_research`
- `open_resource`

Browser-Use must never be handed proprietary code snippets. It receives generic/sanitized topics and goals.

## Model contracts

### Teacher
- internal URL: `http://127.0.0.1:8101/v1`
- public served model name: `spartan-teacher`
- base before fine-tuning: `Qwen/Qwen3-32B`
- tuned after merge: `artifacts/socratic-merged/`

### Embeddings
- internal URL: `http://127.0.0.1:8105/v1`
- model: `Qwen/Qwen3-Embedding-0.6B`
- dimension: `1024`
- production fallback embeddings: disabled

### Browser-Use model proxy
- endpoint exposed by FastAPI: `/agent-llm/v1`
- auth: `Authorization: Bearer $STUDYBUDDY_BRIDGE_TOKEN`
- default provider reuses `spartan-teacher`

## Database contract

PostgreSQL 16 + pgvector only.

`indexed_chunks.embedding` must be `vector(1024)` and use the same embedding model for both ingestion and query.

Retrieval pipeline:
1. PostgreSQL FTS / GIN sparse candidates.
2. pgvector cosine / HNSW dense candidates.
3. reciprocal-rank fusion.
4. optional local teacher rerank.
5. context assembled with source/path/line metadata.

## Observability contract

Every important model/agent request should be able to produce:
- route/mode
- model
- start/end timestamps
- TTFT when streaming is measurable
- generated tokens
- decode tokens/sec
- total latency
- retrieval evidence IDs
- success/error

No fabricated values in UI or poster. Demo values must come from experiment artifacts or live metrics.
