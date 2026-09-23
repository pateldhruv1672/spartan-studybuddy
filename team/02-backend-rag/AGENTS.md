# AGENTS.md — Member 2: Backend, Knowledge Platform & RAG Lead

## Mission

Make private company knowledge trustworthy and retrievable. Own PostgreSQL/pgvector, ingestion, structural code/document indexing, hybrid retrieval, memory, source citations, and assistant routing contracts.

The system should answer “what does this function do?” directly, teach when Socratic mode is selected, explain uploaded material simply, and ground all repository/document claims in indexed evidence.

## Branch

`agent/backend-rag`

## You own

- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/services/indexer.py`
- `backend/app/services/retrieval.py`
- `backend/app/services/sources.py`
- `backend/app/services/memory.py`
- `backend/app/services/projects.py`
- `backend/app/services/chats.py`
- `backend/app/agents/assistant.py`
- `backend/app/agents/onboarding.py` data logic
- `deploy/postgres/**`
- backend-focused tests

Route registration in `backend/app/main.py` is coordinated through Member 5 to avoid merge conflicts.

## Persistence/RAG invariant

PostgreSQL + pgvector only.

```text
source
 → parser
 → structural chunks
 → Qwen3-Embedding-0.6B (1024 dimensions)
 → Postgres
    ├─ tsvector/GIN sparse index
    └─ vector(1024)/HNSW cosine index
 → RRF
 → optional local LLM rerank
 → cited context
```

Never mix hash/fallback embeddings with production Qwen embeddings.

## Ingestion requirements

Must support without source edits:
- GitHub HTTPS repo;
- private repo with token/SSH where environment permits;
- web/document URL;
- Google Drive shared file link;
- Drive API access token for private content;
- website file upload;
- text pushed from VS Code;
- PDF, DOCX, PPTX, XLSX, Markdown, HTML, JSON/YAML, notebooks, source code.

## Code-aware indexing requirements

At minimum:
- stable document IDs;
- re-indexing deletes/replaces stale chunks;
- file path and language metadata;
- class/function/symbol boundaries where parser supports them;
- Python AST symbols/calls/imports;
- line ranges preserved;
- binary/dependency/build/vendor paths ignored;
- oversize files handled safely.

Do not reduce code indexing to arbitrary 2k-character chunks.

## Day-by-day tasks

### Day 1
1. Boot Postgres/pgvector.
2. Verify schema and vector dimension.
3. Ingest one demonstration repo.
4. Verify lexical and vector search independently.
5. Verify RRF returns cited file/line evidence.
6. Make `/api/ask` answer a real repo question using evidence.

### Day 2
1. Harden GitHub/web/upload/Drive ingestion.
2. Finish stable re-indexing and duplicate handling.
3. Add repository map/summary data needed by roadmap generation.
4. Verify central memory is shared by web/browser/VS Code events.
5. Ensure `qa`, `socratic`, `explain`, `code`, `research`, `auto` routing semantics.

### Day 3
1. Build a 20–30 question retrieval test set against the demo repository.
2. Score retrieval hit rate / citation correctness manually or semi-automatically.
3. Tune sparse/dense weighting/RRF candidate sizes if needed.
4. Validate no proprietary snippets enter resource-scout job payloads.
5. Stress test repo re-indexing and concurrent reads.

### Day 4
1. Freeze schema/contracts.
2. Freshly ingest demo repo after DB reset.
3. Verify restart persistence.
4. Produce 5 reliable demo questions and expected cited files.

## Assistant behavior contract

- `qa`: answer directly using evidence. Do not play teacher when the user asked a factual question.
- `socratic`: guide through progressive hints; final solution denied by default.
- `explain`: simple mental model, examples, and check-for-understanding.
- `code`: use current code + repo evidence; point to functions/files.
- `research`: create/consume research agent outputs while keeping private code local.
- `auto`: intent classifier chooses among the above.

## Required acceptance criteria

- `make db-start` healthy.
- `make test` passes against real Postgres.
- pgvector HNSW search works with Qwen embeddings.
- no SQLite runtime path.
- repo re-index does not duplicate stale chunks.
- file/line citations are preserved through retrieval and assistant answer.
- uploaded docs can be explained and queried.
- Google Drive failure returns a clear auth/access error rather than corrupt data.
- private repo data is never placed in Browser-Use public query payloads.

## Handoff to others

Member 3 needs stable JSON from:
- projects/sources/documents/map;
- assistant answer;
- onboarding path/progress;
- learner/resume/admin APIs.

Member 4 needs:
- `/api/events`;
- `/api/resource/session`;
- agent job APIs;
- project list.

Member 5 needs:
- text indexing API;
- assistant API;
- project list;
- health/metrics.
