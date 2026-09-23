#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${STUDYBUDDY_TRAIN_IMAGE:-spartan-studybuddy-train:25.11}"
docker build -t "$IMAGE" -f "$ROOT/training/Dockerfile.spark" "$ROOT"
echo "Built $IMAGE"
