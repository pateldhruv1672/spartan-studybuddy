#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && { set -a; source .env; set +a; }
docker exec spartan-studybuddy-postgres psql -U "${POSTGRES_USER:-studybuddy}" -d "${POSTGRES_DB:-studybuddy}" -Atc \
  "SELECT 'postgres='||current_setting('server_version')||' pgvector='||(SELECT extversion FROM pg_extension WHERE extname='vector')||' chunks='||(SELECT count(*) FROM indexed_chunks);" 2>/dev/null || {
  echo "PostgreSQL is not ready or the application schema has not been initialized yet." >&2; exit 1;
}
