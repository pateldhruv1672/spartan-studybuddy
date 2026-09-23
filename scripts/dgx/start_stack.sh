#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/db/start.sh"
if [[ -f experiments/results/recommended_serving.env ]]; then
  set -a; source experiments/results/recommended_serving.env; set +a
fi
"$ROOT/scripts/models/start_demo_stack.sh"
if [[ -f runtime/pids/backend.pid ]] && kill -0 "$(cat runtime/pids/backend.pid)" 2>/dev/null; then
  echo "Backend already running (pid $(cat runtime/pids/backend.pid))"
else
  if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
  nohup "$PY" backend/run.py > runtime/logs/backend.log 2>&1 &
  echo $! > runtime/pids/backend.pid
fi
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:${STUDYBUDDY_PORT:-8000}/api/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:${STUDYBUDDY_PORT:-8000}/api/health || { echo "Backend failed. See runtime/logs/backend.log" >&2; exit 1; }
echo
echo "Spartan StudyBuddy is running."
echo "Web/API: http://$(hostname -I | awk '{print $1}'):${STUDYBUDDY_PORT:-8000}"
echo "Model:   spartan-teacher (base fallback or fine-tuned model if artifacts/socratic-merged exists)"
