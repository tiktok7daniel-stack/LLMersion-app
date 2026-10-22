"""Runtime configuration. Everything is overridable by environment variables."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    """Per-user state directory, following each platform's convention.

    State lives outside the project on purpose: replacing the code should never
    cost you the audio cache, the translations, the vocabulary or your place in
    a document.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    root = Path(base)
    # an install that predates the LumenRead rename keeps its caches, vocabulary
    # and reading positions: reuse the old folder if it is the only one there
    legacy = root / "ReadingDesk"
    if legacy.exists() and not (root / "LumenRead").exists():
        return legacy
    return root / "LumenRead"


DATA = Path(os.environ["PR_DATA"]) if os.environ.get("PR_DATA") else _user_data_dir()

DOCS_DIR = DATA / "docs"
AUDIO_DIR = DATA / "audio"
DB_PATH = DATA / "reader.db"
DICT_DB = Path(os.environ.get("PR_DICT_DB", DATA / "ecdict.db"))

MODELS_DIR = Path(os.environ.get("PR_MODELS", DATA / "models"))
VOICES_DIR = Path(os.environ.get("PR_VOICES", MODELS_DIR / "voices"))
PIPER_DIR = Path(os.environ.get("PR_PIPER_DIR", MODELS_DIR / "tts" / "piper"))

# optional Arabic voices (Piper). Core reading never needs them.
PIPER_AR_DIR = Path(os.environ.get("PR_PIPER_AR_DIR", MODELS_DIR / "tts" / "piper-ar"))
SETTINGS_PATH = DATA / "settings.json"

for _p in (DATA, DOCS_DIR, AUDIO_DIR, VOICES_DIR, PIPER_DIR, PIPER_AR_DIR):
    _p.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("PR_HOST", "127.0.0.1")
PORT = int(os.environ.get("PR_PORT", "8848"))
# Set PR_TOKEN when binding to anything other than loopback. Requests must then
# carry ?token=... or an X-Reader-Token header. This is a doorstop, not
# security — put it behind SSH or a reverse proxy for anything real.
TOKEN = os.environ.get("PR_TOKEN", "")


def is_local() -> bool:
    return HOST in ("127.0.0.1", "localhost", "::1")

# ---------------------------------------------------------------- TTS
# auto, or any engine id registered in server/engines/
TTS_ENGINE = os.environ.get("PR_TTS", "auto")
TTS_VOICE = os.environ.get("PR_TTS_VOICE", "")   # empty -> first voice available
# learners start slow; the UI offers 0.5x to 1.5x
TTS_SPEED_MIN, TTS_SPEED_MAX = 0.5, 1.5
TTS_SPEED = min(TTS_SPEED_MAX, max(TTS_SPEED_MIN, float(os.environ.get("PR_TTS_SPEED", "0.8"))))
TTS_KEEP = int(os.environ.get("PR_TTS_KEEP", "1"))   # engines kept resident in VRAM
# paragraph = one pass per paragraph (natural prosody); sentence = one pass per sentence
TTS_UNIT = os.environ.get("PR_TTS_UNIT", "paragraph")

# ---------------------------------------------------------------- translate
# auto, or any backend id registered in server/mt/
MT_BACKEND = os.environ.get("PR_MT", "auto")
MT_MODEL = os.environ.get("PR_MT_MODEL", "")   # preferred model, if it is installed

# Translation is a learning aid and independent of the UI language. The target is
# a setting (see server/settings.py); these are the per-target model preferences.
# Arabic defaults to Helsinki-NLP/opus-mt-en-ar (CC-BY-4.0). Swap in any model a
# registered backend lists, e.g. PR_MT_MODEL_AR=facebook/nllb-200-distilled-600M.
MT_TARGETS = ("ar", "zh")
MT_PREFS = {
    "ar": {"backend": os.environ.get("PR_MT_BACKEND_AR", "auto"),
           "model": os.environ.get("PR_MT_MODEL_AR", "Helsinki-NLP/opus-mt-en-ar")},
    "zh": {"backend": os.environ.get("PR_MT_BACKEND_ZH", MT_BACKEND),
           "model": os.environ.get("PR_MT_MODEL_ZH", MT_MODEL)},
}

# ---------------------------------------------------------------- OCR (scanned PDFs)
# Tesseract is a separate install; everything degrades gracefully without it.
TESSERACT_CMD = os.environ.get("PR_TESSERACT", "")      # path to the binary, if not on PATH
OCR_DPI = int(os.environ.get("PR_OCR_DPI", "200"))
# a page with fewer characters than this has no usable text layer
OCR_MIN_CHARS = int(os.environ.get("PR_OCR_MIN_CHARS", "25"))
OLLAMA_URL = os.environ.get("PR_OLLAMA_URL", "http://127.0.0.1:11434")

# ---------------------------------------------------------------- pronunciation
# a phoneme-level CTC model; the learner's audio and the TTS reference both go
# through it, so no grapheme-to-phoneme component is needed
ASR_MODEL = os.environ.get("PR_ASR_MODEL", "facebook/wav2vec2-lv-60-espeak-cv-ft")

DEVICE = os.environ.get("PR_DEVICE", "auto")  # auto | cuda | mps | cpu


def resolve_device() -> str:
    if DEVICE != "auto":
        return DEVICE
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"
