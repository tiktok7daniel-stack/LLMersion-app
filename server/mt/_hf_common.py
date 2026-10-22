"""Shared plumbing for the HuggingFace seq2seq backends (not a backend itself:
the leading underscore keeps discovery from importing it as one)."""
from __future__ import annotations

import importlib.util


def missing_deps() -> str:
    for m in ("transformers", "torch", "sentencepiece"):
        if importlib.util.find_spec(m) is None:
            return f"missing {m}"
    return ""


def load_pair(model: str):
    """(tokenizer, model, device) for a seq2seq checkpoint, loaded once."""
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    from .. import config
    dev = config.resolve_device()
    tok = AutoTokenizer.from_pretrained(model)
    mdl = AutoModelForSeq2SeqLM.from_pretrained(model).to(dev).eval()
    # Marian configs ship a default max_length; clearing it lets max_new_tokens
    # govern alone instead of warning on every call
    mdl.generation_config.max_length = None
    return tok, mdl, dev


def generate(tok, mdl, dev, sources: list[str], **gen_kw) -> list[str]:
    import torch
    batch = tok(sources, return_tensors="pt", padding=True,
                truncation=True, max_length=512).to(dev)
    with torch.inference_mode():
        out = mdl.generate(**batch, max_new_tokens=512, num_beams=4, **gen_kw)
    return tok.batch_decode(out, skip_special_tokens=True)
