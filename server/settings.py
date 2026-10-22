"""User settings, persisted as one small JSON file in the data directory.

The browser keeps a copy of the UI language in localStorage so the page can set
`dir` and `lang` before first paint, but this file is the source of truth.
Unknown keys are dropped and bad values fall back to the default, so a hand-edited
or older file can never break startup.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from . import config

UI_LANGS = ("system", "en", "ar")
THEMES = ("system", "light", "dark", "black")

DEFAULTS: dict[str, Any] = {
    "ui_lang": "system",            # system | en | ar
    "theme": "system",              # system | light | dark | black (true black, for OLED)
    "text_scale": 100,              # percent of the browser's base font size, 80..150
    "show_translation": True,       # translation under each paragraph
    "translation_target": "ar",     # ar | zh
    "tts_speed": config.TTS_SPEED,  # 0.5 .. 1.5
    "tts_voice": "",                # "engine|voice", empty -> first English voice
    # per-target (backend, model) the learner picked in Settings; empty -> config default
    "mt_choice": {},
    "ocr_enabled": True,
    "ocr_arabic": False,            # add the Arabic language pack to OCR
    "arabic_hints": False,          # open Arabic hints automatically on every card
    "curator": False,               # the optional night curator stays off
}

_lock = threading.Lock()


def _coerce(key: str, val: Any) -> tuple[bool, Any]:
    """(ok, cleaned value) for one setting; ok is False when `val` is unusable."""
    default = DEFAULTS[key]
    if key == "ui_lang":
        return val in UI_LANGS, val
    if key == "theme":
        return val in THEMES, val
    if key == "translation_target":
        return val in config.MT_TARGETS, val
    if key == "tts_speed":
        try:
            return True, round(min(config.TTS_SPEED_MAX, max(config.TTS_SPEED_MIN, float(val))), 2)
        except (TypeError, ValueError):
            return False, None
    if key == "text_scale":
        try:
            return True, int(min(150, max(80, int(val))))
        except (TypeError, ValueError):
            return False, None
    if key == "mt_choice":
        if not isinstance(val, dict):
            return False, None
        return True, {t: {"backend": str(c.get("backend", "")), "model": str(c.get("model", ""))}
                      for t, c in val.items() if t in config.MT_TARGETS and isinstance(c, dict)}
    if key == "tts_voice":
        return isinstance(val, str), val
    if isinstance(default, bool):
        return isinstance(val, bool), val
    return True, val


def _clean(raw: dict, base: dict | None = None) -> dict[str, Any]:
    """Defaults, overlaid with `base`, overlaid with every valid key of `raw`."""
    out = dict(DEFAULTS)
    for layer in (base or {}, raw):
        for key in DEFAULTS:
            if key in layer:
                ok, val = _coerce(key, layer[key])
                if ok:
                    out[key] = val
    return out


def load() -> dict[str, Any]:
    with _lock:
        try:
            raw = json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, ValueError):
            raw = {}
        return _clean(raw)


def save(patch: dict) -> dict[str, Any]:
    """Merge `patch` into the stored settings and return the result.

    A key whose value is invalid is ignored, so the stored value survives a bad
    request instead of being reset to the default.
    """
    with _lock:
        try:
            current = json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        merged = _clean(patch if isinstance(patch, dict) else {},
                        current if isinstance(current, dict) else {})
        tmp = config.SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(config.SETTINGS_PATH)
        return merged


def get(key: str) -> Any:
    return load()[key]
