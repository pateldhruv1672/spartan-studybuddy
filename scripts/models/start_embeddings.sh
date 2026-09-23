#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${EMBEDDING_MODEL:-Qwen/Qwen3-Embedding-0.6B}"
PORT="${EMBEDDING_PORT:-8105}"
GPU_UTIL="${EMBEDDING_GPU_UTIL:-0.055}"
MAX_LEN="${EMBEDDING_MAX_MODEL_LEN:-8192}"
start_vllm embeddings "$MODEL" "$PORT" "$GPU_UTIL" "$MAX_LEN" \
  --runner pooling \
  --served-model-name "$MODEL"
