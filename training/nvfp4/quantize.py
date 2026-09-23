#!/usr/bin/env python3
"""PTQ + real-compression step for NVFP4 QLoRA, adapted from NVIDIA TensorRT-Model-Optimizer's
examples/llm_qat/quantize.py for Spartan StudyBuddy's local JSONL Socratic dataset.

Usage:
    python3 training/nvfp4/quantize.py \
        --model Qwen/Qwen3-32B \
        --train-file training/data_v2/train.jsonl \
        --output-dir artifacts/socratic-nvfp4-quantized \
        --calib-size 512 --max-length 3072
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer, default_data_collator

sys.path.insert(0, str(Path(__file__).parent))
from chat_tokenize import make_chat_tokenize_fn

import modelopt.torch.opt as mto
import modelopt.torch.quantization as mtq

mto.enable_huggingface_checkpointing()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument(
        "--model-class",
        default="image-text-to-text",
        choices=["causal-lm", "image-text-to-text"],
        help="Qwen3.8-27B is published as a VLM checkpoint (Qwen3_5ForConditionalGeneration); "
        "load it via AutoModelForImageTextToText even for text-only use. Use causal-lm for "
        "plain dense models like Qwen3-32B.",
    )
    p.add_argument("--train-file", default="training/data_v2/train.jsonl")
    p.add_argument("--output-dir", default="artifacts/socratic-nvfp4-quantized")
    p.add_argument("--calib-size", type=int, default=512)
    p.add_argument("--calib-batch-size", type=int, default=1)
    p.add_argument("--max-length", type=int, default=3072)
    return p.parse_args()


def main():
    args = parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available. Run inside the DGX Spark training container.")

    print(f"Loading base model {args.model} (bf16, class={args.model_class})...")
    model_cls = AutoModelForImageTextToText if args.model_class == "image-text-to-text" else AutoModelForCausalLM
    model = model_cls.from_pretrained(
        args.model, dtype=torch.bfloat16, trust_remote_code=True, device_map={"": 0}
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print(f"Loading calibration data from {args.train_file} (first {args.calib_size} rows)...")
    ds = load_dataset("json", data_files={"train": args.train_file})["train"]
    ds = ds.select(range(min(args.calib_size, len(ds))))
    tokenize_fn = make_chat_tokenize_fn(tokenizer, args.max_length)
    tokenized = ds.map(tokenize_fn, remove_columns=list(ds.features), desc="Tokenizing calibration set")
    tokenized = tokenized.filter(lambda x: any(t != -100 for t in x["labels"]))
    print(f"Calibration set: {len(tokenized)} rows (after dropping empty-label rows)")

    calib_loader = torch.utils.data.DataLoader(
        tokenized, batch_size=args.calib_batch_size, collate_fn=default_data_collator
    )

    def forward_loop(m):
        for batch in tqdm(calib_loader, desc="Calibrating"):
            batch = {k: v.to(m.device) for k, v in batch.items()}
            m(**batch)

    print("Quantizing to NVFP4 (weights + activations, default recipe)...")
    mtq.quantize(model, mtq.NVFP4_DEFAULT_CFG, forward_loop)
    mtq.print_quant_summary(model)

    print("Compressing weights for real QLoRA memory savings...")
    mtq.compress(model)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Saving quantized checkpoint to {out}...")
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    print("Done.")


if __name__ == "__main__":
    main()
