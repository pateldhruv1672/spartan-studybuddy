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
import copy
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
    # NVFP4_DEFAULT_CFG's *weight_quantizer/*input_quantizer patterns are unqualified wildcards, so
    # they also sweep in the vision tower and the GatedDeltaNet causal-conv1d layers. Both are not
    # plain nn.Linear weight matrices (conv1d weight is [out_ch, 1, kernel], vision patch_embed is a
    # patchify conv), and modelopt's real-quant compress/export path corrupts their on-disk shape
    # when it packs them the same way it packs a 2D linear weight (verified: re-loading a checkpoint
    # quantized without this exclusion raises a size-mismatch LOAD REPORT on every conv1d.weight and
    # on visual.patch_embed.proj.weight). NVIDIA's own NVFP4 build of this exact model (see
    # nvidia/Qwen3.8-27B-NVFP4's hf_quant_config.json) likewise never lists conv1d or vision layers
    # among the quantized ones, i.e. it excludes them too. Mirror that here, in the same style as the
    # config's own `*lm_head*` etc. exclude entries.
    quant_cfg = copy.deepcopy(mtq.NVFP4_DEFAULT_CFG)
    for pattern in ("*conv1d*", "*visual*", "*vision*"):
        quant_cfg["quant_cfg"][pattern] = {"enable": False}
    mtq.quantize(model, quant_cfg, forward_loop)
    mtq.print_quant_summary(model)

    # Deliberately NOT calling mtq.compress() here. That physically packs weights into real
    # low-bit storage (e.g. a Linear's [out,in] weight becomes a packed [out,in/2] byte tensor),
    # which is right for continued QLoRA training on a memory-constrained real-quant model, but
    # wrong for this PTQ-then-export-to-vLLM flow: modelopt's own export_nvfp4.py step
    # (export_hf_checkpoint -> requantize_resmooth_fused_llm_layers) runs a real forward pass
    # through the model to resmooth/fuse quantizer scales across fused layers (e.g. qkv), and does
    # the physical packing itself afterward. Pre-compressing here left weights in a packed shape
    # with disabled quantizers and no real-quant GEMM kernel available (needs tensorrt_llm, not
    # installed), so that forward pass crashed with a shape mismatch (verified: 3 export attempts,
    # traceback pinpointed model(fake_input) inside requantize_resmooth_fused_llm_layers). Save the
    # fake-quantized (calibrated, still full-shape) model instead and let export do the real packing.

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Saving quantized checkpoint to {out}...")
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    print("Done.")


if __name__ == "__main__":
    main()
