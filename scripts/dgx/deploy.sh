#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

[[ -f .env ]] || cp .env.example .env
set -a; source .env; set +a

echo "[1/6] DGX/bootstrap dependencies"
"$ROOT/scripts/dgx/setup.sh"

echo "[2/6] PostgreSQL/pgvector + application integration gate"
"$ROOT/scripts/smoke_test.sh"

echo "[3/6] Packaging Chrome + VS Code extensions"
"$ROOT/scripts/extensions/package_all.sh"

echo "[4/6] Starting teacher + embedding models"
"$ROOT/scripts/models/start_demo_stack.sh"

echo "[5/6] Seeding demo organization/workspace with production embeddings"
. "$ROOT/.venv/bin/activate"
PYTHONPATH="$ROOT/backend" python3 "$ROOT/scripts/demo_seed.py"

echo "[6/6] Starting observability + StudyBuddy backend"
"$ROOT/scripts/observability/start.sh"
"$ROOT/scripts/dgx/start_stack.sh"

echo
echo "Deployment complete."
echo "StudyBuddy: http://$(hostname -I | awk '{print $1}'):${STUDYBUDDY_PORT:-8000}"
echo "Grafana:    http://$(hostname -I | awk '{print $1}'):3001"
echo "Extensions: $ROOT/dist/extensions/"
