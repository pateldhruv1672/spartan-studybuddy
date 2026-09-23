#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${SOCRATIC_MERGED_DIR:-$ROOT/artifacts/socratic-merged}"
[[ -f "$MODEL/config.json" ]] || { echo "Missing merged model at $MODEL. Run make train first." >&2; exit 1; }
start_vllm bench-tuned "$MODEL" "${BENCH_PORT:-8201}" "${BENCH_GPU_UTIL:-0.72}" "${BENCH_MAX_MODEL_LEN:-4096}" \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' \
  --max-num-seqs "${BENCH_MAX_NUM_SEQS:-8}" \
  --enable-prefix-caching --enable-chunked-prefill --max-num-batched-tokens "${BENCH_MAX_BATCHED_TOKENS:-8192}" --served-model-name studybuddy-socratic
