#!/usr/bin/env bash
set -euo pipefail
MODEL="${OLLAMA_BROWSER_MODEL:-llama3.1:8b}"
if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama not found. Install it first from https://ollama.com/" >&2
  exit 1
fi

# For safest local use keep Ollama bound to loopback. To use Browser Use's
# native ChatOllama from a different Mac, set OLLAMA_HOST=0.0.0.0:11434 and
# restrict the port to your private LAN/Tailscale firewall.
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
(ollama serve > /tmp/spartan-studybuddy-ollama.log 2>&1 & echo $! > /tmp/spartan-studybuddy-ollama.pid) || true
sleep 2
ollama pull "$MODEL"
echo "Ollama ready with $MODEL at http://$OLLAMA_HOST"
