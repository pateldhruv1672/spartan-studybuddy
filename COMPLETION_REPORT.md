# Spartan StudyBuddy — PostgreSQL/pgvector hardening audit

This report separates source-level validation performed in the packaging environment from integrations that must be exercised on the actual DGX Spark/MacBook because this packaging environment has no Docker/PostgreSQL/NVIDIA runtime.

## Implemented

### Persistence + RAG
- PostgreSQL is the only application persistence database (`DATABASE_URL` is mandatory at runtime).
- `pgvector` is created automatically on startup.
- Embeddings are native `vector(1024)` values, not byte blobs.
- HNSW cosine index on embeddings.
- PostgreSQL generated `tsvector` + GIN index for lexical retrieval.
- Hybrid lexical+dense retrieval using reciprocal-rank fusion and local reranking.
- Documents, chunks, code symbols/edges, projects, users, invites, memories, chats, mastery, onboarding paths, progress, XP, resource sessions, agent jobs and telemetry traces persist in PostgreSQL.
- File/line citations preserved through retrieval.

### Sources + knowledge
- File upload, GitHub HTTPS/SSH clone, URL/PDF ingestion and Google Drive link/token paths.
- PDF/DOCX/PPTX/XLSX/IPYNB/HTML/text/config/code extraction.
- Python AST symbol extraction plus generic multi-language code chunking/symbol metadata.
- VS Code workspace/on-save re-indexing into the same project knowledge base.

### Application
- Enterprise project/workspace/team model, invitations and role-based onboarding paths.
- Gamified progress, XP, streaks and leaderboard.
- Persistent direct Q&A, simple explanation, Socratic tutoring, code reasoning and research routes.
- Shared central memory across web, Chrome, VS Code and agents.
- Resume summaries/checkpoints for tracked resources including YouTube browser sessions.
- Browser-Use job bridge and authenticated local model proxy.

### Model + systems engineering
- Qwen3-32B LoRA/QLoRA training, checkpoint resume and adapter merge.
- Held-out behavior evaluation for base vs tuned model.
- vLLM deployment under stable `spartan-teacher` served name.
- Standard, n-gram speculative and optional Eagle-3 benchmark profiles.
- TTFT, p50/p95 latency, decode TPS and aggregate throughput benchmark artifacts.
- Qwen3-Embedding local vLLM endpoint for pgvector retrieval; production indexing fails closed if the embedding server is unavailable, preventing incompatible vector spaces from being mixed.
- Prometheus metrics, Grafana/Tempo configuration, OpenTelemetry hooks and PostgreSQL agent trace store; LangSmith optional.

## Extension validation performed in this package

The deterministic extension contract suite passes:

- Chrome Manifest V3 package/file/permission validation.
- Chrome service-worker config/ask/event API routing contract.
- Chrome content-script selection UI/message contract.
- VS Code extension activation, command registration, sidebar rendering and save-listener contract.
- VS Code includes **Connect to Workspace**, which fetches project choices from the backend and persists the selected project at workspace scope.
- Both extension artifacts are prepackaged under `dist/extensions/`.

These tests verify code/manifest contracts without requiring a human GUI session. Final installation against the actual Mac Chrome and VS Code remains a deployment check, not a source-code change.

## Static validation performed

- All Python files compile.
- All shell scripts parse with `bash -n`.
- All client/test JavaScript parses with `node --check`.
- All JSON files parse.
- Extension contract tests pass.
- Runtime source contains no SQLite/FTS5 database path.

## Must be executed on the actual DGX Spark/MacBook

Run this first on Spark:

```bash
cp .env.example .env
make dgx-setup
make test
```

`make test` is deliberately a real PostgreSQL/pgvector integration gate: it starts the included database container, runs the integration suite, checks the vector extension/table/indexes, and validates both extensions. There is no SQLite test fallback.

Then validate:

- loading/fine-tuning Qwen3-32B on the physical Spark;
- measured base-vs-tuned quality delta;
- measured TTFT/TPS and speculative-decoding winner;
- private GitHub/Drive credentials;
- Mac Browser-Use CDP control;
- installation of the packaged Chrome/VS Code extensions;
- Grafana/Tempo together with final model residency.

## No-source-edit deployment contract

After unzipping, deployment should require only `.env` configuration for credentials/passwords/IP/model choices. The application, database schema creation, migrations-by-idempotent-startup, model routing, extension packages and benchmark scripts do not require source edits.

## Remaining production gaps (not hackathon blockers)

- enterprise OIDC/SSO and hardened organization-level authorization;
- external secrets manager/token rotation;
- GitHub App / Google OAuth consent flows instead of supplied access credentials;
- compiler-grade multi-language call graph/Tree-sitter coverage for every language;
- recursive Drive folder traversal across arbitrary nested/shared-drive structures;
- distributed workers/pub-sub/high availability, backup/restore and formal security/accessibility audits.

## Completion estimate

- Hackathon implementation completeness: **~90%**.
- Demo-critical source code and packaging: **~95%**.
- Real hardware/account integration validation: **pending until `make test` + model/browser checks run on your equipment**.
- Production enterprise readiness: **~55%**.
