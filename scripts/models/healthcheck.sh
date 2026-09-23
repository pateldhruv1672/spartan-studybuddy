#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
check(){ local label="$1" port="$2"; if port_ready "$port"; then echo "OK   $label :$port"; else echo "DOWN $label :$port"; return 1; fi; }
fail=0
check teacher "${GENERAL_PORT:-8101}" || fail=1
check embeddings "${EMBEDDING_PORT:-8105}" || fail=1
if [[ "${START_DEDICATED_BROWSER_MODEL:-0}" == "1" ]]; then check browser "${BROWSER_PORT:-8104}" || fail=1; fi
exit "$fail"
