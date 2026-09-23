#!/usr/bin/env python3
"""Merge the bf16 LoRA adapter into Qwen3.8-27B's base weights, producing a single bf16
checkpoint ready for NVFP4 quantization (nvfp4/quantize.py) for serving.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-model", default="Qwen/Qwen3.8-27B")
    p.add_argument(
        "--model-class",
        default="image-text-to-text",
        choices=["causal-lm", "image-text-to-text"],
    )
    p.add_argument("--adapter", default="artifacts/socratic-bf16-lora")
    p.add_argument("--output-dir", default="artifacts/socratic-bf16-merged")
    args = p.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_cls = AutoModelForImageTextToText if args.model_class == "image-text-to-text" else AutoModelForCausalLM
    base = model_cls.from_pretrained(
        args.base_model, dtype=torch.bfloat16, device_map={"": 0}, trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(base, args.adapter)
    merged = model.merge_and_unload()
    merged.save_pretrained(out, safe_serialization=True, max_shard_size="5GB")
    tok = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    tok.save_pretrained(out)
    manifest = {"base_model": args.base_model, "adapter": args.adapter, "merged_model": str(out)}
    (out / "studybuddy_merge_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
