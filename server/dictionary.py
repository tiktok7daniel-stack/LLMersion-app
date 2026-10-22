"""Word lookup.

Primary source is ECDICT (github.com/skywind3000/ECDICT, CC-BY / MIT-ish, 3.4M
entries with phonetics, definitions and inflection tables) compiled into a local
SQLite file by ``tools/build_ecdict.py``. Everything is offline and O(1).

If the dictionary is missing we degrade to the translation backend, which still
gives a usable meaning for the selected word or phrase.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from typing import Optional

from . import config

_local = threading.local()
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _conn() -> Optional[sqlite3.Connection]:
    if not config.DICT_DB.exists():
        return None
    c = getattr(_local, "dict", None)
    if c is None:
        c = sqlite3.connect(config.DICT_DB, check_same_thread=False)
        c.row_factory = sqlite3.Row
        _local.dict = c
    return c


def available() -> bool:
    return _conn() is not None


def _row(c: sqlite3.Connection, w: str):
    return c.execute("SELECT * FROM entry WHERE word=?", (w,)).fetchone()


def _naive_lemmas(w: str) -> list[str]:
    out = []
    for suf, reps in (("ies", ["y"]), ("es", ["", "e"]), ("s", [""]),
                      ("ied", ["y"]), ("ed", ["", "e"]), ("ing", ["", "e"]),
                      ("est", ["", "e"]), ("er", ["", "e"]), ("ly", [""])):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            stem = w[: -len(suf)]
            out.extend(stem + r for r in reps)
            if len(stem) > 2 and stem[-1] == stem[-2]:
                out.append(stem[:-1])
    return out


def base_form(word: str) -> str:
    """Return the dictionary head word for an inflected form ('studies' -> 'study')."""
    w = word.strip().lower()
    if not w or " " in w:
        return w
    c = _conn()
    if c is None:
        for cand in _naive_lemmas(w):
            if cand and len(cand) > 2:
                return cand
        return w
    if _row(c, w) is not None:
        lem = c.execute("SELECT base FROM lemma WHERE form=?", (w,)).fetchone()
        # a word can be both a valid entry and an inflection ("studies"); prefer
        # the base only when the base is itself a known entry
        if lem and _row(c, lem["base"]) is not None and lem["base"] != w:
            return lem["base"]
        return w
    lem = c.execute("SELECT base FROM lemma WHERE form=?", (w,)).fetchone()
    if lem:
        return lem["base"]
    for cand in _naive_lemmas(w):
        if _row(c, cand) is not None:
            return cand
    return w


def lookup(query: str, target: str = "") -> dict:
    """Everything the word popup shows.

    `phonetic` (IPA) and `definition` (English) come from ECDICT when it is built.
    `gloss` is the meaning in the learner's translation language: for Arabic it is
    produced by the Arabic MT backend (and cached), for Chinese ECDICT's own
    Chinese entry is used. `translation` mirrors `gloss` for older callers.
    """
    from . import translate as mt
    q = query.strip()
    if not q:
        return {}
    target = target if target in config.MT_TARGETS else mt.current_target()
    words = _WORD.findall(q)
    is_phrase = len(words) > 1
    head = q.lower() if not is_phrase else q

    result = {"query": q, "word": q, "phonetic": "", "translation": "", "gloss": "",
              "target": target, "zh": "", "definition": "", "tag": "",
              "source": "none", "lemma_of": ""}

    c = _conn()
    if c is not None and not is_phrase:
        w = head
        r = _row(c, w)
        if r is None:
            lem = c.execute("SELECT base FROM lemma WHERE form=?", (w,)).fetchone()
            if lem:
                r = _row(c, lem["base"])
                if r:
                    result["lemma_of"] = lem["base"]
        if r is None:
            for cand in _naive_lemmas(w):
                r = _row(c, cand)
                if r:
                    result["lemma_of"] = cand
                    break
        if r is not None:
            result.update({
                "word": r["word"],
                "phonetic": r["phonetic"] or "",
                "zh": (r["translation"] or "").replace("\\n", "\n"),
                "definition": (r["definition"] or "").replace("\\n", "\n"),
                "tag": r["tag"] or "",
                "source": "ecdict",
            })
            if target == "zh":
                result["gloss"] = result["zh"]
            else:
                result["gloss"] = _gloss(result["word"], target)
            result["translation"] = result["gloss"]
            return result

    # no dictionary entry (or a phrase): the translation model still gives a gloss
    result["gloss"] = _gloss(q, target)
    result["translation"] = result["gloss"]
    result["source"] = "mt" if result["gloss"] else "none"
    if not is_phrase and not result["definition"]:
        result["definition"] = _define(q)
    return result


def _gloss(text: str, target: str) -> str:
    from . import translate as mt
    try:
        return mt.translate([text], target=target)[0]
    except Exception:  # noqa: BLE001 — a missing backend must not break the popup
        return ""


def _define(word: str) -> str:
    """One-line English definition from the tutor model, when there is no dictionary."""
    from . import cache, llm
    key = cache.sha1("define", word.lower())
    hit = cache.get_trans(key)
    if hit is not None:
        return hit
    if not llm.available():
        return ""
    try:
        out = llm.chat(llm.prompts.load("define.en", word=word), temperature=0.1, timeout=40)
    except Exception:  # noqa: BLE001
        return ""
    out = out.strip().splitlines()[0].strip() if out.strip() else ""
    if out:
        cache.put_trans(key, out)
    return out
