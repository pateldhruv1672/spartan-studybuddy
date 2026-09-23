#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
echo "This removes the Spartan StudyBuddy PostgreSQL volume and ALL indexed knowledge/memory."
if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "Type RESET to continue: " answer
  [[ "$answer" == "RESET" ]] || exit 1
fi
docker compose -f deploy/postgres/docker-compose.yml down -v
"$ROOT/scripts/db/start.sh"
