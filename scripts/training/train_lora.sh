#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${STUDYBUDDY_TRAIN_IMAGE:-spartan-studybuddy-train:25.11}"
MODEL="${SOCRATIC_BASE_MODEL:-Qwen/Qwen3-32B}"
QUANT="${SOCRATIC_QUANTIZATION:-none}"
mkdir -p "$ROOT/artifacts" "${HF_HOME:-$HOME/.cache/huggingface}"
echo "Training Spartan Teacher LoRA on $MODEL"
echo "max_steps=${SOCRATIC_MAX_STEPS:-300} max_length=${SOCRATIC_MAX_LENGTH:-3072} quantization=$QUANT"
docker run --rm --gpus all --ipc host --ulimit memlock=-1 --ulimit stack=67108864 \
  -e HF_TOKEN="${HF_TOKEN:-}" -e HUGGING_FACE_HUB_TOKEN="${HF_TOKEN:-}" -e RESUME_TRAINING="${RESUME_TRAINING:-1}" \
  -v "$ROOT:/workspace/spartan-studybuddy" \
  -v "${HF_HOME:-$HOME/.cache/huggingface}:/root/.cache/huggingface" \
  "$IMAGE" python3 training/train_socratic.py \
    --model "$MODEL" --train-file training/data/train.jsonl --eval-file training/data/validation.jsonl \
    --output-dir artifacts/socratic-lora --epochs "${SOCRATIC_EPOCHS:-1}" --max-steps "${SOCRATIC_MAX_STEPS:-300}" \
    --learning-rate "${SOCRATIC_LR:-0.0001}" --max-length "${SOCRATIC_MAX_LENGTH:-3072}" \
    --grad-accum "${SOCRATIC_GRAD_ACCUM:-8}" --lora-r "${SOCRATIC_LORA_R:-32}" --lora-alpha "${SOCRATIC_LORA_ALPHA:-64}" \
    --quantization "$QUANT"
