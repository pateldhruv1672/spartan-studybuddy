#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="$ROOT/dist/extensions"; rm -rf "$OUT"; mkdir -p "$OUT"
( cd apps/chrome-extension && zip -qr "$OUT/spartan-studybuddy-chrome.zip" . )
python3 "$ROOT/scripts/extensions/make_vsix.py"
echo "Extension packages:"
ls -lh "$OUT"
