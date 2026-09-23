# AGENTS.md — Member 1: Model, Fine-Tuning & Inference Lead

## Mission

Own the hackathon's strongest technical claim: a large local teacher model that is measurably better at enterprise software tutoring than its base checkpoint, and a vLLM serving configuration that is measurably faster for the StudyBuddy workload.

You are not responsible for frontend features, Postgres schema, Chrome, or VS Code.

## Branch

`agent/model-inference`

## You own

- `training/**`
- `experiments/**`
- `scripts/models/**`
- `scripts/training/**`
- `scripts/competition/**`
- model-specific documentation
- model-related `.env.example` values

Do not modify `apps/**` or retrieval/database implementation without a handoff to its owner.

## Model target

Primary competition model:

```text
Qwen/Qwen3-32B
   + LoRA/QLoRA teaching behavior
   → merged artifacts/socratic-merged/
   → vLLM served as spartan-teacher
```

Do not fine-tune private company repositories into weights. Repository knowledge stays in RAG. The model learns behavior: direct grounded Q&A, simple explanation, progressive Socratic tutoring, misconception correction, architecture/code reasoning.

## Required training modes

The dataset must deliberately contain at least these behaviors:

- `[MODE:DIRECT]` — answer factual questions directly and concisely.
- `[MODE:SOCRATIC]` — guide with progressive questions/hints; no final answer by default.
- `[MODE:EXPLAIN]` — first-principles, plain-language explanation plus a small comprehension check.
- code comprehension examples grounded in supplied context.
- debugging guidance that points at evidence before suggesting a fix.
- misconception correction.
- role-sensitive depth: junior vs mid/senior.

## Day-by-day tasks

### Day 1
1. Run `make doctor`.
2. Start base teacher and embeddings.
3. Confirm OpenAI-compatible inference through `:8101/v1` and `:8105/v1`.
4. Run `make train-smoke` before the full run.
5. Audit dataset split: train/validation/held-out must be disjoint.
6. Produce a 20-prompt manual qualitative base-model sample for later comparison.

### Day 2
1. Finalize dataset composition and filtering.
2. Launch QLoRA/LoRA run with checkpointing.
3. Watch loss, sequence truncation, OOM, and throughput.
4. If training is stable, do not waste time tuning dozens of hyperparameters. Prefer one clean run and one targeted correction run.

### Day 3
1. Merge best adapter into standalone model.
2. Serve tuned checkpoint as `spartan-teacher`.
3. Run held-out evaluation against identical base/tuned prompts.
4. Benchmark:
   - base standard vLLM;
   - tuned standard vLLM;
   - tuned + n-gram speculation;
   - tuned + Eagle-3 when compatible.
5. Record TTFT, p50/p95 latency, decode tok/s, aggregate tok/s, and acceptance metrics where available.
6. Run `experiments/select_best_spec.py`; never assume speculation wins.

### Day 4
1. Freeze model/checkpoint.
2. Re-run the exact final benchmark twice for stability.
3. Produce final `HACKATHON_RESULTS.md` and qualitative examples.
4. Give Member 3 the exact measured numbers/JSON only.
5. Give Member 5 the frozen serving profile/env.

## Required acceptance criteria

- base model serves successfully;
- tuned merged model serves successfully;
- behavior eval uses held-out prompts;
- direct-answer mode remains direct after fine-tuning;
- Socratic mode reduces answer dumping on the eval set;
- no claimed quality delta without saved JSON artifacts;
- no claimed throughput/latency improvement without measured artifacts;
- `make models-health` passes;
- `make models-test` passes;
- `make benchmark` completes on the physical Spark.

## Performance tuning order

Tune one variable at a time:
1. stable model load;
2. max model length;
3. GPU utilization;
4. max sequences / batched tokens;
5. prefix caching;
6. speculative decoding;
7. only then concurrency experiments.

For interactive tutoring, optimize TTFT and p95 latency, not only peak batch throughput.

## Artifacts you hand off

- `artifacts/socratic-merged/`
- `experiments/results/base_quality.json`
- `experiments/results/tuned_quality.json`
- serving benchmark JSONs
- `experiments/results/recommended_serving.env`
- `experiments/results/HACKATHON_RESULTS.md`
- 3–5 clean qualitative examples showing base vs tuned behavior

## Never do

- Do not claim “3× faster” because a theoretical spec-decoding blog says so.
- Do not train on held-out evaluation prompts.
- Do not fine-tune private customer repository data unless explicitly approved for a separate private adapter experiment.
- Do not expose raw vLLM ports on the event LAN.
- Do not change API model names from `spartan-teacher` without coordination.
