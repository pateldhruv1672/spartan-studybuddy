#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${SOCRATIC_MERGED_DIR:-$ROOT/artifacts/socratic-merged}"
[[ -f "$MODEL/config.json" ]] || { echo "Missing merged model at $MODEL. Run make train first." >&2; exit 1; }
start_vllm bench-spec-eagle3 "$MODEL" "${BENCH_PORT:-8203}" "${BENCH_GPU_UTIL:-0.82}" "${BENCH_MAX_MODEL_LEN:-4096}" \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' \
  --max-num-seqs "${BENCH_MAX_NUM_SEQS:-8}" \
  --enable-prefix-caching --enable-chunked-prefill --max-num-batched-tokens "${BENCH_MAX_BATCHED_TOKENS:-8192}" --served-model-name studybuddy-socratic-spec-eagle3 \
  --speculative-config "{\"model\":\"${EAGLE3_SPECULATOR_MODEL:-RedHatAI/Qwen3-32B-speculator.eagle3}\",\"num_speculative_tokens\":${EAGLE3_SPEC_TOKENS:-3},\"method\":\"eagle3\"}" \
  --per-request-spec-decode-metrics summary
