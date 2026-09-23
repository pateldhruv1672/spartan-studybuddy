#!/usr/bin/env python3
"""Standalone accuracy/perplexity eval against the held-out, leak-free test.jsonl split.

Unlike training's periodic eval (loss only), this computes token-level accuracy
(argmax(logits) == label, on assistant-only tokens) and perplexity — run this
separately after training completes, against either the base model or a
base+adapter combination, without touching a live training process.

Usage:
    # Base model only
    python3 training/nvfp4/eval_test_set.py --model Qwen/Qwen3.8-27B \
        --test-file training/data_v2/test.jsonl --output experiments/results/base_test_eval.json

    # Base + LoRA adapter
    python3 training/nvfp4/eval_test_set.py --model Qwen/Qwen3.8-27B \
        --adapter artifacts/socratic-bf16-lora \
        --test-file training/data_v2/test.jsonl --output experiments/results/tuned_test_eval.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))
from chat_tokenize import IGNORE_TOKEN_ID, make_chat_tokenize_fn

import peft.tuners.lora.torchao as _peft_lora_torchao

_peft_lora_torchao.is_torchao_available = lambda: False


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="Base model path/name, or a merged checkpoint dir")
    p.add_argument(
        "--model-class",
        default="image-text-to-text",
        choices=["causal-lm", "image-text-to-text"],
    )
    p.add_argument("--adapter", default=None, help="Optional LoRA adapter dir to apply on top of --model")
    p.add_argument("--test-file", default="training/data_v2/test.jsonl")
    p.add_argument("--max-length", type=int, default=3072)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--output", required=True)
    return p.parse_args()


def main():
    args = parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available. Run inside the DGX Spark training container.")

    print(f"Loading model {args.model} (class={args.model_class})...")
    model_cls = AutoModelForImageTextToText if args.model_class == "image-text-to-text" else AutoModelForCausalLM
    model = model_cls.from_pretrained(args.model, dtype=torch.bfloat16, trust_remote_code=True, device_map={"": 0})
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    if args.adapter:
        from peft import PeftModel

        print(f"Applying LoRA adapter from {args.adapter}...")
        model = PeftModel.from_pretrained(model, args.adapter)

    model.eval()

    tokenize_fn = make_chat_tokenize_fn(tokenizer, args.max_length)
    ds = load_dataset("json", data_files={"test": args.test_file})["test"]
    ds = ds.map(tokenize_fn, remove_columns=list(ds.features), desc="Tokenizing test set")
    ds = ds.filter(lambda x: any(t != IGNORE_TOKEN_ID for t in x["labels"]))
    print(f"test examples: {len(ds)}")

    total_loss_sum = 0.0
    total_scored_tokens = 0
    total_correct = 0

    with torch.no_grad():
        for i in range(0, len(ds), args.batch_size):
            batch = ds[i : i + args.batch_size]
            input_ids = torch.tensor(batch["input_ids"]).to(model.device)
            attention_mask = torch.tensor(batch["attention_mask"]).to(model.device)
            labels = torch.tensor(batch["labels"]).to(model.device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits[:, :-1, :]
            shift_labels = labels[:, 1:]

            mask = shift_labels != IGNORE_TOKEN_ID
            n_scored = mask.sum().item()
            if n_scored == 0:
                continue

            loss = torch.nn.functional.cross_entropy(
                logits[mask], shift_labels[mask], reduction="sum"
            )
            preds = logits[mask].argmax(dim=-1)
            correct = (preds == shift_labels[mask]).sum().item()

            total_loss_sum += loss.item()
            total_scored_tokens += n_scored
            total_correct += correct

            if (i // args.batch_size) % 50 == 0:
                print(f"  {i}/{len(ds)} examples processed...")

    mean_loss = total_loss_sum / total_scored_tokens
    perplexity = float(torch.exp(torch.tensor(mean_loss)))
    token_accuracy = total_correct / total_scored_tokens

    result = {
        "model": args.model,
        "adapter": args.adapter,
        "test_file": args.test_file,
        "test_examples": len(ds),
        "scored_tokens": total_scored_tokens,
        "test_loss": mean_loss,
        "test_perplexity": perplexity,
        "test_token_accuracy": token_accuracy,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
