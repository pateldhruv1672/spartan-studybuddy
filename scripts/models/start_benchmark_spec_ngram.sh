#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${SOCRATIC_MERGED_DIR:-$ROOT/artifacts/socratic-merged}"
[[ -f "$MODEL/config.json" ]] || { echo "Missing merged model at $MODEL. Run make train first." >&2; exit 1; }
start_vllm bench-spec-ngram "$MODEL" "${BENCH_PORT:-8202}" "${BENCH_GPU_UTIL:-0.78}" "${BENCH_MAX_MODEL_LEN:-4096}" \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' \
  --max-num-seqs "${BENCH_MAX_NUM_SEQS:-8}" \
  --enable-prefix-caching --enable-chunked-prefill --max-num-batched-tokens "${BENCH_MAX_BATCHED_TOKENS:-8192}" --served-model-name studybuddy-socratic-spec-ngram \
  --speculative-config "{\"method\":\"ngram\",\"num_speculative_tokens\":${NGRAM_SPEC_TOKENS:-5},\"prompt_lookup_min\":1,\"prompt_lookup_max\":${NGRAM_PROMPT_LOOKUP_MAX:-4}}" \
  --per-request-spec-decode-metrics summary
