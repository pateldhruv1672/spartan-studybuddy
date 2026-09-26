# AGENTS.md — Spartan StudyBuddy for Teams

## Product north star

Spartan StudyBuddy turns private engineering knowledge into a personalized onboarding academy. A manager connects private repositories/documents, the system infers prerequisites and role-specific learning paths, public Browser-Use agents curate generic learning resources, and a locally fine-tuned teacher provides direct grounded answers or Socratic coaching depending on intent.

## Non-negotiable invariants

1. Private repository/document content remains on the DGX Spark unless the user explicitly exports it.
2. Public-web agents receive sanitized topics/queries rather than raw proprietary source code.
3. Direct factual questions must be answered directly; do not force Socratic behavior everywhere.
4. Socratic mode should use progressive hints and avoid paste-ready assessment answers unless policy explicitly permits them.
5. Web, Chrome and VS Code all use the same project knowledge layer, event stream and persistent learner memory.
6. All source types normalize into `indexed_documents`, `indexed_chunks`, embeddings and code-symbol metadata.
7. Raw vLLM ports bind to localhost. Remote clients use the StudyBuddy API/proxy.
8. Never fabricate benchmark improvements. Show only artifacts produced on the DGX Spark.

## Main modules

```text
backend/app/main.py                  API + websocket hub
backend/app/services/sources.py     GitHub/Drive/web ingestion
backend/app/services/indexer.py     parsers, code chunks/symbols, lexical+dense RRF
backend/app/services/retrieval.py   graph augmentation + optional LLM rerank
backend/app/services/memory.py      central learner memory/mastery
backend/app/services/resource_sessions.py resume summaries/questions
backend/app/services/model_router.py local route/model policy + metrics
backend/app/services/telemetry.py   Prometheus + traces + optional LangSmith
backend/app/agents/assistant.py     qa/socratic/explain/code/research routing
backend/app/agents/onboarding.py    role paths, resources, XP/progress
apps/web                            manager/learner control center
apps/chrome-extension               browser learning telemetry
apps/vscode-extension               code index + contextual tutor
bridges/mac_bridge.py               Browser-Use executor on Mac
training/                           dataset/SFT/merge pipeline
experiments/                        quality, TTFT/TPS, speculation benchmarks
deploy/observability                Prometheus/Grafana/Tempo
```

## Retrieval contract

Prefer structured chunks over arbitrary character splitting:

- Python: AST class/function boundaries and basic import/call metadata.
- Other code: language-aware/generic symbol boundaries where implemented.
- Documents: structural headings/paragraph chunks.
- Retrieval: PostgreSQL tsvector/GIN sparse search + pgvector HNSW cosine search + local Qwen3 embeddings + reciprocal-rank fusion, then optional local LLM reranking.
- Every answer should preserve source/file/line citations when evidence is available.

Production ingestion must not mix embedding spaces. `ALLOW_EMBEDDING_FALLBACK=0` is the deployment default; deterministic hash embeddings are permitted only in tests/dev when explicitly enabled.

## Model topology

Default competition model:

```text
8101  Qwen/Qwen3-32B or artifacts/socratic-merged, served as spartan-teacher
8105  Qwen/Qwen3-Embedding-0.6B
```

Browser-Use reuses `spartan-teacher` through `/agent-llm/v1` by default. Starting `browser-use/bu-30b-a3b-preview` as a second ~30B model is optional and must be memory-tested first.

Fine-tuning learns *teaching behavior*, not customer repositories. Private knowledge belongs in RAG.

## Training modes

The SFT dataset explicitly teaches:

- `[MODE:DIRECT]`: concise grounded factual answer.
- `[MODE:SOCRATIC]`: progressive hint/question.
- `[MODE:EXPLAIN]`: first-principles plain-language explanation + self-check.

Held-out behavior prompts must never enter training.

## Browser/VS Code rules

- Chrome learning telemetry must be opt-in.
- Do not send arbitrary private page contents to public websites.
- VS Code may index opted-in workspace files and nearby current-code context.
- Re-index mutable files under a stable document ID.
- Ignore dependency/build directories and oversized/binary files.

## Definition of done

Run `make test`. If you change an API shape, update web, Chrome, VS Code and tests together. For model-serving changes also run `make models-health` and `make models-test` on the DGX Spark.
