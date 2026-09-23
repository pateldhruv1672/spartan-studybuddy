# Vendored (trimmed) from NVIDIA TensorRT-Model-Optimizer examples/llm_qat/dataset_utils.py
# (Apache-2.0, NVIDIA CORPORATION & AFFILIATES). Only the chat tokenization / assistant-only
# label-masking logic is kept; the distributed blend/streaming machinery is dropped since we
# load a single local JSONL file per split.
from __future__ import annotations

import re

from transformers.trainer_pt_utils import LabelSmoother

IGNORE_TOKEN_ID = LabelSmoother.ignore_index

_TESTED_MODEL_FAMILIES = ("qwen", "nemotron")


def _supports_chatml_heuristic(tokenizer) -> bool:
    try:
        im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
        im_end = tokenizer.convert_tokens_to_ids("<|im_end|>")
        return tokenizer.unk_token_id not in (im_start, im_end)
    except Exception:
        return False


def _chat_template_has_generation(tokenizer) -> bool:
    template = getattr(tokenizer, "chat_template", None)
    if template is None:
        return False
    if isinstance(template, dict):
        template = template.get("default")
        if not isinstance(template, str):
            return False
    return bool(re.search(r"\{\%-?\s*generation\s*-?\%\}", template))


def _encode_role(tokenizer, role: str) -> list[int]:
    return tokenizer.encode(role, add_special_tokens=False)


def _matches_role(input_ids: list[int], start: int, role_ids: list[int]) -> bool:
    end = start + len(role_ids)
    return end <= len(input_ids) and input_ids[start:end] == role_ids


def _chatml_assistant_mask(input_ids: list[int], tokenizer) -> list[int]:
    im_start_id = tokenizer.convert_tokens_to_ids("<|im_start|>")
    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    assistant_ids = _encode_role(tokenizer, "assistant")
    newline_id = tokenizer.encode("\n", add_special_tokens=False)[-1]

    masks = [0] * len(input_ids)
    n_role = len(assistant_ids)
    in_assistant = False
    skip_remaining = 0
    skip_newline = False

    for i, tid in enumerate(input_ids):
        if tid == im_start_id:
            in_assistant = _matches_role(input_ids, i + 1, assistant_ids)
            if in_assistant:
                skip_remaining = n_role
            skip_newline = False
            continue
        if tid == im_end_id:
            in_assistant = False
            continue
        if in_assistant:
            if skip_remaining > 0:
                skip_remaining -= 1
                if skip_remaining == 0:
                    skip_newline = True
                continue
            if skip_newline:
                skip_newline = False
                if tid == newline_id:
                    continue
            masks[i] = 1

    return masks


def _is_tested_model_family(tokenizer) -> bool:
    model_name = getattr(tokenizer, "name_or_path", "") or ""
    return any(family in model_name.lower() for family in _TESTED_MODEL_FAMILIES)


def make_chat_tokenize_fn(tokenizer, max_length: int, chat_key: str = "messages"):
    """Assistant-only-loss chat tokenizer. Uses the tokenizer's native {% generation %}
    tag when available, else a ChatML heuristic mask (correct for Qwen3's ChatML template).
    """
    mask_mode = "native" if _chat_template_has_generation(tokenizer) else None
    if mask_mode is None:
        if _supports_chatml_heuristic(tokenizer):
            mask_mode = "chatml"
        else:
            raise ValueError(
                f"Tokenizer '{getattr(tokenizer, 'name_or_path', '?')}' supports neither native "
                "{% generation %} tags nor ChatML — cannot safely compute assistant-only labels."
            )

    def tokenize(sample):
        messages = sample.get(chat_key)
        if not messages:
            pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id or 0
            return {
                "input_ids": [pad_id] * max_length,
                "attention_mask": [0] * max_length,
                "labels": [IGNORE_TOKEN_ID] * max_length,
            }

        result = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            return_dict=True,
            return_assistant_tokens_mask=mask_mode == "native",
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )

        input_ids = result["input_ids"]
        if mask_mode == "native":
            label_mask = result["assistant_masks"]
        else:
            label_mask = _chatml_assistant_mask(input_ids, tokenizer)

        labels = [tid if mask else IGNORE_TOKEN_ID for tid, mask in zip(input_ids, label_mask)]
        return {"input_ids": input_ids, "attention_mask": result["attention_mask"], "labels": labels}

    return tokenize
