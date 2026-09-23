#!/usr/bin/env bash
set -euo pipefail
name="${1:?usage: stop_one.sh <profile-name>}"
if command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}}' | grep -qx "studybuddy-$name"; then
  docker rm -f "studybuddy-$name" >/dev/null
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
pidfile="$ROOT/runtime/pids/$name.pid"
if [[ -f "$pidfile" ]]; then
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$pidfile"
fi
