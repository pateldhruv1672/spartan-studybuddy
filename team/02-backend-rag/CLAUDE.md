# CLAUDE.md — Member 2 Working Instructions

You own the knowledge substrate. Correctness and grounding beat clever abstractions.

Read:
1. `team/SHARED_CONTRACTS.md`
2. role `AGENTS.md`
3. `docs/ARCHITECTURE.md`

## First commands

```bash
make db-start
make test
```

If tests fail because the embedding server is intentionally absent, use only the repository's explicit test/dev fallback mode. Never enable fallback embeddings in real production indexing.

## Development loop

For every ingestion/retrieval change:
1. ingest a fixture;
2. inspect rows/chunks/metadata;
3. run sparse search;
4. run dense search;
5. run hybrid search;
6. ask an answerable question;
7. verify citation path and line range.

Do not judge RAG quality solely from “the answer sounded good.” Verify evidence.

## Contract discipline

If you need to change a request or response shape:
- update `team/SHARED_CONTRACTS.md` first;
- notify Members 3, 4, 5;
- add/adjust tests;
- ask Member 5 to make the route-level merge if `main.py` is affected.

## Failure behavior

Prefer explicit failures:
- embedding server unavailable → indexing fails clearly;
- Drive auth invalid → source ingestion returns actionable error;
- unsupported/binary file → skip with structured reason;
- empty retrieval → answer that evidence was not found; do not invent repo facts.

## End-of-session gate

```bash
make test
```

Record one sample query, retrieved citations, and final answer in your handoff note so downstream teammates can sanity-check the integration.
