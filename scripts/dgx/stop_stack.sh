#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
"$ROOT/scripts/models/stop_models.sh" || true
pidfile="$ROOT/runtime/pids/backend.pid"
if [[ -f "$pidfile" ]]; then pid="$(cat "$pidfile" 2>/dev/null || true)"; [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true; rm -f "$pidfile"; fi
