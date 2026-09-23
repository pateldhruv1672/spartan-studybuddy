#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
"$ROOT/scripts/models/start_general.sh"
"$ROOT/scripts/models/start_embeddings.sh"
if [[ "${START_DEDICATED_BROWSER_MODEL:-0}" == "1" ]]; then
  echo "WARNING: starting a second ~30B browser model. Ensure enough unified memory is available."
  "$ROOT/scripts/models/start_browser.sh"
fi
echo
echo "Spartan StudyBuddy model stack is ready."
echo "  Teacher:    http://127.0.0.1:${GENERAL_PORT:-8101}/v1"
echo "  Embeddings: http://127.0.0.1:${EMBEDDING_PORT:-8105}/v1"
echo "  Browser-Use default: reuses teacher through the authenticated StudyBuddy proxy."
