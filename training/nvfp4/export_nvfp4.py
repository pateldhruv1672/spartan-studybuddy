#!/usr/bin/env python3
"""Export a modelopt NVFP4-QLoRA checkpoint to a base_model/ + adapter layout vLLM can serve
with --enable-lora. Adapted near-verbatim from NVIDIA TensorRT-Model-Optimizer's
examples/llm_qat/export.py.

Usage:
    python3 training/nvfp4/export_nvfp4.py \
        --pyt-ckpt-path artifacts/socratic-nvfp4-lora \
        --export-path artifacts/socratic-nvfp4-lora-hf
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

from transformers import AutoModelForCausalLM, AutoTokenizer

import modelopt.torch.opt as mto
from modelopt.torch.export.convert_hf_config import convert_hf_quant_config_format
from modelopt.torch.export.unified_export_hf import _export_transformers_checkpoint
from modelopt.torch.opt.conversion import ModeloptStateManager, restore_from_modelopt_state
from modelopt.torch.quantization.utils import set_quantizer_state_dict
from modelopt.torch.utils import print_rank_0

mto.enable_huggingface_checkpointing()


def get_model(ckpt_path: str, device: str = "cuda"):
    device_map = "cpu" if device == "cpu" else "auto"
    model = AutoModelForCausalLM.from_pretrained(ckpt_path, device_map=device_map)
    if hasattr(model, "peft_config") and not ModeloptStateManager.is_converted(model):
        modelopt_state = mto.load_modelopt_state(f"{ckpt_path}/modelopt_state_train.pth")
        restore_from_modelopt_state(model, modelopt_state)
        modelopt_weights = modelopt_state.pop("modelopt_state_weights", None)
        if modelopt_weights is not None:
            set_quantizer_state_dict(model, modelopt_weights)
        print_rank_0("Restored modelopt state")
    return model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pyt-ckpt-path", required=True)
    p.add_argument("--device", default="cuda")
    p.add_argument("--export-path", default="exported_model")
    args = p.parse_args()

    model = get_model(args.pyt_ckpt_path, args.device)
    tokenizer = AutoTokenizer.from_pretrained(args.pyt_ckpt_path)
    is_qlora = hasattr(model, "peft_config")

    export_dir = Path(args.export_path)
    export_dir.mkdir(parents=True, exist_ok=True)
    base_model_dir = export_dir / "base_model" if is_qlora else export_dir
    base_model_dir.mkdir(parents=True, exist_ok=True)

    try:
        post_state_dict, hf_quant_config = _export_transformers_checkpoint(model, is_modelopt_qlora=is_qlora)
        with open(f"{base_model_dir}/hf_quant_config.json", "w") as f:
            json.dump(hf_quant_config, f, indent=4)
        hf_quant_config = convert_hf_quant_config_format(hf_quant_config)

        if is_qlora:
            model.base_model.save_pretrained(f"{base_model_dir}", state_dict=post_state_dict)
            model.save_pretrained(export_dir)
        else:
            model.save_pretrained(export_dir, state_dict=post_state_dict)

        config_data = model.config.to_dict()
        config_data["quantization_config"] = hf_quant_config
        with open(f"{base_model_dir}/config.json", "w") as f:
            json.dump(config_data, f, indent=4)

        tokenizer.save_pretrained(export_dir)
        print(f"Exported to {export_dir} (base_model/ + adapter)")
    except Exception:
        warnings.warn("Export failed; the modelopt-optimized state_dict can be saved with torch.save for inspection.")
        raise


if __name__ == "__main__":
    main()
