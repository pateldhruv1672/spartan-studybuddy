#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
cd "$ROOT/deploy/observability"
docker compose up -d
echo "Grafana: http://$(hostname -I | awk '{print $1}'):3001 (${GRAFANA_USER:-admin}/configured password)"
echo "Prometheus: http://127.0.0.1:9090"
echo "Tempo/OTLP HTTP: http://127.0.0.1:4318"
