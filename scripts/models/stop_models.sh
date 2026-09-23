#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Stop StudyBuddy-owned containers if present.
if command -v docker >/dev/null 2>&1; then
  mapfile -t containers < <(docker ps -a --format '{{.Names}}' 2>/dev/null | grep '^studybuddy-' || true)
  for name in "${containers[@]}"; do
    [[ -n "$name" ]] || continue
    echo "Stopping/removing $name"
    docker rm -f "$name" >/dev/null || true
  done
fi

# Also stop native-mode processes if used.
shopt -s nullglob
for pidfile in "$ROOT"/runtime/pids/*.pid; do
  name="$(basename "$pidfile" .pid)"
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "Stopping native $name (pid $pid)"
    kill "$pid" || true
  fi
  rm -f "$pidfile"
done
