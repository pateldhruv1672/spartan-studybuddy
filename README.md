# Spartan StudyBuddy for Teams

**Private codebase → structured onboarding academy → locally fine-tuned Socratic engineering tutor.**

Spartan StudyBuddy turns a company's private repositories, documents, URLs, and shared knowledge into role-specific onboarding paths. New hires learn through direct grounded Q&A, simple explanations, Socratic guidance, curated public resources, repository-specific exercises, progress tracking, XP, and team leaderboards. Private source code, indexed knowledge, learner memory, model inference, and local traces live on the DGX Spark.

## What is in this repository

- Apple-inspired web control center served by FastAPI.
- Project/workspace model for company knowledge bases.
- GitHub HTTPS/SSH repository ingestion, including private repositories with an operator-provided token.
- Google Drive file/document/presentation/spreadsheet import; Drive folder import with an access token.
- Arbitrary web/PDF URL ingestion and direct file upload.
- Code/document indexing for PDF, DOCX, PPTX, XLSX, notebooks, HTML, Markdown, text, CSV, JSON/YAML and common programming languages.
- Code-aware chunks, Python AST symbol extraction, generic multi-language symbol extraction, symbol/dependency metadata, file map and line citations.
- Hybrid retrieval: PostgreSQL full-text search + native pgvector HNSW cosine search + local Qwen3 embeddings + reciprocal-rank fusion + optional LLM reranking.
- Shared persistent memory, chat threads, activity events, learner mastery, resource resume state, onboarding progress, XP and leaderboards.
- Request router for direct Q&A, Socratic tutoring, simple explanation, code reasoning and research.
- Browser-Use Mac bridge for public resource scouting/research while private repository context stays on the Spark.
- Chrome extension for browser learning telemetry, YouTube/research-paper progress, selections and shared memory.
- VS Code extension for workspace indexing, on-save re-indexing, diagnostics/context and direct/Socratic/explain assistance.
- Prometheus metrics, Grafana dashboard, Tempo/OpenTelemetry plumbing, local agent trace storage and optional LangSmith export.
- DGX Spark scripts for Qwen3-32B LoRA fine-tuning, merge, vLLM serving, base-vs-tuned behavior evaluation, TTFT/TPS benchmarking and speculative decoding A/B tests.

## Architecture

```text
                         MACBOOK
        ┌──────────────────┼───────────────────┐
        │                  │                   │
     Chrome             VS Code            Web UI
  + extension         + extension           browser
        │                  │                   │
        ├──── Browser-Use bridge / CDP ───────┤
        └──────────────────┬───────────────────┘
                           │ LAN / Tailscale / SSH
                           ▼
                       DGX SPARK
┌─────────────────────────────────────────────────────────┐
│ FastAPI control plane                                   │
│  Projects · Team · Invites · Paths · XP · Memory       │
│  Source ingestion · RAG · Chat/router · Agent queue    │
│                                                         │
│ Knowledge layer                                         │
│  Git repos · uploads · URLs · Google Drive             │
│  PostgreSQL · pgvector · tsvector · HNSW · symbols   │
│                                                         │
│ Local inference                                         │
│  :8101 spartan-teacher (Qwen3-32B base/tuned)          │
│  :8105 Qwen3-Embedding-0.6B                            │
│  optional dedicated Browser-Use/VLM server             │
│                                                         │
│ Observability                                           │
│  /metrics · Prometheus · Grafana · Tempo · local trace │
└─────────────────────────────────────────────────────────┘
```

## Development smoke path without models

PostgreSQL + pgvector is mandatory; there is no SQLite fallback. Production ingestion also refuses to silently mix a hash embedding space with Qwen embeddings. For a **test/dev-only** no-model smoke run, explicitly opt into deterministic fallback vectors:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
make db-start
ALLOW_EMBEDDING_FALLBACK=1 make seed
ALLOW_EMBEDDING_FALLBACK=1 make run
```

For the real deployment use `make deploy`, which starts the Qwen embedding server before seeding/indexing.

## DGX Spark setup

For a fresh Spark, the no-source-edit deployment path is:

```bash
cp .env.example .env
# edit only runtime credentials/passwords if needed
make deploy
```

`make deploy` performs bootstrap, real PostgreSQL/pgvector integration tests, extension packaging, demo seed, observability startup and application/model startup. For manual control, use:

```bash
cp .env.example .env
make doctor
make dgx-setup
python3 scripts/models/prefetch_models.py
make models
make models-health
make models-test
make start
```

Default resident models:

```text
8101  spartan-teacher          Qwen/Qwen3-32B or artifacts/socratic-merged
8105  embeddings               Qwen/Qwen3-Embedding-0.6B
```

The browser agent reuses `spartan-teacher` through the authenticated `/agent-llm/v1` proxy by default to keep DGX Spark unified-memory usage predictable. A dedicated `browser-use/bu-30b-a3b-preview` server remains optional.

## Fine-tune + prove improvement

```bash
INCLUDE_HF_DATASETS=1 make competition
```

The pipeline:

1. builds the public/local tutoring dataset;
2. fine-tunes Qwen3-32B with LoRA;
3. merges the adapter into `artifacts/socratic-merged`;
4. evaluates base vs tuned behavior on held-out prompts;
5. benchmarks standard vLLM serving;
6. benchmarks n-gram speculative decoding;
7. optionally benchmarks Eagle-3;
8. selects the measured serving profile;
9. writes judge-facing JSON/Markdown results.

For a small pipeline sanity check first:

```bash
make train-smoke
```

Do not claim any quality or performance improvement until the DGX-generated results exist in `experiments/results/`.

## Add a private GitHub repository

From the web UI paste an HTTPS/SSH GitHub URL, or call:

```bash
curl -X POST http://127.0.0.1:8000/api/sources/ingest \
  -H 'content-type: application/json' \
  -d '{"project_id":"PROJECT_ID","uri":"git@github.com:org/private-repo.git","kind":"github"}'
```

For HTTPS private repos set `GITHUB_TOKEN` in `.env` or pass a temporary `access_token` in the request. Tokens are not persisted by the source record.

## Google Drive

Paste a Drive/Docs/Slides/Sheets link into the Sources UI. Public/shared individual files can be imported directly where Google permits it. Private files and folder traversal require `GOOGLE_DRIVE_ACCESS_TOKEN` in `.env` or a temporary access token.

This is a token-based hackathon integration, not a production Google OAuth application.

## Browser-Use on the MacBook

```bash
./scripts/mac/setup_browser_use.sh
cp .env.mac.example .env.mac
# set STUDYBUDDY_API to the Spark URL
./scripts/mac/launch_studybuddy_chrome.sh
./scripts/mac/start_bridge.sh
```

The bridge attaches to the dedicated visible Chrome profile over CDP. Resource scouting is instructed to search only generic/public prerequisite concepts; private source code does not need to leave the Spark.

## Chrome extension

Run `make extensions-package`, unzip `dist/extensions/spartan-studybuddy-chrome.zip`, load that folder unpacked in Chrome, and set:

- DGX endpoint
- user ID
- learning-memory toggle

Then press **Refresh workspaces**, choose the project from the backend-provided workspace list, and save the connection. No project ID needs to be copied manually.

It records browser/resource progress and synchronizes it with the central memory. YouTube progress is based on the HTML video element; research-paper/web progress is based on active/visible page telemetry.

## VS Code extension

Prebuilt extension packages are generated by `make extensions-package` under `dist/extensions/`. Install `spartan-studybuddy-vscode.vsix` in VS Code, or open `apps/vscode-extension` and press `F5` for extension development. Configure:

- `spartan.api`
- `spartan.projectId`
- `spartan.userId`
- `spartan.indexOnSave`

Commands include **Connect to Workspace**, direct code Q&A, Socratic hints, simple explanation and full workspace indexing. The selected StudyBuddy project is persisted at VS Code workspace scope, so no project ID needs to be copied manually.

## Observability

```bash
./scripts/observability/start.sh
```

- StudyBuddy Prometheus metrics: `http://SPARK:8000/metrics`
- Grafana: `http://SPARK:3001`
- Prometheus: bound to localhost `:9090`
- Tempo/OTLP: bound to localhost

The app records model route, model name, retrieved evidence, latency, TTFT, token counts and TPS in the local `agent_traces` table. LangSmith export occurs only if `LANGSMITH_API_KEY` is explicitly configured.

## Tests

```bash
make test
```

The smoke suite starts a real `pgvector/pgvector` PostgreSQL container, initializes the schema, validates hybrid full-text + vector search, direct/Socratic routing, gamified progress and resume memory, validates both extension runtime contracts, and then runs JS/Python syntax checks.

## Current limitations

Read `COMPLETION_REPORT.md` before demo day. The repository is hackathon-grade, not production SaaS: authentication is demo-level, Drive/GitHub integrations are token based, multi-language code graphs are not yet full Tree-sitter/call-graph analysis, and the 32B fine-tune/speculative profiles still need to be executed and benchmarked on your physical DGX Spark. PostgreSQL + pgvector is now the only application database.
