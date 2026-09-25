#!/usr/bin/env bash
set -euo pipefail
PORT="${STUDYBUDDY_CHROME_DEBUG_PORT:-9222}"
PROFILE_DIR="${STUDYBUDDY_CHROME_DATA_DIR:-$HOME/.spartan-studybuddy/chrome-profile}"
CHROME="${STUDYBUDDY_CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
# Headless by default so browser-use research jobs don't pop a window in front of whatever the
# user is doing. Set STUDYBUDDY_CHROME_HEADLESS=0 to watch it work (useful for debugging).
HEADLESS="${STUDYBUDDY_CHROME_HEADLESS:-1}"

if [[ ! -x "$CHROME" ]]; then
  echo "Google Chrome not found at: $CHROME" >&2
  exit 1
fi
mkdir -p "$PROFILE_DIR"

if curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "StudyBuddy Chrome already exposes CDP on :$PORT"
  exit 0
fi

HEADLESS_FLAGS=()
if [[ "$HEADLESS" == "1" ]]; then
  HEADLESS_FLAGS=(--headless=new)
fi

"$CHROME" \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "${HEADLESS_FLAGS[@]}" \
  about:blank >/tmp/spartan-studybuddy-chrome.log 2>&1 &

echo "Started StudyBuddy Chrome (profile: $PROFILE_DIR, CDP: http://127.0.0.1:$PORT, headless: $HEADLESS)"
echo "Load the extension from apps/chrome-extension and sign in to Canvas/library once in this profile."
if [[ "$HEADLESS" == "1" ]]; then
  echo "Running headless -- no visible window. Set STUDYBUDDY_CHROME_HEADLESS=0 to watch it work instead."
fi
