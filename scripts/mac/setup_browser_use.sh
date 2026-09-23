#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  uv venv .bridge-venv --python 3.12
  uv pip install --python .bridge-venv/bin/python --upgrade browser-use httpx python-dotenv
else
  python3 -m venv .bridge-venv
  .bridge-venv/bin/python -m pip install --upgrade pip browser-use httpx python-dotenv
fi

cat <<'TXT'
Browser-Use bridge environment is ready.
Next:
  1. scripts/mac/launch_studybuddy_chrome.sh
  2. Load apps/chrome-extension in that Chrome profile.
  3. export STUDYBUDDY_API=http://<spark-ip>:8000
  4. scripts/mac/start_bridge.sh
TXT
