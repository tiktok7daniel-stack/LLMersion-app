"""Prompt files, loaded from prompts/.

Every instruction the local model receives lives in a plain-text file so it can
be read, reviewed and changed without touching Python. Files are named
`<job>.<variant>.txt`:

    tutor.en.txt            the conversation tutor (English is the default voice)
    correction.en.txt       the grammar coach
    writing.en.txt          writing feedback
    simplify.en.txt         paragraph simplifier
    mt.<lang>.txt           system prompt for LLM translation into <lang>
    *.hint_<lang>.txt       the opt-in hint variant, written in <lang>

`{name}` placeholders are filled by plain replacement, so braces that belong to
the prompt itself (JSON examples, for instance) never need escaping.
"""
from __future__ import annotations

from functools import lru_cache

from . import config

DIR = config.ROOT / "prompts"

HINT_LANGS = ("ar", "zh")


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    path = DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def exists(name: str) -> bool:
    return (DIR / f"{name}.txt").exists()


def load(name: str, **values: object) -> str:
    text = _read(name)
    for key, val in values.items():
        text = text.replace("{" + key + "}", str(val))
    return text


def hint(job: str, lang: str, **values: object) -> str:
    """The hint variant of `job` for `lang`, falling back to Arabic."""
    lang = lang if lang in HINT_LANGS else "ar"
    return load(f"{job}.hint_{lang}", **values)


def reload() -> None:
    _read.cache_clear()
