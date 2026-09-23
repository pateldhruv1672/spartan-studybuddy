#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
command -v docker >/dev/null || { echo "Docker is required on DGX Spark." >&2; exit 1; }
command -v nvidia-smi >/dev/null || { echo "nvidia-smi not found; run on DGX Spark." >&2; exit 1; }
nvidia-smi >/dev/null
[[ -f .env ]] || cp .env.example .env
"$ROOT/scripts/db/start.sh"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
"$ROOT/scripts/models/install_vllm.sh"
"$ROOT/scripts/training/build_image.sh"
python3 training/prepare_socratic_dataset.py --output-dir training/data --local-multiplier 10
mkdir -p runtime/logs runtime/pids artifacts experiments/results data
echo "DGX setup complete. For external datasets set INCLUDE_HF_DATASETS=1 and run make dataset."
