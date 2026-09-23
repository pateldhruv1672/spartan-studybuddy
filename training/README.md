# Socratic tutor fine-tuning

Spartan StudyBuddy fine-tunes **teaching behavior**, not course knowledge. Course facts remain in the indexed RAG layer; the adapter learns to diagnose, question, hint, scaffold, and avoid dumping ready-to-submit answers.

## One-command DGX Spark path

```bash
make train
```

This builds the NVIDIA PyTorch training image, prepares the dataset, trains a Qwen3-8B LoRA adapter, and merges it into `artifacts/socratic-merged/` for vLLM.

Use public Socratic datasets in addition to the built-in cross-domain data:

```bash
INCLUDE_HF_DATASETS=1 make train
```

Optional QLoRA:

```bash
SOCRATIC_QUANTIZATION=4bit make train
```

Then measure the result:

```bash
make benchmark
make results
```

Or run training + all quality/performance experiments:

```bash
make competition
```

See `docs/FINE_TUNING_AND_BENCHMARKS.md` for the exact evaluation methodology and serving profiles.
