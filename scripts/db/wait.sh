#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && { set -a; source .env; set +a; }
for _ in $(seq 1 60); do
  if docker exec spartan-studybuddy-postgres pg_isready -U "${POSTGRES_USER:-studybuddy}" -d "${POSTGRES_DB:-studybuddy}" >/dev/null 2>&1; then
    docker exec spartan-studybuddy-postgres psql -U "${POSTGRES_USER:-studybuddy}" -d "${POSTGRES_DB:-studybuddy}" -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;' >/dev/null
    echo "PostgreSQL + pgvector ready on 127.0.0.1:${POSTGRES_PORT:-5432}."
    exit 0
  fi
  sleep 2
done
echo "PostgreSQL did not become healthy. Run: docker logs spartan-studybuddy-postgres" >&2
exit 1
