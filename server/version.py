"""Product identity, version and the license table shown on the About screen.

The model names and license identifiers are proper nouns / SPDX ids, so they live
here as data; every sentence around them lives in web/i18n/*.json.
"""
from __future__ import annotations

APP_NAME = "LumenRead"
__version__ = "1.0.0"

UPSTREAM = {
    "name": "LLMersion-1",
    "project": "LLMersion",
    "repo": "https://github.com/QM378/LLMersion",
    "paper": "https://arxiv.org/abs/2609.29672",
    "paper_title": ("LLMersion: A Local-First AI Agent Framework for Low-Cost Home "
                    "Language Learning toward Educational Equity"),
    "license": "MIT",
}

# Weights are never bundled; each keeps the license on its upstream model card.
MODELS = [
    {"id": "opus-mt-en-ar", "name": "Helsinki-NLP/opus-mt-en-ar", "license": "CC-BY-4.0",
     "url": "https://huggingface.co/Helsinki-NLP/opus-mt-en-ar", "role": "translation"},
    {"id": "opus-mt-en-zh", "name": "Helsinki-NLP/opus-mt-en-zh", "license": "CC-BY-4.0",
     "url": "https://huggingface.co/Helsinki-NLP/opus-mt-en-zh", "role": "translation"},
    {"id": "kokoro", "name": "Kokoro-82M", "license": "Apache-2.0",
     "url": "https://huggingface.co/hexgrad/Kokoro-82M", "role": "voice"},
    {"id": "whisper", "name": "Whisper / faster-whisper", "license": "MIT",
     "url": "https://github.com/openai/whisper", "role": "speech"},
    {"id": "wav2vec2", "name": "wav2vec2-lv-60-espeak-cv-ft", "license": "Apache-2.0",
     "url": "https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft",
     "role": "pronunciation"},
    {"id": "tutor", "name": "Ollama tutor model (Llama / Qwen / Gemma)", "license": "per-model-card",
     "url": "https://ollama.com/library", "role": "tutor"},
    {"id": "piper-ar", "name": "Piper Arabic voices (optional)", "license": "per-voice-card",
     "url": "https://huggingface.co/rhasspy/piper-voices", "role": "voice"},
    {"id": "tesseract", "name": "Tesseract OCR eng + ara (optional)", "license": "Apache-2.0",
     "url": "https://github.com/tesseract-ocr/tesseract", "role": "ocr"},
    {"id": "ecdict", "name": "ECDICT (optional dictionary)", "license": "MIT",
     "url": "https://github.com/skywind3000/ECDICT", "role": "dictionary"},
]


def about() -> dict:
    return {"name": APP_NAME, "version": __version__, "upstream": UPSTREAM,
            "models": MODELS, "code_license": "MIT"}
