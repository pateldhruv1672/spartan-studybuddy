#!/usr/bin/env bash
# Post-training pipeline: merge LoRA -> NVFP4 quantize -> export a vLLM-servable checkpoint.
# Run once training/nvfp4/train_bf16_lora.py has completed and saved its final adapter to
# artifacts/socratic-bf16-lora. Uses distinct output dirs so nothing existing gets overwritten.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ADAPTER_DIR="${1:-artifacts/socratic-bf16-lora}"
BASE_MODEL="${2:-Qwen/Qwen3.8-27B}"

echo "=== 1/3: Merging LoRA adapter into base bf16 weights ==="
python3 training/nvfp4/merge_bf16_lora.py \
  --base-model "$BASE_MODEL" \
  --adapter "$ADAPTER_DIR" \
  --output-dir artifacts/socratic-bf16-merged-final

echo "=== 2/3: NVFP4 PTQ + compression of the merged model ==="
python3 training/nvfp4/quantize.py \
  --model artifacts/socratic-bf16-merged-final \
  --train-file training/data_v2/train.jsonl \
  --output-dir artifacts/socratic-nvfp4-quantized-final \
  --calib-size 512 --max-length 3072

echo "=== 3/3: Exporting a clean, vLLM-servable NVFP4 checkpoint ==="
python3 training/nvfp4/export_nvfp4.py \
  --pyt-ckpt-path artifacts/socratic-nvfp4-quantized-final \
  --export-path artifacts/socratic-nvfp4-final

echo
echo "Done. Servable checkpoint at: artifacts/socratic-nvfp4-final"
echo "Serve with, e.g.:"
echo "  vllm serve artifacts/socratic-nvfp4-final --served-model-name studybuddy-socratic-final \\"
echo "    --speculative-config '{\"method\":\"eagle3\",\"model\":\"...\"}' # or MTP config for qwen3_5"
