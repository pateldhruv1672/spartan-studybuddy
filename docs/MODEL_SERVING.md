# Spartan StudyBuddy model serving on DGX Spark

The MacBook is the interaction surface. DGX Spark is the private inference, retrieval, memory and observability appliance. Raw vLLM ports bind locally; FastAPI is the application boundary.

## Default resident topology

| Role | Model / served name | Port | Purpose |
|---|---|---:|---|
| teacher/reasoner | `spartan-teacher` → `Qwen/Qwen3-32B` or merged tuned checkpoint | 8101 | direct Q&A, Socratic tutor, code reasoning, roadmaps, research synthesis, Browser-Use planning |
| embeddings | `Qwen/Qwen3-Embedding-0.6B` | 8105 | pgvector dense retrieval |

The default Browser-Use bridge reuses `spartan-teacher`. A dedicated `browser-use/bu-30b-a3b-preview` server remains optional (`START_DEDICATED_BROWSER_MODEL=1`) when memory headroom and browser-task quality justify it.

## First-time setup

```bash
cp .env.example .env
make dgx-setup
python3 scripts/models/prefetch_models.py   # recommended before demo day
```

`make dgx-setup` also starts PostgreSQL/pgvector and installs backend dependencies.

## Fine-tune + benchmark

```bash
make competition
```

The measured winner is written to `experiments/results/recommended_serving.env`.

## Start the full system

```bash
make start
```

`scripts/models/start_general.sh` automatically serves `artifacts/socratic-merged/` when present and `USE_TUNED_SOCRATIC_MODEL=1`; otherwise it serves `Qwen/Qwen3-32B`. The public model name remains `spartan-teacher`, so no application code changes are required after training.

## Speculative decoding

Supported tuned-model profiles:

```text
none
ngram     prompt lookup, no draft-model residency
Eagle-3   RedHatAI/Qwen3-32B-speculator.eagle3
```

The benchmark harness treats speculation as an A/B experiment and activates only the measured winner.

## Browser-Use on Mac

```bash
./scripts/mac/setup_browser_use.sh
cp .env.mac.example .env.mac
# Set STUDYBUDDY_API=http://<SPARK-IP>:8000
./scripts/mac/launch_studybuddy_chrome.sh
./scripts/mac/start_bridge.sh
```

Browser-Use controls the visible dedicated Chrome profile through CDP. Its LLM calls go through the authenticated StudyBuddy proxy to the local teacher model; raw vLLM is not exposed to the LAN.

## PostgreSQL / pgvector

The application requires PostgreSQL 16 + pgvector. `make db-start` starts the included `pgvector/pgvector` container. Startup creates the vector extension and idempotent schema automatically.

Retrieval uses:

```text
PostgreSQL tsvector/GIN lexical retrieval
+ pgvector cosine search over vector(1024)
+ HNSW vector index
+ reciprocal-rank fusion
+ optional local LLM reranking
```

There is no SQLite persistence or vector-blob fallback.
