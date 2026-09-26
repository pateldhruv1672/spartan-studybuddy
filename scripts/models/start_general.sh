#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

BASE_MODEL="${SOCRATIC_BASE_MODEL:-Qwen/Qwen3-32B}"
TUNED_DIR="${SOCRATIC_MERGED_DIR:-$ROOT/artifacts/socratic-merged}"
MODEL="$BASE_MODEL"; PROFILE="base"
if [[ "${USE_TUNED_SOCRATIC_MODEL:-1}" == "1" && -f "$TUNED_DIR/config.json" ]]; then MODEL="$TUNED_DIR"; PROFILE="tuned"; fi
PORT="${GENERAL_PORT:-8101}"
GPU_UTIL="${GENERAL_GPU_UTIL:-0.72}"
MAX_LEN="${GENERAL_MAX_MODEL_LEN:-32768}"
SPECULATION_METHOD="${SPECULATION_METHOD:-none}"
EXTRA=(
  --reasoning-parser qwen3
  --default-chat-template-kwargs '{"enable_thinking": false}'
  --max-num-seqs "${GENERAL_MAX_NUM_SEQS:-8}"
  --enable-prefix-caching
  --enable-chunked-prefill
  --max-num-batched-tokens "${GENERAL_MAX_BATCHED_TOKENS:-8192}"
  --served-model-name "${GENERAL_SERVED_MODEL_NAME:-spartan-teacher}"
)
# Fixed KV budget skips vLLM's free-memory profiling assertion on DGX Spark
# unified memory; set GENERAL_KV_CACHE_BYTES= (empty) to use GENERAL_GPU_UTIL sizing.
GENERAL_KV_CACHE_BYTES="${GENERAL_KV_CACHE_BYTES-16G}"
if [[ -n "$GENERAL_KV_CACHE_BYTES" ]]; then EXTRA+=(--kv-cache-memory-bytes "$GENERAL_KV_CACHE_BYTES"); fi
if [[ "$PROFILE" == "tuned" ]]; then
  case "$SPECULATION_METHOD" in
    ngram)
      EXTRA+=(--speculative-config "{\"method\":\"ngram\",\"num_speculative_tokens\":${NGRAM_SPEC_TOKENS:-5},\"prompt_lookup_min\":1,\"prompt_lookup_max\":${NGRAM_PROMPT_LOOKUP_MAX:-4}}")
      EXTRA+=(--per-request-spec-decode-metrics summary) ;;
    eagle3)
      EXTRA+=(--speculative-config "{\"model\":\"${EAGLE3_SPECULATOR_MODEL:-RedHatAI/Qwen3-32B-speculator.eagle3}\",\"num_speculative_tokens\":${EAGLE3_SPEC_TOKENS:-3},\"method\":\"eagle3\"}")
      EXTRA+=(--per-request-spec-decode-metrics summary) ;;
    none) ;;
    *) echo "Unknown SPECULATION_METHOD=$SPECULATION_METHOD" >&2; exit 2 ;;
  esac
fi

echo "StudyBuddy teacher: $PROFILE | $MODEL | speculation=$([[ $PROFILE == tuned ]] && echo "$SPECULATION_METHOD" || echo none)"
start_vllm general "$MODEL" "$PORT" "$GPU_UTIL" "$MAX_LEN" "${EXTRA[@]}"
