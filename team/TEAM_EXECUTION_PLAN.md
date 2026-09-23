# Spartan StudyBuddy — 5-Person Execution Plan

## Goal

Ship a hackathon-ready enterprise onboarding platform that can ingest private engineering knowledge, build role-specific gamified onboarding paths, answer grounded code/document questions, teach Socratically, remember learning across browser + IDE, curate public learning resources with Browser-Use, and prove that a locally fine-tuned 32B teacher plus optimized vLLM serving improves both pedagogical quality and inference performance on DGX Spark.

## Team topology

| Member | Lane | Branch | Primary deliverable |
|---|---|---|---|
| 1 | Model + Inference | `agent/model-inference` | Qwen3-32B fine-tune, merged model, vLLM, speculation, quality/perf report |
| 2 | Backend + RAG + Postgres | `agent/backend-rag` | Source ingestion, pgvector hybrid RAG, memory, routing, API stability |
| 3 | Web Product + Gamification | `agent/web-product` | Beautiful manager/learner UX, roadmaps, teams, leaderboard, resume experience |
| 4 | Browser Intelligence | `agent/browser-agent` | Chrome extension, Browser-Use, YouTube/web/paper telemetry, resource scout |
| 5 | VS Code + Observability + Integration | `agent/vscode-integration` | VS Code extension, Grafana/Prometheus/Tempo, deploy gate, final integration |

## Hard rule: one owner per file family

Do not let five people edit the same core files. Shared contracts are frozen unless the owner publishes a migration note in `team/SHARED_CONTRACTS.md` and all affected members acknowledge it.

### Ownership

**Member 1 owns**
- `training/**`
- `experiments/**`
- `scripts/models/**`
- `scripts/training/**`
- `scripts/competition/**`
- model-related `.env.example` values

**Member 2 owns**
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/services/indexer.py`
- `backend/app/services/retrieval.py`
- `backend/app/services/sources.py`
- `backend/app/services/memory.py`
- `backend/app/services/projects.py`
- `backend/app/agents/assistant.py`
- database schema/migrations under `deploy/postgres/**`

**Member 3 owns**
- `apps/web/**`
- product copy, visual system, interactions
- frontend API adapters only

**Member 4 owns**
- `apps/chrome-extension/**`
- `bridges/mac_bridge.py`
- Browser-Use prompts/tools
- browser resource telemetry

**Member 5 owns**
- `apps/vscode-extension/**`
- `deploy/observability/**`
- `scripts/dgx/**`
- `scripts/observability/**`
- `scripts/extensions/**`
- top-level deployment/validation wiring in `Makefile`

**Root `backend/app/main.py` is integration-owned by Member 5.** Other members request route changes through a small patch or contract note rather than editing it concurrently.

## Frozen service topology

```text
MacBook
├── Web browser / Chrome extension
├── VS Code extension
└── Browser-Use bridge
       │
       │ LAN / Tailscale
       ▼
DGX Spark
├── FastAPI                         :8000
├── PostgreSQL + pgvector           :5432 (localhost)
├── Qwen3-32B / tuned teacher       :8101 (localhost)
├── Qwen3-Embedding-0.6B            :8105 (localhost)
├── Prometheus                      :9090
├── Grafana                         :3001
├── Tempo                           :3200
└── OTLP HTTP                       :4318
```

Public clients call FastAPI. Raw vLLM ports remain localhost-only.

## Four-day schedule

### Day 1 — make the vertical slice undeniable

**By hour 4**
- Member 1: base Qwen3-32B serving + embedding serving healthy.
- Member 2: Postgres/pgvector starts, one local repo indexes, `/api/search` returns cited results.
- Member 3: project dashboard + source panel + assistant shell connected to real API.
- Member 4: Chrome extension connects to a workspace and posts a learning event.
- Member 5: VS Code extension connects to the same workspace; `make test`/extension contracts run.

**By end of Day 1**
Demo one end-to-end flow:
1. connect repo;
2. index repo;
3. ask “what does this function do?”;
4. receive cited answer;
5. ask Socratic hint in VS Code;
6. see both interactions in shared memory/activity.

No team member moves to stretch work until this works.

### Day 2 — product depth + training

- Member 1: prepare final behavior dataset; run smoke tune; begin full LoRA/QLoRA run.
- Member 2: finish GitHub/URL/upload/Drive ingestion, hybrid sparse+dense+RRF retrieval, memory and request routing.
- Member 3: manager invites, role selection, roadmap, XP, leaderboard, resume cards, premium UI motion.
- Member 4: Browser-Use resource scout + YouTube/paper/blog session tracking + resume summaries/questions.
- Member 5: VS Code indexing-on-save, context-aware modes, Prometheus/Grafana/Tempo, one-command deploy.

**Day 2 integration gate:**
`make test && make extensions-test && make models-health`

### Day 3 — prove the hackathon criteria

- Member 1: merge best LoRA, run held-out base vs tuned quality eval, then normal vs n-gram vs Eagle-3 benchmark.
- Member 2: retrieval evaluation on real repo questions; improve citations/grounding and failure handling.
- Member 3: connect Engineering Lab to actual benchmark JSON; final visual polish and responsive layout.
- Member 4: benchmark Browser-Use jobs; ensure no private code is sent to public search.
- Member 5: full stack deployment rehearsal on DGX + Mac, dashboard metrics, extension packages, fault recovery.

**Day 3 freeze:** no new architecture after 8 PM. Only bugs, performance, copy, and demo flow.

### Day 4 — final reliability + pitch

Morning:
- clean deployment from ZIP on DGX;
- install extensions from packaged artifacts;
- index one fresh demonstration repo;
- run `make competition` or load frozen results;
- verify Grafana metrics and activity traces.

Afternoon:
- 3 complete demo rehearsals;
- unplug/reconnect network test;
- restart model/backend/db test;
- backup demo database and model result artifacts;
- freeze exact presentation numbers.

Final 90 minutes: no code except demo-blocking fixes.

## Required demo story

1. **Manager connects private repository** and chooses “ML Engineer — Junior.”
2. StudyBuddy maps repository concepts and creates a role-specific onboarding roadmap.
3. Browser agent curates sanitized public resources for prerequisites.
4. Learner opens a YouTube/resource, leaves part-way, then returns to a summary + recall question.
5. Learner asks a direct repo question and receives a grounded answer with file/line citations.
6. In VS Code, learner asks for help on an exercise and gets progressive Socratic guidance instead of a paste-ready solution.
7. Manager dashboard shows progress, XP, leaderboard, knowledge gaps.
8. Engineering Lab shows **real** base vs tuned quality and vLLM TTFT/TPS/speculation measurements.
9. Grafana shows live local inference telemetry.

## Definition of hackathon done

All of the following must be true:

- `make doctor` succeeds on DGX Spark.
- `make test` passes against live PostgreSQL/pgvector.
- `make extensions-test` passes.
- `make models-health` passes.
- one repository can be ingested without manual DB edits.
- direct Q&A cites indexed evidence.
- Socratic mode avoids final answers by default.
- roadmap/resource scout creates usable public resources.
- resource progress and resume summary survive restart.
- Chrome and VS Code use the same user/project memory.
- `make competition` produces quality + benchmark artifacts, or frozen artifacts are present from a completed run.
- Grafana shows request latency/model metrics.
- no private repository content is sent to public Browser-Use queries.
- a clean demo can be run from a new browser session without modifying source code.

## Merge protocol

1. Every member rebases on `main` twice per day: noon and 8 PM.
2. Never merge a branch with failing lane tests.
3. Shared API changes require a `SHARED_CONTRACTS.md` update first.
4. Member 5 is release integrator and merges in this order:
   1. Member 2 backend contracts
   2. Member 1 model/runtime
   3. Member 4 browser
   4. Member 3 web
   5. Member 5 VS Code/observability/deploy
5. Tag stable checkpoints: `demo-day1`, `demo-day2`, `demo-freeze`.

## Daily standup format — 5 minutes total

Each person says only:
- **Working:** what is green right now.
- **Blocking:** exact dependency/API needed.
- **Next gate:** command/demo that will be green by the next standup.

No long status presentations.
