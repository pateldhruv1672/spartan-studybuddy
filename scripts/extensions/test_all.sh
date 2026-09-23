#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
node --check apps/chrome-extension/service-worker.js
node --check apps/chrome-extension/content.js
node --check apps/chrome-extension/popup.js
node --check apps/vscode-extension/extension.js
python3 tests/validate_chrome_manifest.py
node tests/validate_chrome_service_worker.js
node tests/validate_chrome_content.js
node tests/validate_vscode_extension.js
printf '\nExtension validation passed.\n'
