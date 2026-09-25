#!/usr/bin/env python3
"""Export a modelopt-quantized checkpoint (from quantize.py) to a clean HF layout vLLM can load,
via modelopt's `export_hf_checkpoint()`. Originally adapted from NVIDIA TensorRT-Model-Optimizer's
examples/llm_qat/export.py, since rewritten for modelopt 0.37.0's newer, simpler export API and for
plain (non-QLoRA) checkpoints -- see the note below.

Usage:
    python3 training/nvfp4/export_nvfp4.py \
        --pyt-ckpt-path artifacts/socratic-nvfp4-quantized-final \
        --export-path artifacts/socratic-nvfp4-final
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer

import modelopt.torch.opt as mto
from modelopt.torch.export.unified_export_hf import export_hf_checkpoint
from modelopt.torch.opt.conversion import ModeloptStateManager

mto.enable_huggingface_checkpointing()

# NOTE: modelopt 0.37.0's public export API is `export_hf_checkpoint()` (writes hf_quant_config.json
# + quantization_config + safetensors straight to export_dir in one call). The older two-step
# `_export_transformers_checkpoint(model, is_modelopt_qlora=...)` used by NVIDIA's llm_qat/export.py
# example does not exist in this version, so this script no longer supports the QLoRA
# (base_model/ + adapter) export layout that function produced -- our pipeline never used it since
# we merge the LoRA adapter into bf16 weights *before* quantizing (see merge_bf16_lora.py), so the
# quantized checkpoint here is always a plain model with no `peft_config`.


def get_model(ckpt_path: str, model_class: str, device: str = "cuda"):
    device_map = "cpu" if device == "cpu" else "auto"
    model_cls = AutoModelForImageTextToText if model_class == "image-text-to-text" else AutoModelForCausalLM
    # enable_huggingface_checkpointing() patches from_pretrained to also restore the modelopt
    # quantization state (modelopt_state.pth, written by quantize.py's model.save_pretrained) --
    # nothing further to do here as long as that file sits next to the checkpoint.
    # NOTE: this must load a checkpoint saved by quantize.py WITHOUT mtq.compress() -- i.e. the
    # fake-quantized (calibrated, still full-shape) model. export_hf_checkpoint() below runs its
    # own forward pass to resmooth/fuse quantizer scales, then does the real low-bit packing
    # itself. A pre-compressed (physically packed) checkpoint has no working real-quant GEMM here
    # (needs tensorrt_llm, not installed) and both loading and that forward pass will break with
    # shape mismatches -- see quantize.py's comment at its (removed) mtq.compress() call.
    model = model_cls.from_pretrained(ckpt_path, dtype=torch.bfloat16, device_map=device_map, trust_remote_code=True)
    if hasattr(model, "peft_config"):
        raise SystemExit(
            "This checkpoint has a peft_config (QLoRA-style adapter-on-quantized-base). That export "
            "path needs modelopt's older _export_transformers_checkpoint API, which this modelopt "
            "version (0.37.0) removed. Our pipeline merges the adapter before quantizing, so this "
            "script only supports plain (non-adapter) checkpoints; if you see this, something upstream "
            "changed."
        )
    assert ModeloptStateManager.is_converted(model), (
        f"{ckpt_path} has no restored modelopt quantization state -- is modelopt_state.pth present?"
    )
    return model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pyt-ckpt-path", required=True)
    p.add_argument("--model-class", default="image-text-to-text", choices=["causal-lm", "image-text-to-text"])
    p.add_argument("--device", default="cuda")
    p.add_argument("--export-path", default="exported_model")
    args = p.parse_args()

    model = get_model(args.pyt_ckpt_path, args.model_class, args.device)
    tokenizer = AutoTokenizer.from_pretrained(args.pyt_ckpt_path, trust_remote_code=True)

    export_dir = Path(args.export_path)
    export_dir.mkdir(parents=True, exist_ok=True)

    export_hf_checkpoint(model, dtype=torch.bfloat16, export_dir=export_dir, save_modelopt_state=False)
    tokenizer.save_pretrained(export_dir)
    print(f"Exported to {export_dir}")


if __name__ == "__main__":
    main()
