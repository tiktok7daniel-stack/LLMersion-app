"""Local LLM helper for learning features (writing feedback, simplification, hints).

One narrow function over the Ollama chat API. Every use in the reader is a
place where the model's output is inspectable by the learner --- a correction
they can compare against their draft, a paraphrase they can compare against
the original --- in keeping with the system's rule of never using a generative
model as an unverifiable oracle.

The prompts themselves are files in prompts/ (see server/prompts.py).
"""
from __future__ import annotations

import os

import requests

from . import config, prompts

MODEL = os.environ.get("PR_LLM_MODEL", "gemma3:4b")


def available() -> bool:
    try:
        requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def chat(prompt: str, temperature: float = 0.3, timeout: int = 180) -> str:
    r = requests.post(f"{config.OLLAMA_URL}/api/chat",
                      json={"model": MODEL, "stream": False,
                            "options": {"temperature": temperature, "num_ctx": 4096},
                            "messages": [{"role": "user", "content": prompt}]},
                      timeout=timeout)
    r.raise_for_status()
    out = r.json().get("message", {}).get("content", "").strip()
    if "</think>" in out:
        out = out.split("</think>")[-1].strip()
    return out


def write_prompt(vocab: str, text: str) -> str:
    return prompts.load("writing.en", vocab=vocab, text=text)


def simplify_prompt(text: str) -> str:
    return prompts.load("simplify.en", text=text)
