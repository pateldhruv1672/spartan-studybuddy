#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || cp .env.example .env
set -a; source .env; set +a
command -v docker >/dev/null || { echo "Docker is required for PostgreSQL + pgvector." >&2; exit 1; }
docker compose -f deploy/postgres/docker-compose.yml up -d postgres
"$ROOT/scripts/db/wait.sh"
