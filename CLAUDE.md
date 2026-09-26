# CLAUDE.md — Spartan StudyBuddy developer guide

Read `AGENTS.md`, `README.md` and `COMPLETION_REPORT.md` first.

## Mission

Maintain a local-first enterprise onboarding product that can ingest private code/docs, construct role-specific learning paths, curate public resources, remember learner progress across web + IDE, and route each question to the correct direct/Socratic/explanation/research behavior.

## Before edits

```bash
make test
```

Keep it green.

## Important paths

- `backend/app/services/sources.py`: GitHub, Google Drive and web ingestion.
- `backend/app/services/indexer.py`: canonical document/code index.
- `backend/app/services/retrieval.py`: hybrid retrieval/reranking.
- `backend/app/agents/assistant.py`: intent/mode routing.
- `backend/app/agents/onboarding.py`: role paths, Browser-Use scout jobs, XP.
- `backend/app/services/resource_sessions.py`: continuation summary/questions.
- `bridges/mac_bridge.py`: Browser-Use on the MacBook.
- `apps/chrome-extension`: browsing/resource memory.
- `apps/vscode-extension`: code context/indexing.
- `training/`: 32B Socratic/direct/explain fine-tuning pipeline.
- `experiments/`: base/tuned/speculative benchmarks.

## Engineering rules

- Never make a cloud AI API required.
- Never expose raw vLLM admin/server ports over the hackathon LAN.
- Do not send private code to public Browser-Use searches; extract generic concepts locally first.
- Direct code/document Q&A should answer directly and cite evidence.
- Socratic mode should teach instead of dumping a final solution.
- Keep one shared memory rather than separate browser/IDE memories.
- Keep hybrid retrieval and file/line citations intact when adding vector stores or rerankers.
- Hosted LangSmith is optional only. Local traces remain the source of truth.

## Competition model

`SOCRATIC_BASE_MODEL=Qwen/Qwen3-32B` by default. Train LoRA, merge the adapter, then serve the merged checkpoint through vLLM as `spartan-teacher`.

Benchmark standard serving against n-gram and optional Eagle-3 speculative decoding on the physical Spark. Never hard-code a claimed improvement.
