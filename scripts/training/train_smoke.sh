#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOCRATIC_MAX_STEPS="${SOCRATIC_MAX_STEPS:-20}" \
SOCRATIC_MAX_LENGTH="${SOCRATIC_MAX_LENGTH:-1024}" \
LOCAL_DATA_MULTIPLIER="${LOCAL_DATA_MULTIPLIER:-4}" \
INCLUDE_HF_DATASETS="${INCLUDE_HF_DATASETS:-0}" \
"$ROOT/scripts/training/train_all.sh"
