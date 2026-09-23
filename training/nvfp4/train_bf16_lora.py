#!/usr/bin/env python3
"""bf16 LoRA fine-tuning for Qwen3.8-27B (qwen3_5 architecture). Trains at full bf16 speed
(no NVFP4 dequant-fallback bottleneck), producing an adapter that gets merged and then
quantized to NVFP4 for serving via nvfp4/quantize.py + merge_lora.py.

Usage:
    python3 training/nvfp4/train_bf16_lora.py \
        --model Qwen/Qwen3.8-27B \
        --train-file training/data_v2/train.jsonl \
        --eval-file training/data_v2/validation.jsonl \
        --output-dir artifacts/socratic-bf16-lora \
        --max-steps 600 --num-layers 64 --last-n-layers 16
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoModelForImageTextToText,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
    default_data_collator,
)

sys.path.insert(0, str(Path(__file__).parent))
from chat_tokenize import make_chat_tokenize_fn

# This container's torchao build is incompatible with peft's dispatch_torchao() version gate,
# which hard-raises ImportError instead of returning False. We never use torchao-quantized
# layers here, so the check is irrelevant — neutralize it.
import peft.tuners.lora.torchao as _peft_lora_torchao

_peft_lora_torchao.is_torchao_available = lambda: False


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument(
        "--model-class",
        default="image-text-to-text",
        choices=["causal-lm", "image-text-to-text"],
    )
    p.add_argument("--train-file", default="training/data_v2/train.jsonl")
    p.add_argument("--eval-file", default="training/data_v2/validation.jsonl")
    p.add_argument("--output-dir", default="artifacts/socratic-bf16-lora")
    p.add_argument("--max-steps", type=int, default=600)
    p.add_argument("--learning-rate", type=float, default=1e-4)
    p.add_argument("--max-length", type=int, default=3072)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lora-r", type=int, default=32)
    p.add_argument("--lora-alpha", type=int, default=64)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument(
        "--target-modules",
        default=(
            "q_proj,k_proj,v_proj,o_proj,"
            "gate_proj,up_proj,down_proj,"
            "in_proj_qkv,in_proj_z,in_proj_b,in_proj_a,out_proj"
        ),
    )
    p.add_argument("--exclude-modules", default="*visual*,*vision*")
    p.add_argument("--num-layers", type=int, default=None)
    p.add_argument("--last-n-layers", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--logging-steps", type=int, default=5)
    p.add_argument("--eval-steps", type=int, default=25)
    p.add_argument("--save-steps", type=int, default=50)
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
    model.config.use_cache = False
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    tokenize_fn = make_chat_tokenize_fn(tokenizer, args.max_length)

    def load_split(path):
        ds = load_dataset("json", data_files={"data": path})["data"]
        ds = ds.map(tokenize_fn, remove_columns=list(ds.features), desc=f"Tokenizing {path}")
        return ds.filter(lambda x: any(t != -100 for t in x["labels"]))

    print(f"Tokenizing train file {args.train_file}...")
    train_dataset = load_split(args.train_file)
    print(f"Tokenizing eval file {args.eval_file}...")
    eval_dataset = load_split(args.eval_file)
    print(f"train={len(train_dataset)} eval={len(eval_dataset)}")

    lora_kwargs = dict(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=[m.strip() for m in args.target_modules.split(",") if m.strip()],
        exclude_modules=[m.strip() for m in args.exclude_modules.split(",") if m.strip()] or None,
    )
    if args.last_n_layers is not None:
        if args.num_layers is None:
            raise SystemExit("--last-n-layers requires --num-layers")
        first_layer = args.num_layers - args.last_n_layers
        lora_kwargs["layers_to_transform"] = list(range(first_layer, args.num_layers))
        print(f"Restricting LoRA to layers {first_layer}..{args.num_layers - 1} (last {args.last_n_layers} of {args.num_layers})")
    lora_config = LoraConfig(**lora_kwargs)

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        bf16=True,
        dataloader_drop_last=True,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=2,
        logging_steps=args.logging_steps,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        optim="adamw_torch_fused",
        report_to="none",
        seed=args.seed,
        data_seed=args.seed,
    )

    trainer = Trainer(
        model=model,
        processing_class=tokenizer,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=default_data_collator,
    )

    resume = any(Path(args.output_dir).glob("checkpoint-*"))
    train_result = trainer.train(resume_from_checkpoint=resume)
    eval_metrics = trainer.evaluate()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    metrics = {
        "base_model": args.model,
        "precision": "bf16",
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "max_steps": args.max_steps,
        "train_metrics": train_result.metrics,
        "eval_metrics": eval_metrics,
    }
    Path(args.output_dir, "studybuddy_bf16_training_metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
