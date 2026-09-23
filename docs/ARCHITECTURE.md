# Architecture notes

## Trust boundaries

**MacBook:** browser sessions, VS Code project, Chrome built-in AI, browser automation execution.

**DGX Spark:** organization/project data, learner identity, activity history, indexed private content, onboarding/community state, PostgreSQL/pgvector, model serving, RAG, research/tutor orchestration and local traces.

The Browser-Use bridge token protects the OpenAI-compatible model proxy. In a production deployment, replace the demo identity model with SSO/OIDC and organization-scoped RBAC.

## Persistence

PostgreSQL 16 + pgvector is mandatory. `deploy/postgres/docker-compose.yml` starts `pgvector/pgvector:0.8.6-pg16` bound to localhost on the Spark. FastAPI runs idempotent schema initialization at startup.

`indexed_chunks` stores each code/document chunk together with:

- structural metadata and line ranges;
- a `tsvector` generated column with a GIN index for lexical retrieval;
- a native `vector(1024)` embedding with an HNSW cosine index.

There is no SQLite/vector-blob fallback.

## Retrieval path

```text
GitHub/private repo ─┐
Google Drive ────────┤
Web/PDF URLs ───────┼→ parser → structural chunks → PostgreSQL
Website uploads ────┤                            ├→ tsvector/GIN sparse search
VS Code files ──────┘                            └→ pgvector/HNSW dense search
                                                      ↓
                                              reciprocal-rank fusion
                                                      ↓
                                              optional LLM reranker
                                                      ↓
                                           Tutor / Q&A / Roadmap / Research
```

Code chunks preserve symbols, paths and line ranges. Python gets AST-aware symbols/call edges; other supported languages use structural symbol extraction. Stable document IDs cause old chunks to be cascade-deleted before re-indexing.

## Shared memory path

```text
Chrome events ─┐
VS Code events ├→ PostgreSQL events/resource_sessions/memory/mastery → all agents
Web app events ┘
```

The same project/user memory is read by the direct Q&A router, Socratic tutor, code tutor and roadmap/research agents. WebSocket broadcast is currently single-process; for multiple API workers add Redis/NATS pubsub.
