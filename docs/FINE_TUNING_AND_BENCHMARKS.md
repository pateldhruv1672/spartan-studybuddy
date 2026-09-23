# Spartan StudyBuddy — fine-tuning + performance experiment

This is the hackathon evidence pipeline. It produces measured artifacts under `experiments/results/`; the Engineering Lab UI reads those files directly.

## Model objective

The default verifier is **`Qwen/Qwen3-32B`**. StudyBuddy fine-tunes a LoRA/QLoRA adapter for mode-conditioned enterprise tutoring:

- `[MODE:DIRECT]`: answer factual repository/document questions directly and cite retrieved private context;
- `[MODE:SOCRATIC]`: diagnose understanding, ask a focused question, and escalate hints without dumping an assessment solution;
- `[MODE:EXPLAIN]`: explain concepts simply with a mental model and concrete example.

Private customer repositories are **never** fine-tuning data. Company knowledge remains in PostgreSQL/pgvector RAG and the code graph. The merged adapter is deployed as a standalone checkpoint so vLLM and speculative decoding operate on one target checkpoint.

## Dataset

Offline/local dataset:

```bash
python3 training/prepare_socratic_dataset.py --output-dir training/data
```

Optional public tutoring mix:

```bash
INCLUDE_HF_DATASETS=1 make dataset
```

`training/data/behavior_eval.jsonl` is held out and never placed into the SFT split.

## Training on DGX Spark

```bash
make train-smoke   # short pipeline validation
make train         # normal run
```

Defaults:

```text
base                 Qwen/Qwen3-32B
max steps            300
sequence length       3072
LoRA rank             32
LoRA alpha            64
learning rate         1e-4
BF16                   yes
QLoRA                  optional (SOCRATIC_QUANTIZATION=4bit)
```

Outputs:

```text
artifacts/socratic-lora/
artifacts/socratic-lora/studybuddy_training_metrics.json
artifacts/socratic-merged/
```

## Quality proof

Base and tuned checkpoints receive the same held-out cases. The evaluation records:

- direct-answer correctness/appropriateness;
- direct-answer leakage in Socratic mode;
- probing-question rate;
- progressive-guidance behavior;
- concision;
- an inspectable weighted behavior score.

No cloud judge is required.

## Serving + performance proof

`make benchmark` sequentially measures:

1. base Qwen3-32B;
2. merged StudyBuddy Teacher 32B;
3. tuned + n-gram speculative decoding;
4. optionally tuned + Qwen3-32B Eagle-3 speculator.

Metrics include p50/p95 TTFT, end-to-end latency, decode tokens/sec, aggregate output tokens/sec, and speculative acceptance metrics when available. Speculation is selected only if the measured Spark result improves the configured interactive objective.

The selected profile is written to:

```text
experiments/results/recommended_serving.env
```

`make start` consumes it automatically.

## Complete experiment

```bash
make competition
```

Pipeline:

```text
mode-conditioned tutoring data
  → Qwen3-32B LoRA/QLoRA
  → merge adapter
  → held-out base/tuned quality eval
  → standard vLLM benchmark
  → n-gram speculation A/B
  → optional Eagle-3 A/B
  → measured profile selection
  → HACKATHON_RESULTS.md + JSON artifacts
```

## Agent benchmark

With the Mac Browser-Use bridge active:

```bash
python3 experiments/benchmark_agent_jobs.py \
  --api http://SPARK_IP:8000 \
  --jobs 3 \
  --label vllm-browser \
  --output experiments/results/agent_vllm.json
```

This measures actual Resource Scout job completion p50/p95 and jobs/min, not only raw model throughput.
