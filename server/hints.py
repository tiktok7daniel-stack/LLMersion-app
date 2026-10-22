"""Opt-in hints in the learner's own language.

Tutor replies, grammar corrections, pronunciation feedback and writing notes are
English by default. Each card has a "Show Arabic hint" button; pressing it calls
`make()` here, which asks the local tutor model for a short explanation in Arabic
(or Chinese, when that is the translation target). Nothing is generated until the
button is pressed, and every result is cached.

When no LLM is running, a hint for a tutor line or a correction rule falls back to
plain machine translation of the English, which is less helpful but never wrong
about what was said. Pronunciation and writing hints need the LLM.
"""
from __future__ import annotations

import json

from . import cache, llm, prompts, translate

KINDS = ("tutor", "correction", "pronunciation", "writing")
LANGS = ("ar", "zh")


class HintError(Exception):
    def __init__(self, key: str, msg: str = ""):
        super().__init__(msg or key)
        self.key = key


def _problems(ops: list[dict]) -> str:
    lines = []
    for o in ops or []:
        op = o.get("op")
        if op == "sub":
            lines.append(f"/{o.get('target', '')}/ -> /{o.get('heard', '')}/")
        elif op == "miss":
            lines.append(f"/{o.get('target', '')}/ -> (not pronounced)")
        elif op == "extra":
            lines.append(f"(nothing) -> /{o.get('heard', '')}/")
    return "\n".join(lines[:8]) or "(no specific mismatches)"


def _prompt(kind: str, lang: str, ctx: dict) -> str:
    s = lambda k, n=800: str(ctx.get(k, "")).strip()[:n]   # noqa: E731
    if kind == "tutor":
        return prompts.hint("tutor", lang, text=s("text"))
    if kind == "correction":
        return prompts.hint("correction", lang, said=s("said"), fixed=s("fixed"), why=s("why"))
    if kind == "pronunciation":
        return prompts.hint("pronunciation", lang, word=s("word", 80),
                            problems=_problems(ctx.get("ops") or []))
    return prompts.hint("writing", lang, feedback=s("feedback", 3000))


def _fallback_text(kind: str, ctx: dict) -> str:
    if kind == "tutor":
        return str(ctx.get("text", "")).strip()
    if kind == "correction":
        return str(ctx.get("why", "")).strip()
    return ""


def make(kind: str, lang: str, ctx: dict) -> dict:
    """{hint, lang, source} or raises HintError(key)."""
    if kind not in KINDS:
        raise HintError("err.hint_kind", f"unknown hint kind {kind!r}")
    if lang not in LANGS:
        lang = translate.current_target()
    prompt = _prompt(kind, lang, ctx)
    key = cache.sha1("hint", kind, lang, json.dumps(ctx, sort_keys=True, ensure_ascii=False))
    hit = cache.get_trans(key)
    if hit:
        return {"hint": hit, "lang": lang, "source": "cache"}

    if llm.available():
        try:
            out = llm.chat(prompt, temperature=0.2, timeout=120).strip()
        except Exception as exc:  # noqa: BLE001
            raise HintError("err.llm_failed", exc.__class__.__name__) from exc
        if out:
            cache.put_trans(key, out)
            return {"hint": out, "lang": lang, "source": "llm"}

    src = _fallback_text(kind, ctx)
    if src:
        try:
            out = translate.translate([src], target=lang)[0]
        except Exception:  # noqa: BLE001
            out = ""
        if out:
            return {"hint": out, "lang": lang, "source": "mt"}
    raise HintError("err.hint_unavailable")
