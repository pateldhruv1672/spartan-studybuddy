#!/usr/bin/env bash
set -euo pipefail
# Optional dedicated Browser-Use model. The default deployment reuses the teacher model.
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${DEDICATED_BROWSER_MODEL:-browser-use/bu-30b-a3b-preview}"
PORT="${BROWSER_PORT:-8104}"
GPU_UTIL="${BROWSER_GPU_UTIL:-0.58}"
MAX_LEN="${BROWSER_MAX_MODEL_LEN:-32768}"
start_vllm browser "$MODEL" "$PORT" "$GPU_UTIL" "$MAX_LEN" \
  --max-num-seqs "${BROWSER_MAX_NUM_SEQS:-2}" \
  --limit-mm-per-prompt '{"image": 4}' \
  --served-model-name "$MODEL"
