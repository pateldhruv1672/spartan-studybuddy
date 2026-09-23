#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
RUNTIME="${VLLM_RUNTIME:-docker}"
IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:latest}"

if [[ "$RUNTIME" == "docker" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for the recommended DGX Spark path." >&2
    exit 1
  fi
  if ! docker ps >/dev/null 2>&1; then
    cat >&2 <<'TXT'
Docker exists but is not usable by this user.
On DGX Spark, NVIDIA recommends enabling non-sudo Docker access:
  sudo usermod -aG docker $USER
  newgrp docker
Then rerun this script.
TXT
    exit 1
  fi
  echo "Checking NVIDIA GPU access through Docker..."
  if ! docker info 2>/dev/null | grep -qi 'runtimes'; then
    echo "Warning: could not verify NVIDIA Container Toolkit from docker info." >&2
  fi
  echo "Pulling $IMAGE"
  docker pull "$IMAGE"
  echo "Containerized vLLM ready. Set HF_TOKEN if you use gated models."
else
  echo "Installing native vLLM (non-default on DGX Spark)..."
  python3 -m pip install --upgrade pip
  python3 -m pip install --upgrade 'vllm>=0.12.0' huggingface_hub openai
  echo "vLLM installed: $(vllm --version 2>/dev/null || true)"
fi
