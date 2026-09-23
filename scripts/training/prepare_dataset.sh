#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
ARGS=(--output-dir training/data --local-multiplier "${LOCAL_DATA_MULTIPLIER:-18}")
if [[ "${INCLUDE_HF_DATASETS:-1}" == "1" ]]; then ARGS+=(--include-hf --socrateach-samples "${SOCRATEACH_SAMPLES:-8000}" --pact-samples "${PACT_SAMPLES:-2000}"); fi
if python3 -c 'import datasets' >/dev/null 2>&1; then
  python3 training/prepare_socratic_dataset.py "${ARGS[@]}"
else
  echo "Host lacks datasets; preparing inside the DGX training image."
  IMAGE="${STUDYBUDDY_TRAIN_IMAGE:-spartan-studybuddy-train:25.11}"
  docker run --rm -e HF_TOKEN="${HF_TOKEN:-}" -e HUGGING_FACE_HUB_TOKEN="${HF_TOKEN:-}" \
    -v "$ROOT:/workspace/spartan-studybuddy" -v "${HF_HOME:-$HOME/.cache/huggingface}:/root/.cache/huggingface" "$IMAGE" \
    python3 training/prepare_socratic_dataset.py "${ARGS[@]}"
fi
