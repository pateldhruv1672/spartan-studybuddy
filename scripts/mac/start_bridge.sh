#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env.mac" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.mac"
  set +a
fi

export STUDYBUDDY_API="${STUDYBUDDY_API:-${1:-http://127.0.0.1:8001}}"
export STUDYBUDDY_CDP_URL="${STUDYBUDDY_CDP_URL:-http://localhost:9222}"
export STUDYBUDDY_BROWSER_PROVIDER="${STUDYBUDDY_BROWSER_PROVIDER:-vllm-proxy}"
export STUDYBUDDY_BROWSER_MODEL="${STUDYBUDDY_BROWSER_MODEL:-spartan-teacher}"

PY="$ROOT/.bridge-venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Bridge virtualenv missing. Run scripts/mac/setup_browser_use.sh first." >&2
  exit 1
fi

exec "$PY" bridges/mac_bridge.py
