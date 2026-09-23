#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="$ROOT/runtime"
PIDS="$RUNTIME/pids"
LOGS="$RUNTIME/logs"
mkdir -p "$PIDS" "$LOGS"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

VLLM_API_KEY="${VLLM_API_KEY:-local-edge}"
VLLM_RUNTIME="${VLLM_RUNTIME:-docker}"
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:latest}"
VLLM_BIN="${VLLM_BIN:-vllm}"
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

pid_alive() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local pid
  pid="$(cat "$file" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_ready() {
  local port="$1"
  curl -fsS --max-time 2 -H "Authorization: Bearer $VLLM_API_KEY" "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
}

wait_ready() {
  local name="$1" port="$2" timeout="${3:-1200}"
  local start now
  start="$(date +%s)"
  printf 'Waiting for %s on :%s' "$name" "$port"
  while ! port_ready "$port"; do
    sleep 2
    printf '.'
    now="$(date +%s)"
    if (( now - start > timeout )); then
      echo
      if [[ "$VLLM_RUNTIME" == "docker" ]]; then
        echo "Timed out. Inspect: docker logs studybuddy-$name" >&2
      else
        echo "Timed out. Inspect: $LOGS/${name}.log" >&2
      fi
      return 1
    fi
  done
  echo " ready"
}

start_vllm_docker() {
  local name="$1" model="$2" port="$3" gpu_util="$4" max_len="$5"
  shift 5
  local cname="studybuddy-${name}"

  if ! have_cmd docker; then
    echo "Docker not found. DGX Spark default is containerized vLLM. Run scripts/models/install_vllm.sh." >&2
    return 1
  fi
  if docker ps --format '{{.Names}}' | grep -qx "$cname"; then
    echo "$cname container already running"
    wait_ready "$name" "$port"
    return 0
  fi
  if docker ps -a --format '{{.Names}}' | grep -qx "$cname"; then
    docker rm "$cname" >/dev/null
  fi

  mkdir -p "$HF_CACHE"
  local docker_model="$model"
  if [[ "$model" == "$ROOT"/* ]]; then
    docker_model="/workspace/spartan-studybuddy/${model#"$ROOT"/}"
  elif [[ "$model" == artifacts/* || "$model" == training/* ]]; then
    docker_model="/workspace/spartan-studybuddy/$model"
  fi
  echo "Starting $cname: $model -> 127.0.0.1:$port"
  docker run -d \
    --name "$cname" \
    --gpus all \
    --ipc host \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --entrypoint "" \
    -p "127.0.0.1:${port}:8000" \
    -e HF_TOKEN="${HF_TOKEN:-}" \
    -e HUGGING_FACE_HUB_TOKEN="${HF_TOKEN:-}" \
    -v "$HF_CACHE:/root/.cache/huggingface" \
    -v "$ROOT:/workspace/spartan-studybuddy:ro" \
    "$VLLM_IMAGE" \
    vllm serve "$docker_model" \
      --host 0.0.0.0 \
      --port 8000 \
      --api-key "$VLLM_API_KEY" \
      --dtype auto \
      --gpu-memory-utilization "$gpu_util" \
      --max-model-len "$max_len" \
      "$@" >/dev/null
  wait_ready "$name" "$port" "${MODEL_START_TIMEOUT:-1200}"
}

start_vllm_native() {
  local name="$1" model="$2" port="$3" gpu_util="$4" max_len="$5"
  shift 5
  local pidfile="$PIDS/${name}.pid" logfile="$LOGS/${name}.log"

  if port_ready "$port"; then
    echo "$name already healthy on :$port"
    return 0
  fi
  if pid_alive "$pidfile"; then
    echo "$name process already running (pid $(cat "$pidfile")); waiting for readiness"
    wait_ready "$name" "$port"
    return 0
  fi
  if ! have_cmd "$VLLM_BIN"; then
    echo "vLLM command not found. Set VLLM_RUNTIME=docker or install native vLLM." >&2
    return 1
  fi

  echo "Starting native $name: $model on 127.0.0.1:$port"
  nohup "$VLLM_BIN" serve "$model" \
    --host 127.0.0.1 \
    --port "$port" \
    --api-key "$VLLM_API_KEY" \
    --dtype auto \
    --gpu-memory-utilization "$gpu_util" \
    --max-model-len "$max_len" \
    "$@" >"$logfile" 2>&1 &
  echo $! > "$pidfile"
  wait_ready "$name" "$port" "${MODEL_START_TIMEOUT:-1200}"
}

start_vllm() {
  if [[ "$VLLM_RUNTIME" == "docker" ]]; then
    start_vllm_docker "$@"
  else
    start_vllm_native "$@"
  fi
}
