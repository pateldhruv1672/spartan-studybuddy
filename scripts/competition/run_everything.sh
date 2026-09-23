#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/training/train_all.sh"
"$ROOT/scripts/competition/run_benchmarks.sh"
echo
echo "Competition pipeline complete. Start the measured winner with: make start"
