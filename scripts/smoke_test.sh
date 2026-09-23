#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] || cp .env.example .env
set -a; source .env; set +a

# Integration tests are intentionally executed against the real PostgreSQL + pgvector
# container. There is no SQLite test fallback, so passing this command proves the same
# persistence/retrieval path used by the demo.
if command -v docker >/dev/null 2>&1; then
  "$ROOT/scripts/db/start.sh"
else
  echo "Docker is required for the PostgreSQL integration suite." >&2
  exit 1
fi

OTEL_SDK_DISABLED=true ALLOW_EMBEDDING_FALLBACK=1 PYTHONPATH="$ROOT/backend" pytest -q tests/test_extractors.py tests/test_system.py
"$ROOT/scripts/extensions/test_all.sh"
node --check apps/web/app.js
python3 -m py_compile bridges/mac_bridge.py bridges/computer_use_executor.py
python3 -m py_compile $(find backend training experiments scripts -name '*.py' -type f | tr '\n' ' ')

# Verify the backend initialized the pgvector schema during TestClient lifespan.
docker exec spartan-studybuddy-postgres psql -U "${POSTGRES_USER:-studybuddy}" -d "${POSTGRES_DB:-studybuddy}" -v ON_ERROR_STOP=1 -Atc \
  "SELECT CASE WHEN EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')
               AND EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='indexed_chunks' AND column_name='embedding')
          THEN 'pgvector-schema-ok' ELSE 'missing' END;" | grep -qx 'pgvector-schema-ok'
printf '\nAll Spartan StudyBuddy PostgreSQL + extension smoke checks passed.\n'
