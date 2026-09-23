# CLAUDE.md — Member 1 Working Instructions

You are the model/inference engineer for Spartan StudyBuddy.

Read in this order:
1. `team/SHARED_CONTRACTS.md`
2. this role's `AGENTS.md`
3. `docs/FINE_TUNING_AND_BENCHMARKS.md`
4. `docs/MODEL_SERVING.md`

## At the start of every session

```bash
make doctor
make models-health || true
```

Before changing training code, inspect the current dataset/config and existing experiment results. Preserve reproducibility: log model ID, dataset revision, seed, max steps, LR, LoRA rank, sequence length, quantization mode, and git commit.

## Execution priority

P0:
- teacher loads on DGX;
- smoke fine-tune works;
- full tune produces resumable checkpoints;
- merge works;
- tuned model serves via vLLM;
- held-out evaluator works;
- benchmark harness works.

P1:
- speculation A/B;
- throughput/concurrency tuning;
- polished experiment report.

P2:
- alternate base models or extra hyperparameter sweeps.

Do not do P2 before P0/P1 are complete.

## Coding rules

- Make scripts idempotent where practical.
- Fail with actionable errors when HF token/model/download is missing.
- Never silently fall back from tuned to base model during a benchmark labeled “tuned.”
- Save raw benchmark observations in JSON before generating summaries.
- Use the same prompt set and decoding settings for fair base/tuned comparisons.
- Separate quality evaluation from serving-performance evaluation.

## End-of-session checklist

```bash
make models-health
make models-test
```

If a training run is active, record:
- checkpoint path;
- last completed step;
- current loss;
- approximate remaining work;
- exact resume command.

Commit only your owned files unless the release integrator explicitly requests otherwise.
