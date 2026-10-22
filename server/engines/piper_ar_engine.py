"""Piper Arabic voices — optional, never required for reading.

Reading in LumenRead is English-first, so no Arabic voice is needed for the core
loop. This engine exists for learners who want to *hear* the Arabic translation
or an Arabic document. It is the same Piper runtime as `piper_engine.py`, pointed
at a separate folder so the English default can never land on an Arabic voice.

Setup (see docs/INSTALL.md):

    pip install piper-tts
    # download an Arabic voice (.onnx + .onnx.json) from
    #   https://huggingface.co/rhasspy/piper-voices/tree/main/ar
    # e.g. ar_JO-kareem-medium, and put both files in <data>/models/tts/piper-ar/

Voice licenses differ per voice; read the model card before redistributing.
"""
from __future__ import annotations

import importlib.util

from . import register
from .piper_engine import PiperEngine
from .base import Voice


@register
class PiperArabicEngine(PiperEngine):
    id = "piper_ar"
    label = "Piper Arabic (optional)"
    rank = 90
    notes = ("pip install piper-tts, then put an Arabic voice (.onnx + .onnx.json from "
             "rhasspy/piper-voices) in <data>/models/tts/piper-ar/")

    @classmethod
    def check(cls) -> tuple[bool, str]:
        if importlib.util.find_spec("piper") is None:
            return False, "missing piper"
        from .. import config
        if not list(config.PIPER_AR_DIR.glob("**/*.onnx")):
            return False, f"no Arabic .onnx voices in {config.PIPER_AR_DIR}"
        return True, ""

    @classmethod
    def list_voices(cls) -> list[Voice]:
        from .. import config
        out = []
        for p in sorted(config.PIPER_AR_DIR.glob("**/*.onnx")):
            out.append(Voice(id=p.stem, label=p.stem.replace("_", " "), engine=cls.id,
                             accent="Arabic", lang="ar", params={"path": str(p)}))
        return out
