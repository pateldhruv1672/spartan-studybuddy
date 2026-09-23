#!/usr/bin/env bash
set -euo pipefail
# Optional third server. The default demo profile reuses BU-30B as the VLM.
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${VLLM_VLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct}"
PORT="${VLM_PORT:-8103}"
GPU_UTIL="${VLM_GPU_UTIL:-0.18}"
MAX_LEN="${VLM_MAX_MODEL_LEN:-16384}"

start_vllm vlm "$MODEL" "$PORT" "$GPU_UTIL" "$MAX_LEN" \
  --max-num-seqs "${VLM_MAX_NUM_SEQS:-2}" \
  --limit-mm-per-prompt '{"image": 4}'
