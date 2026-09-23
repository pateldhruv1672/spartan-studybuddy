#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/models/stop_models.sh" || true
[[ "${SKIP_TRAIN_IMAGE_BUILD:-0}" == "1" ]] || "$ROOT/scripts/training/build_image.sh"
"$ROOT/scripts/training/prepare_dataset.sh"
"$ROOT/scripts/training/train_lora.sh"
"$ROOT/scripts/training/merge_lora.sh"
echo
echo "Socratic model ready: $ROOT/artifacts/socratic-merged"
