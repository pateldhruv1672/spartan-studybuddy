# Spartan StudyBuddy for Teams

**Private codebase → structured onboarding academy → locally fine-tuned Socratic engineering tutor.**

🤗 **Fine-tuned model on Hugging Face:** [`dhruv1672/spartan-studybuddy-qwen3.8-27b-nvfp4`](https://huggingface.co/dhruv1672/spartan-studybuddy-qwen3.8-27b-nvfp4) — Qwen3.8-27B, LoRA-tuned for Socratic tutoring, NVFP4-quantized, with native MTP speculative decoding. Full training/quantization writeup and measured benchmarks in [Model training](#qwen38-27b-socratic-fine-tune-progress-architecture-and-results-2026-09-24) below.

## Elevator pitch

A new hire's first weeks are usually the same private tax paid over and over: read scattered docs, ask the same five Slack questions every engineer asks, get pointed at a wiki page from two reorgs ago. Spartan StudyBuddy turns a company's own repositories, documents and internal knowledge into a role-specific onboarding academy, generated and answered entirely by models running on the team's own hardware — nothing about the private codebase ever leaves the machine.

A manager connects a repository (or a Drive folder, or a handful of URLs); the system indexes it, builds a knowledge graph, and generates a week-by-week curriculum for a chosen role. Each concept in that curriculum is paired with a real public resource — a specific YouTube video, a specific doc page, a specific blog post — found and verified by a browser-automation agent that runs on the *learner's own machine*, not the GPU box, so scouting the open web never competes with the model inference budget and private code is never sent to a public search. The learner studies through direct grounded Q&A, plain-language explanations, or Socratic guidance that teaches instead of handing over the answer, all backed by citations into the actual private source. Progress, quiz scores, XP and a live leaderboard turn onboarding into something a manager can actually see happening, in real time, across a team.

Everything — retrieval, routing, the tutor itself — runs on locally-served, fine-tuned open models. No onboarding conversation, and no line of private code, ever has to touch a third-party API.

## What is in this repository

- Apple-inspired web control center served by FastAPI.
- Project/workspace model for company knowledge bases.
- GitHub HTTPS/SSH repository ingestion, including private repositories with an operator-provided token.
- Google Drive file/document/presentation/spreadsheet import; Drive folder import with an access token.
- Arbitrary web/PDF URL ingestion and direct file upload.
- Code/document indexing for PDF, DOCX, PPTX, XLSX, notebooks, HTML, Markdown, text, CSV, JSON/YAML and common programming languages.
- Code-aware chunks, Python AST symbol extraction, generic multi-language symbol extraction, symbol/dependency metadata, file map and line citations.
- Hybrid retrieval: PostgreSQL full-text search + native pgvector HNSW cosine search + local Qwen3 embeddings + reciprocal-rank fusion + optional LLM reranking.
- Shared persistent memory, chat threads, activity events, learner mastery, resource resume state, onboarding progress, XP and leaderboards.
- Request router for direct Q&A, Socratic tutoring, simple explanation, code reasoning and research.
- Browser-Use Mac bridge for public resource scouting/research while private repository context stays on the Spark.
- Chrome extension for browser learning telemetry, YouTube/research-paper progress, selections and shared memory.
- VS Code extension (lighter-weight companion to the Chrome extension) for workspace indexing, on-save re-indexing, and direct/Socratic/explain chat inside the editor.
- Prometheus metrics, Grafana dashboard, Tempo/OpenTelemetry plumbing, local agent trace storage and optional LangSmith export.
- DGX Spark scripts for Qwen3-32B LoRA fine-tuning, merge, vLLM serving, base-vs-tuned behavior evaluation, TTFT/TPS benchmarking and speculative decoding A/B tests.

## Architecture

```text
                         MACBOOK
        ┌──────────────────┼───────────────────┐
        │                  │                   │
     Chrome             VS Code            Web UI
  + extension         + extension           browser
        │                  │                   │
        ├──── Browser-Use bridge / CDP ───────┤
        └──────────────────┬───────────────────┘
                           │ LAN / Tailscale / SSH
                           ▼
                       DGX SPARK
┌─────────────────────────────────────────────────────────┐
│ FastAPI control plane                                   │
│  Projects · Team · Invites · Paths · XP · Memory       │
│  Source ingestion · RAG · Chat/router · Agent queue    │
│                                                         │
│ Knowledge layer                                         │
│  Git repos · uploads · URLs · Google Drive             │
│  PostgreSQL · pgvector · tsvector · HNSW · symbols   │
│                                                         │
│ Local inference                                         │
│  :8101 spartan-teacher (Qwen3-32B base/tuned)          │
│  :8105 Qwen3-Embedding-0.6B                            │
│  optional dedicated Browser-Use/VLM server             │
│                                                         │
│ Observability                                           │
│  /metrics · Prometheus · Grafana · Tempo · local trace │
└─────────────────────────────────────────────────────────┘
```

The running app also has a live, presentation-ready **Architecture** page (in the sidebar nav, `/architecture`) with a more detailed component-and-data-flow diagram — every arrow labeled with the real protocol or call it represents (HTTP poll interval, WebSocket push, CDP port, the `/agent-llm` proxy), not just a box with a name on it.

## Walkthrough

1. **Connect a workspace.** A manager creates a project and points it at a GitHub repo (HTTPS or SSH, private repos supported with a token), a Google Drive folder, or a handful of URLs. Ingestion chunks and embeds the content, extracts code symbols, and builds a knowledge graph of concepts, files and their relationships — entirely on the local machine.
2. **Generate a role's onboarding path.** Pick a role (e.g. "Backend Engineer") and a time budget; if the repo is indexed, the graph engine builds a curriculum grounded in the *actual* codebase (real files, real symbols, a quiz gating each module); otherwise an LLM engine builds a generic-but-structured curriculum from the role alone.
3. **Resources get scouted automatically.** Each module's topic is dispatched as a job to whichever bridge is online — one small browser-use agent per topic, searching and clicking real results (never a freely-typed URL), running several topics concurrently. Every candidate is validated (topic relevance, real YouTube-ID shape, live URL check) before being stored with a real screenshot and a real, code-measured video duration — never a model's guess at either.
4. **The learner studies.** Each concept step shows its attached resource inline — the specific video or article, not a generic search link — plus direct Q&A, a Socratic hint mode that guides instead of answering, and a "explain simply" mode, all grounded in citations back into the private source.
5. **Progress is visible.** Completing an item and passing a module's quiz earns XP; a live leaderboard and analytics dashboard let a manager see the whole team's onboarding progress at a glance, without asking anyone for a status update.
6. **Memory is shared, not siloed.** The Chrome extension tracks reading/watch progress on whatever resource the learner actually opens (in a real tab, or the dashboard's own embedded player) and writes it back to the same resource-session store the dashboard's "resume where you left off" feed reads from.

## Development smoke path without models

PostgreSQL + pgvector is mandatory; there is no SQLite fallback. Production ingestion also refuses to silently mix a hash embedding space with Qwen embeddings. For a **test/dev-only** no-model smoke run, explicitly opt into deterministic fallback vectors:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
make db-start
ALLOW_EMBEDDING_FALLBACK=1 make seed
ALLOW_EMBEDDING_FALLBACK=1 make run
```

For the real deployment use `make deploy`, which starts the Qwen embedding server before seeding/indexing.

## DGX Spark setup

For a fresh Spark, the no-source-edit deployment path is:

```bash
cp .env.example .env
# edit only runtime credentials/passwords if needed
make deploy
```

`make deploy` performs bootstrap, real PostgreSQL/pgvector integration tests, extension packaging, demo seed, observability startup and application/model startup. For manual control, use:

```bash
cp .env.example .env
make doctor
make dgx-setup
python3 scripts/models/prefetch_models.py
make models
make models-health
make models-test
make start
```

Default resident models:

```text
8101  spartan-teacher          Qwen/Qwen3-32B or artifacts/socratic-merged
8105  embeddings               Qwen/Qwen3-Embedding-0.6B
```

The browser agent reuses `spartan-teacher` through the authenticated `/agent-llm/v1` proxy by default to keep DGX Spark unified-memory usage predictable. A dedicated `browser-use/bu-30b-a3b-preview` server remains optional.

## Fine-tune + prove improvement

```bash
INCLUDE_HF_DATASETS=1 make competition
```

The pipeline:

1. builds the public/local tutoring dataset;
2. fine-tunes Qwen3-32B with LoRA;
3. merges the adapter into `artifacts/socratic-merged`;
4. evaluates base vs tuned behavior on held-out prompts;
5. benchmarks standard vLLM serving;
6. benchmarks n-gram speculative decoding;
7. optionally benchmarks Eagle-3;
8. selects the measured serving profile;
9. writes judge-facing JSON/Markdown results.

For a small pipeline sanity check first:

```bash
make train-smoke
```

Do not claim any quality or performance improvement until the DGX-generated results exist in `experiments/results/`.

## Qwen3.8-27B Socratic fine-tune: progress, architecture, and results (2026-09-24)

This supersedes the Qwen3-32B path described above for the actual DGX Spark run. Everything below was
measured on-device; no number here is estimated or hard-coded.

### Model architecture

- **Base:** [`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B), HF arch `qwen3_5`, model class
  `Qwen3_5ForConditionalGeneration` (a VLM class; loaded via `AutoModelForImageTextToText`).
- **Hybrid attention:** GatedDeltaNet linear attention on 48 of 64 layers, full self-attention on every
  4th layer (layers 3, 7, 11, ... 63).
- **Vision tower:** `model.visual.*` (Qwen3VL-style ViT blocks) — present in the checkpoint, excluded from
  both LoRA tuning and quantization; StudyBuddy only uses this model as a text tutor.
- **Native MTP draft head:** the base checkpoint ships 15 `mtp.*` tensors (~425M params, bf16,
  `mtp_num_hidden_layers=1`, no dedicated embeddings — reuses the main model's embedding table). This is
  what makes real speculative decoding possible without a separately trained drafter (see below).
- Needs `transformers==5.14.1` (has the `qwen3_5` model type; also the newest version `nvidia-modelopt`
  0.37.0 tolerates without warning).

### LoRA fine-tune

- **Data:** real Hugging Face datasets only — `meric533/socrateach-sft` (8000 rows) +
  `AndreiSobo/PACT-Socratic-Coding-Tutor` (2000 rows). No synthetic/templated seed rows.
- **Split:** 3-way, leak-checked by SHA-256 row fingerprint (`training/prepare_socratic_dataset.py`) —
  train 7241 / val 493 / test 493 rows (7216 / 492 survive the assistant-only label-mask filter).
- **LoRA config:** r=32, alpha=64, dropout=0.05, **only layers 48–63** (last 16 of 64 — later layers
  govern style/behavior more than early layers), targeting
  `q/k/v/o_proj, gate/up/down_proj, in_proj_qkv/z/b/a, out_proj` (attention + MLP + GatedDeltaNet
  projections), vision excluded. **58,363,904 trainable params — 0.2129%** of ~27.4B total.
- **Training:** bf16 (an NVFP4 QLoRA path was tried and abandoned — modelopt's real-quant GEMM needs
  `tensorrt_llm`, not installed here, so it silently fell back to dequantizing every layer, making
  training too slow to be practical). 400 steps, batch 1 × grad-accum 8, lr 1e-4 cosine, ~91 s/step,
  ~11 h wall clock.
- **Loss:** train_loss 0.8064 final. eval_loss **0.7893 → 0.7766** (step 200 → step 400, still improving,
  not yet plateaued/overfitting).
- Checkpoint: `artifacts/socratic-bf16-lora/` — verified byte-for-byte: no NaN/Inf, all `lora_B` tensors
  non-zero (genuinely trained, not stuck at init), config matches the trained layer range exactly.

### Post-processing: merge → NVFP4 quantize → export → MTP graft

1. **Merge** (`training/nvfp4/merge_bf16_lora.py`): adapter merged into bf16 base → 51.75 GiB checkpoint.
   Verified layers 48–63 changed and layers 0–47 are byte-identical to the base — the merge touched
   exactly what it should and nothing else.
2. **Quantize** (`training/nvfp4/quantize.py`, `nvidia-modelopt` 0.37.0): NVFP4 (4-bit, group size 16),
   calibrated on 512 training rows. `conv1d` (GatedDeltaNet), the vision tower, and `lm_head` are
   excluded from quantization — matching NVIDIA's own official NVFP4 release recipe for this model
   family, not a StudyBuddy-specific choice.
3. **Export** (`training/nvfp4/export_nvfp4.py`, modelopt's `export_hf_checkpoint()`): final servable
   checkpoint, **18.73 GiB weights** (vs. 51.75 GiB bf16, vs. ~55.6 GiB base on disk).
4. **MTP graft** (`training/nvfp4/graft_mtp.py`, new): the merge/export pipeline doesn't carry the base
   model's `mtp.*` draft-head tensors forward, so this step additively copies them from the base
   checkpoint into a new shard (`model-mtp.safetensors`, 810 MiB) and extends
   `model.safetensors.index.json` — **the original `model.safetensors` is never opened for writing.**

**Two real bugs found and fixed along the way (both metadata, not weight-data problems — no
re-quantization needed for either fix):**
- `modelopt`'s exporter wrote the quantization `ignore`/`exclude_modules` lists with an extra, incorrect
  `.layers` path segment (`model.layers.visual*` instead of the real key prefix `model.visual*`), so
  vLLM's loader thought the vision tower should be NVFP4-quantized when it wasn't — it allocated
  wrong-sized destination tensors and crashed loading the real bf16 vision weights. Fixed by correcting
  the path strings in `config.json` / `hf_quant_config.json` (originals kept as `*.orig-buggy-ignore-paths`).
- After grafting MTP weights, the same ignore lists had no `mtp*` entry (because MTP wasn't in the model
  when quantization ran), so vLLM tried to load the grafted bf16 MTP weights into NVFP4-shaped slots.
  Fixed by adding `mtp*` / `mtp.layers.0*` to the ignore lists, matching NVIDIA's own official NVFP4
  release for this model (which excludes MTP from quantization entirely).
- Also had to copy `preprocessor_config.json` / `video_preprocessor_config.json` from the base repo into
  the export dir — never pulled into the local cache because the pipeline only ever called
  `AutoModelForImageTextToText` / `AutoTokenizer`, not the image processor.

Final checkpoint: `artifacts/socratic-nvfp4-final/` (20 GiB total, weights + MTP shard). Confirmed
correct end to end: vLLM 0.30.0 loads it, resolves `Qwen3_5ForConditionalGeneration`, picks
`FlashInferCutlassNvFp4LinearKernel` (real NVFP4 GEMM, not a simulated/dequantized path), and answers
correctly (`"What is 2+2?"` → `"4"`).

### Serving benchmarks (measured on the DGX Spark GB10)

`experiments/benchmark_serving.py`, 16 sequential Socratic-tutoring requests, max_tokens=180,
concurrency=1, against `artifacts/socratic-nvfp4-final`:

| Profile | Aggregate tok/s | Decode tok/s (p50) | TTFT (p50) | Draft acceptance | Mean acceptance length |
|---|---|---|---|---|---|
| No speculative decoding | 12.55 | 12.72 | 0.167 s | — | — |
| + n-gram speculative decoding | 14.24 (+13.5%) | 13.25 | 0.105 s | **1.8%** | 1.09 |
| + MTP, num_speculative_tokens=1 | 18.22 (+45.2%) | 18.61 | 0.230 s | 74.1% | 1.74 |
| + **MTP, num_speculative_tokens=2** | **19.84 (+58.1%)** | **20.57** | — | **75.6%** | 2.51 |
| + MTP, num_speculative_tokens=3 | 18.98 (+51.2%) | 19.63 | — | 61.8% ↓ | 2.85 |

**Honest read:** the n-gram result is *not* a reliable win — n-gram speculation only pays off on
repetitive text (e.g. code), and its 1.8% draft-acceptance rate on free-form Socratic tutoring responses
means the +13.5% is most likely run-to-run noise, not a real effect. **MTP is a genuine, evidenced
speedup**: its ~74-76% acceptance rate (vs. n-gram's 1.8%) is because it's a head purpose-trained to
predict this exact model's own next tokens, not a generic pattern-matcher. The checkpoint's MTP head has
only **one physical draft layer** (`mtp_num_hidden_layers=1`); vLLM reuses it cyclically for
`num_speculative_tokens > 1` (drafting off its own prior draft). Empirically this **helps up to
`num_speculative_tokens=2`** (acceptance rate holds steady, throughput improves further) but **degrades at
3** (acceptance rate drops to 61.8%, confirmed by vLLM's own startup warning: *"Enabling
num_speculative_tokens > 1 will run multiple times of forward on same MTP layer, which may result in lower
acceptance rate"* — true, just one step later than the warning implies). **`num_speculative_tokens=2` is
the empirically-found optimum and the recommended default.** Sample size is 16 requests per config — the
exact crossover point could shift with more data, but the direction of the trend (degrading past 2 steps)
is mechanistically sound, not noise.

**Sanity check against hardware limits:** batch-1 decode is memory-bandwidth bound. GB10's published
unified-memory bandwidth (~273 GB/s) predicts a ceiling of 18.73 GiB ÷ 273 GB/s ≈ 69 ms/token ≈ 14.6 tok/s
for the plain (non-speculative) NVFP4 model — matching the measured 12.55–12.72 tok/s closely. This also
matches a separate earlier measurement of the unquantized bf16 Qwen3-32B on the same hardware class
(~3.6–3.8 tok/s, ~64 GiB weights): the ratio between the two (~3.4×) matches the ratio of bytes read per
token (~3.4×) almost exactly, confirming the NVFP4 speedup is a real bandwidth effect, not a fluke.

**Memory footprint:** floor is the weights themselves (18.73 GiB); everything above that is a tunable
`--gpu-memory-utilization` KV-cache reservation, not a hard requirement (verified working from 0.22 up to
0.8 utilization, ~27 GiB to ~90 GiB total). MTP's own CUDA-graph/draft overhead is small in isolation
(~0.6 GiB) but was seen to spike much higher (~30-47 GiB) when sharing the GPU with another concurrent
vLLM instance during A/B testing — budget generously if running more than one server at once.

### How to serve (recommended: MTP speculative decoding, num_speculative_tokens=2)

Plain vLLM, local checkpoint:

```bash
vllm serve artifacts/socratic-nvfp4-final \
  --trust-remote-code \
  --served-model-name spartan-teacher \
  --speculative-config '{"method":"mtp","num_speculative_tokens":2}' \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --per-request-spec-decode-metrics summary
```

Via **HP zrt** (pulls from the public HF repo, since zrt only accepts `hf:`/`azureml:`/`mlflow:` sources,
never local paths) — **verified working end-to-end**:

```bash
zrt stop --all   # clear any stale/dead service state first
MAX_JOBS=4 zrt serve hf:dhruv1672/spartan-studybuddy-qwen3.8-27b-nvfp4 \
  --label studybuddy-mtp \
  --gpu-memory-fraction 0.7 \
  --extra "--trust-remote-code" \
  --extra "--max-model-len=4096" \
  --extra '--speculative-config={"method":"mtp","num_speculative_tokens":2}' \
  --extra '--default-chat-template-kwargs={"enable_thinking": false}'
```

zrt has no dedicated speculative-decoding flag of its own — this works because `zrt serve` forwards
arbitrary vLLM flags verbatim via repeated `--extra` (or a bare `--` separator). **Always disable
"thinking" mode** (`enable_thinking: false`) for this checkpoint when serving for tool-calling/agent use
(e.g. Browser-Use) — see the JSON-validity gotcha below.

**zrt-specific gotchas** (zrt bundles an older vLLM/FlashInfer than the Docker image used for the
benchmarks above, so it must JIT-compile NVFP4 kernels from source on first use — a genuine one-time cost):
omit `--per-request-spec-decode-metrics` (not supported by zrt's bundled vLLM; cosmetic, not required);
set `MAX_JOBS=4` to avoid intermittent build failures from `ninja` over-parallelizing the CUDA kernel
compile; expect to retry `zrt stop --all` + `zrt serve` a few times on a cold machine — every stage caches
to disk permanently, so each retry gets further, and this is a **one-time cost per machine**, not a
recurring problem. See HANDOFF.md §6 for the full diagnosis.

**Cross-check: zrt vs. Docker vLLM, same model, same `num_speculative_tokens=2` config** — two
independent vLLM builds (zrt's 0.26.0 vs. the Docker image's 0.30.0):

| Metric | zrt | Docker |
|---|---|---|
| Aggregate tok/s | 19.43 | 19.84 |
| Decode tok/s (p50) | 20.74 | 20.57 |
| Decode tok/s (p95) | 22.73 | 23.71 |

Nearly identical despite the different vLLM versions and environments — strong corroborating evidence the
throughput numbers above are genuine and reproducible, not an artifact of one specific setup. One gap: zrt
doesn't expose the per-request `speculative_decoding` acceptance-rate field (same missing flag as above),
so this cross-check confirms matching *throughput*, not matching *acceptance rate*, directly.

**Two serving gotchas, both fixed by config, not by touching the checkpoint:**
- Qwen3-style "thinking" mode is on by default and breaks strict JSON output (e.g. `browser_use`'s tool
  schema) by prepending free-form reasoning text before the JSON. Fix: `--default-chat-template-kwargs
  '{"enable_thinking": false}'`, set server-side so every client gets it without needing its own change.
- For agentic/tool-calling use, prefer vLLM's constrained/guided JSON decoding over letting the model
  format tool-call JSON freely — verified directly: with free-form JSON the model reliably got nested
  action parameters wrong (e.g. `{"click": 21062}` instead of `{"click": {"index": 21062}}`); with guided
  decoding enforced, the same task succeeded in 3 clean steps, zero JSON errors.

### Known gaps / not yet done

- **EAGLE** speculative decoding is not applicable here without training a purpose-built draft head for
  this specific model — reusing the NVFP4 checkpoint as a "draft" for itself gives ~100% acceptance but
  zero speedup, since the draft costs exactly as much as the target it's meant to be cheaper than.
- Accuracy/perplexity eval on the held-out `test.jsonl` split (`training/nvfp4/eval_test_set.py`) for
  base vs. tuned vs. quantized has not been run yet.
- Not yet wired into the backend as `spartan-teacher` on `:8101` — currently only exercised on
  standalone benchmark ports.
- Model + model card: [`dhruv1672/spartan-studybuddy-qwen3.8-27b-nvfp4`](https://huggingface.co/dhruv1672/spartan-studybuddy-qwen3.8-27b-nvfp4)
  (public), including the MTP shard and both bugfixes above.

### Browser-Use on Linux, no separate Mac required

The Mac-only path above (`scripts/mac/...`) has a Linux equivalent at `scripts/linux/launch_studybuddy_chrome.sh`,
verified end-to-end on the DGX Spark itself over SSH (no physical display needed):

1. `sudo apt install -y chromium-browser xvfb` (one-time; needs a human to run it — not automatable).
2. `./scripts/linux/launch_studybuddy_chrome.sh` — starts a virtual display (`Xvfb`) and Chrome with a
   **persistent, non-hidden** profile dir (`~/spartan-studybuddy-chrome-profile`) and CDP on `:9222`.
   Gotcha: `chromium-browser` on Ubuntu resolves to the confined **snap** package, whose `home` interface
   confinement blocks writes to hidden dot-directories — the profile dir must be a visible path, not
   e.g. `~/.spartan-studybuddy/...`.
3. One-time login (Google/GitHub/Canvas/etc.), done by a human, not automatable: from your **local**
   machine, `ssh -L 9222:localhost:9222 <user>@<host>`, then in your own local Chrome open
   `chrome://inspect/#devices`, add `localhost:9222`, and log in via the live screencast. This uses
   Chrome's own remote-debugging inspector — no VNC or `ssh -X` needed.
4. Cookies/sessions persist in that profile dir permanently; every future `browser_use` run against
   `http://127.0.0.1:9222` reuses the authenticated session with zero re-login.

**Verified working end-to-end**, using our fine-tuned NVFP4 model (`enable_thinking: false`, guided JSON
decoding, `max_model_len=32768` — GitHub's page alone is 31-38K characters as DOM/accessibility-tree text,
far more than the 4096 tokens used for the speed benchmarks above): the agent correctly reported an
already-logged-in GitHub session without attempting to log in itself, and separately found and summarized
a specific repository from a live repo list purely by reading the page. `use_vision=False` (DOM/text mode)
throughout — no vision-capable model is required for this default `browser_use` path.

## Add a private GitHub repository

From the web UI paste an HTTPS/SSH GitHub URL, or call:

```bash
curl -X POST http://127.0.0.1:8000/api/sources/ingest \
  -H 'content-type: application/json' \
  -d '{"project_id":"PROJECT_ID","uri":"git@github.com:org/private-repo.git","kind":"github"}'
```

For HTTPS private repos set `GITHUB_TOKEN` in `.env` or pass a temporary `access_token` in the request. Tokens are not persisted by the source record.

## Google Drive

Paste a Drive/Docs/Slides/Sheets link into the Sources UI. Public/shared individual files can be imported directly where Google permits it. Private files and folder traversal require `GOOGLE_DRIVE_ACCESS_TOKEN` in `.env` or a temporary access token.

This is a token-based hackathon integration, not a production Google OAuth application.

## Browser-Use on the MacBook

```bash
./scripts/mac/setup_browser_use.sh
cp .env.mac.example .env.mac
# set STUDYBUDDY_API to the Spark URL
./scripts/mac/launch_studybuddy_chrome.sh
./scripts/mac/start_bridge.sh
```

The bridge attaches to the dedicated visible Chrome profile over CDP. Resource scouting is instructed to search only generic/public prerequisite concepts; private source code does not need to leave the Spark.

## Chrome extension

Run `make extensions-package`, unzip `dist/extensions/spartan-studybuddy-chrome.zip`, load that folder unpacked in Chrome, and set:

- DGX endpoint
- user ID
- learning-memory toggle

Then press **Refresh workspaces**, choose the project from the backend-provided workspace list, and save the connection. No project ID needs to be copied manually.

It records browser/resource progress and synchronizes it with the central memory. YouTube progress is based on the HTML video element; research-paper/web progress is based on active/visible page telemetry.

## VS Code extension

A lighter-weight companion to the Chrome extension — it has not had the same level of end-to-end testing this cycle, so treat it as a working prototype, not a polished surface. Prebuilt extension packages are generated by `make extensions-package` under `dist/extensions/`. Install `spartan-studybuddy-vscode.vsix` in VS Code, or open `apps/vscode-extension` and press `F5` for extension development. Configure:

- `spartan.api`
- `spartan.projectId`
- `spartan.userId`
- `spartan.authToken`
- `spartan.indexOnSave`

What it actually does today: a sidebar chat panel with **Connect to Workspace**, direct code Q&A, a Socratic hint mode, a plain-language explain mode, and full/on-save workspace indexing of supported file types. Each `ask` call sends the current selection (or a window of text around the cursor) and the active file's path as context — it does **not** currently send editor diagnostics/problems to the backend, despite what earlier documentation implied; that's dead code in `extension.js`, not a wired-up feature.

## Observability

```bash
./scripts/observability/start.sh
```

- StudyBuddy Prometheus metrics: `http://SPARK:8000/metrics`
- Grafana: `http://SPARK:3001`
- Prometheus: bound to localhost `:9090`
- Tempo/OTLP: bound to localhost

The app records model route, model name, retrieved evidence, latency, TTFT, token counts and TPS in the local `agent_traces` table. LangSmith export occurs only if `LANGSMITH_API_KEY` is explicitly configured.

## Tests

```bash
make test
```

The smoke suite starts a real `pgvector/pgvector` PostgreSQL container, initializes the schema, validates hybrid full-text + vector search, direct/Socratic routing, gamified progress and resume memory, validates both extension runtime contracts, and then runs JS/Python syntax checks.

## Current limitations

Read `COMPLETION_REPORT.md` before demo day. The repository is hackathon-grade, not production SaaS: authentication is demo-level, Drive/GitHub integrations are token based, multi-language code graphs are not yet full Tree-sitter/call-graph analysis, and the 32B fine-tune/speculative profiles still need to be executed and benchmarked on your physical DGX Spark. PostgreSQL + pgvector is now the only application database.
