#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
MODEL="${EMBEDDING_MODEL:-Qwen/Qwen3-Embedding-0.6B}"
PORT="${EMBEDDING_PORT:-8105}"
GPU_UTIL="${EMBEDDING_GPU_UTIL:-0.055}"
MAX_LEN="${EMBEDDING_MAX_MODEL_LEN:-8192}"
# Fixed KV budget skips vLLM's free-memory profiling, which asserts on DGX Spark
# unified memory when other processes allocate/release memory during startup.
KV_BYTES="${EMBEDDING_KV_CACHE_BYTES:-2G}"
start_vllm embeddings "$MODEL" "$PORT" "$GPU_UTIL" "$MAX_LEN" \
  --runner pooling \
  --kv-cache-memory-bytes "$KV_BYTES" \
  --served-model-name "$MODEL"
