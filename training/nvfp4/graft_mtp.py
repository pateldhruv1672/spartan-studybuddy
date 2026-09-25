#!/usr/bin/env python3
"""Copy the base model's MTP (multi-token-prediction) tensors into an exported checkpoint.

The HF model class used for merging/quantizing does not load `mtp.*` weights, so the exported
checkpoint lacks the draft head that vLLM's `mtp` speculative decoding needs. The base checkpoint
ships them in bf16 (NVIDIA's NVFP4 build also leaves them unquantized: exclude_modules `mtp*`).
This writes them as an extra shard and adds them to model.safetensors.index.json. Nothing else
in the target directory is modified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--target", required=True, help="exported checkpoint dir to add mtp.* tensors to")
    args = p.parse_args()

    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    from safetensors.torch import save_file

    target = Path(args.target)
    idx_path = target / "model.safetensors.index.json"
    single_file = target / "model.safetensors"
    if idx_path.exists():
        tgt_idx = json.loads(idx_path.read_text())
    elif single_file.exists():
        # Our export writes a single unsharded model.safetensors with no index.json. Build one:
        # existing tensors all map to that file (untouched), new mtp tensors map to a new shard.
        # This only reads the header (tensor names), never the ~19 GB of tensor data itself.
        with safe_open(single_file, framework="pt") as f:
            weight_map = {k: "model.safetensors" for k in f.keys()}
        tgt_idx = {"metadata": {"total_size": single_file.stat().st_size}, "weight_map": weight_map}
    else:
        raise SystemExit(f"Neither {idx_path} nor {single_file} exists")
    if any(k.startswith("mtp.") for k in tgt_idx["weight_map"]):
        print("target already has mtp.* tensors; nothing to do")
        return

    base_idx = json.loads(Path(hf_hub_download(args.base_model, "model.safetensors.index.json")).read_text())
    mtp_keys = {k: f for k, f in base_idx["weight_map"].items() if k.startswith("mtp.")}
    print(f"base has {len(mtp_keys)} mtp tensors in shards {sorted(set(mtp_keys.values()))}")

    tensors = {}
    for shard in sorted(set(mtp_keys.values())):
        path = hf_hub_download(args.base_model, shard)
        with safe_open(path, framework="pt") as f:
            for k in f.keys():
                if k in mtp_keys:
                    tensors[k] = f.get_tensor(k).contiguous()
    missing = set(mtp_keys) - set(tensors)
    assert not missing, f"missing tensors: {sorted(missing)[:5]}"

    out_name = "model-mtp.safetensors"
    save_file(tensors, str(target / out_name), metadata={"format": "pt"})
    for k in tensors:
        tgt_idx["weight_map"][k] = out_name
    idx_path.write_text(json.dumps(tgt_idx, indent=2))
    print(f"wrote {len(tensors)} tensors ({sum(t.numel() for t in tensors.values())/1e6:.1f}M params) -> {target/out_name}")


if __name__ == "__main__":
    main()
