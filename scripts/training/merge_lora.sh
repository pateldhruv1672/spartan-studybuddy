#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${STUDYBUDDY_TRAIN_IMAGE:-spartan-studybuddy-train:25.11}"
mkdir -p "$ROOT/artifacts" "${HF_HOME:-$HOME/.cache/huggingface}"
docker run --rm --gpus all --ipc host --ulimit memlock=-1 --ulimit stack=67108864 \
  -e HF_TOKEN="${HF_TOKEN:-}" -v "$ROOT:/workspace/spartan-studybuddy" \
  -v "${HF_HOME:-$HOME/.cache/huggingface}:/root/.cache/huggingface" "$IMAGE" \
  python3 training/merge_lora.py --base-model "${SOCRATIC_BASE_MODEL:-Qwen/Qwen3-32B}" \
  --adapter artifacts/socratic-lora --output-dir artifacts/socratic-merged
