"""Cached translation in front of the backend registry.

The cache is keyed on target language, backend, model and source text, so an
Arabic rendering never shadows a Chinese one and switching models never serves
stale output. Rows live in the `trans` table (its `zh` column predates Arabic and
simply holds "the translation").
"""
from __future__ import annotations

from . import cache, config, settings
from .mt import MANAGER


def current_target() -> str:
    return settings.get("translation_target")


def info() -> dict:
    out = {"backends": MANAGER.status(), "defaults": {}}
    for target in config.MT_TARGETS:
        bid, model = MANAGER.default(target)
        out["defaults"][target] = {"backend": bid, "model": model}
    out["default"] = out["defaults"].get(current_target(), {"backend": "none", "model": ""})
    out["target"] = current_target()
    out["targets"] = list(config.MT_TARGETS)
    return out


def cache_key(target: str, backend: str, model: str, text: str) -> str:
    # `zh` keeps its historical key so existing Chinese caches stay valid
    tag = f"{backend}:{model}" if target == "zh" else f"{target}|{backend}:{model}"
    return cache.sha1(tag, text)


def translate(texts: list[str], backend: str = "", model: str = "",
              target: str = "") -> list[str]:
    target = target if target in config.MT_TARGETS else current_target()
    if not backend or not model:
        d_backend, d_model = MANAGER.default(target)
        backend = backend or d_backend
        model = model or d_model
    if backend == "none" or not model:
        return ["" for _ in texts]

    keys = [cache_key(target, backend, model, t) for t in texts]
    results: list[str | None] = [cache.get_trans(k) for k in keys]

    todo = [i for i, r in enumerate(results) if r is None]
    if todo:
        fresh = MANAGER.translate([texts[i] for i in todo], backend, model, target)
        for i, tr in zip(todo, fresh):
            results[i] = tr
            if tr:
                cache.put_trans(keys[i], tr)
    return [r or "" for r in results]
