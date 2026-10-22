"""English -> Arabic translation, offline, from small seq2seq models.

Default is Helsinki-NLP/opus-mt-en-ar (Marian, ~77 M parameters, CC-BY-4.0): fast
enough to translate a paragraph while the voice is still reading the previous
one. NLLB-200 is offered as a slower, usually better alternative; pick either
with PR_MT_MODEL_AR or in Settings. Any other model can be added to `MODELS`.

opus-mt-en-ar is a multi-target model: the source text must start with a
sentence-initial token naming the target variety, `>>ara<<` for Modern Standard
Arabic. Without it the model may answer in a dialect or in Latin script.
"""
from __future__ import annotations

from . import register
from ._hf_common import generate, load_pair, missing_deps
from .base import MTBackend, join_sentences

OPUS_PREFIX = ">>ara<<"
NLLB_ARABIC = "arb_Arab"

MODELS = [
    {"id": "Helsinki-NLP/opus-mt-en-ar", "label": "opus-mt en-ar (77M, very fast)",
     "license": "CC-BY-4.0"},
    {"id": "facebook/nllb-200-distilled-600M", "label": "NLLB-200 600M",
     "license": "CC-BY-NC-4.0"},
    {"id": "facebook/nllb-200-1.3B", "label": "NLLB-200 1.3B",
     "license": "CC-BY-NC-4.0"},
]


def prepare(model: str, sentences: list[str]) -> list[str]:
    """Source strings as the model expects them."""
    if "opus-mt" in model:
        return [f"{OPUS_PREFIX} {s}" for s in sentences]
    return list(sentences)


def generation_kwargs(model: str, tok) -> dict:
    if "nllb" in model:
        return {"forced_bos_token_id": tok.convert_tokens_to_ids(NLLB_ARABIC)}
    return {}


@register
class OpusArabicBackend(MTBackend):
    id = "opus_ar"
    label = "Arabic MT (opus-mt / NLLB)"
    rank = 5
    targets = ("ar",)
    notes = "pip install transformers sentencepiece sacremoses torch"

    @classmethod
    def check(cls) -> tuple[bool, str]:
        why = missing_deps()
        return (not why, why)

    @classmethod
    def list_models(cls) -> list[dict]:
        return MODELS

    def load(self) -> None:
        self._cache: dict[str, tuple] = {}

    def _pair(self, model: str):
        if model not in self._cache:
            self._cache = {model: load_pair(model)}   # keep only the current one
        return self._cache[model]

    def translate(self, texts: list[str], model: str, target: str = "ar") -> list[str]:
        from ..textseg import split_sentences
        tok, mdl, dev = self._pair(model)
        kw = generation_kwargs(model, tok)
        out = []
        for t in texts:
            sents = [s["text"] for s in split_sentences(t)] or [t]
            parts = generate(tok, mdl, dev, prepare(model, sents), **kw)
            out.append(join_sentences(parts, "ar"))
        return out
