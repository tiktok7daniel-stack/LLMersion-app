"""The tutor, and the coach sitting next to it.

Three ways to ground a conversation, because forcing a document on someone who
just wants to talk is the wrong default, and forcing free chat on someone who
just finished a paper wastes the one thing this system has that an online
assistant does not:

    free    nothing but the learner's own vocabulary list
    topic   one line the learner typed
    doc     the stretch of document the voice actually read to them

All three share the same speaking rules and the same vocabulary instruction.
That instruction is the productive half of the loop the reader already runs on
the input side: the curator arranges for saved words to be *met* again, here
the tutor arranges for them to be *used* again out loud.

Correction is a separate pass with its own prompt, not a field bolted onto the
reply. Conversation and error analysis are different jobs and a 4B model does
each one better when asked for one at a time; the two run concurrently, so this
costs latency only if the local runtime refuses to overlap them.
"""
from __future__ import annotations

import re
import time

import requests

from . import config
from server import cache, dictionary, prompts

MODES = ("free", "topic", "doc")

# ------------------------------------------------------------------ context


def passage(doc_id: str, para: int | None = None, span: int = 4) -> dict:
    """The stretch of document the conversation is about.

    Anchored on the reading head — where the voice actually got to — because
    that is what "what you just read" means from the learner's side.
    """
    doc = cache.get_doc(doc_id)
    if not doc:
        raise KeyError("document not found")
    paras = [p.get("text", "") for p in doc["paragraphs"] if p.get("text", "").strip()]
    if not paras:
        raise KeyError("document has no text")

    if para is None:
        para = int(cache.get_progress(doc_id).get("para", 0))
    para = max(0, min(para, len(paras) - 1))

    start = max(0, para - 1)
    picked: list[str] = []
    words = 0
    i = start
    while i < len(paras) and words < config.PASSAGE_WORDS and len(picked) < span + 2:
        picked.append(paras[i])
        words += len(paras[i].split())
        i += 1

    return {"doc_id": doc_id, "title": doc.get("title", ""), "para": para,
            "from": start, "to": i - 1, "paras": picked,
            "text": "\n\n".join(picked), "words": words, "total": len(paras)}


def target_words(limit: int | None = None) -> list[str]:
    """Words the learner saved and has not marked known, freshest first."""
    limit = limit or config.TARGET_WORDS
    rows = [v for v in cache.list_vocab(400) if not v.get("known")]
    rows.sort(key=lambda v: (v.get("last") or v.get("ts") or 0), reverse=True)
    seen, out = set(), []
    for v in rows:
        w = (v.get("word") or "").strip().lower()
        if w and w not in seen and w.isalpha() and len(w) > 2:
            seen.add(w)
            out.append(w)
        if len(out) >= limit:
            break
    return out


_SUFFIX = r"(?:s|es|ed|d|ing|ly|er|ers|ion|ions|al)?"


def used_words(text: str, words: list[str]) -> list[str]:
    """Which target words appear in a turn, tolerating ordinary inflections."""
    if not text or not words:
        return []
    low = text.lower()
    hits, missed = [], []
    for w in words:
        stem = w[:-1] if w.endswith("e") and len(w) > 4 else w
        if re.search(rf"\b{re.escape(stem)}{_SUFFIX}\b", low):
            hits.append(w)
        else:
            missed.append(w)
    if missed:
        bases = {dictionary.base_form(t) for t in set(re.findall(r"[a-z']+", low))}
        hits.extend(w for w in missed if w in bases)
    return hits


# ------------------------------------------------------------------ model
def llm_alive() -> bool:
    try:
        requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def llm_info() -> dict:
    if config.DEV:
        return {"available": True, "model": "dev", "reason": ""}
    ok = llm_alive()
    return {"available": ok, "model": config.LLM_MODEL,
            "reason": "" if ok else "Ollama is not answering — start it and reload"}


def _chat(messages: list[dict], temperature: float = 0.6, predict: int = 220,
          timeout: int = 180) -> str:
    r = requests.post(f"{config.OLLAMA_URL}/api/chat",
                      json={"model": config.LLM_MODEL, "stream": False,
                            "options": {"temperature": temperature, "num_ctx": 4096,
                                        "num_predict": predict},
                            "messages": messages},
                      timeout=timeout)
    r.raise_for_status()
    out = r.json().get("message", {}).get("content", "").strip()
    if "</think>" in out:
        out = out.split("</think>")[-1].strip()
    return out


# ------------------------------------------------------------------ the tutor
# The words the tutor is given live in prompts/ (tutor.*.en.txt) so they can be
# read and tuned without touching code. English is always the tutor's voice; the
# learner asks for an Arabic (or Chinese) hint per message with the hint button.


def _system(mode: str, ctx: dict | None, topic: str, words: list[str]) -> str:
    if mode == "doc" and ctx:
        head = prompts.load("tutor.ground_doc.en", passage=ctx["text"][:6000])
    elif mode == "topic":
        head = prompts.load("tutor.ground_topic.en", topic=topic[:300])
    else:
        head = prompts.load("tutor.ground_free.en")
    rules = prompts.load("tutor.en", level=config.LEVEL,
                         vocab=", ".join(words) or "(none saved yet)")
    return head + "\n\n" + rules


def _one_line(raw: str) -> str:
    line = ""
    for ln in raw.splitlines():
        s = ln.strip()
        if s.upper().startswith("REPLY:"):
            line = s[6:].strip()
            break
    if not line:
        line = re.sub(r"^\s*REPLY\s*:", "", raw.strip(), flags=re.I).strip()
        line = line.split("\n")[0].strip()
    return re.sub(r"[*_`#]", "", line).strip()[:900]


def _dev_open(mode: str, ctx: dict | None, topic: str) -> str:
    if mode == "doc" and ctx:
        return (f"So this section is about {ctx['title'] or 'the topic'}. "
                "What do you think its main claim is?")
    if mode == "topic":
        return f"Alright, {topic}. What got you interested in it?"
    return "No agenda then. What have you been chewing on this week?"


def _dev_reply(history: list[dict], words: list[str]) -> str:
    n = len([h for h in history if h["role"] == "learner"])
    w = words[n % len(words)] if words else "argument"
    canned = [
        f"That is a fair reading, though it leans on the {w} more than you said. "
        "Why do you think it holds?",
        "Fine, but you skipped the part that would make it fail. Where would it fail?",
        f"Right. Say more about the {w} — what would change your mind about it?",
    ]
    return canned[n % len(canned)]


def open_turn(mode: str, ctx: dict | None, topic: str, words: list[str]) -> str:
    if config.DEV:
        return _dev_open(mode, ctx, topic)
    opener = prompts.load(f"tutor.open_{mode if mode in MODES else 'free'}.en")
    msgs = [{"role": "system", "content": _system(mode, ctx, topic, words)},
            {"role": "user", "content": opener}]
    return _one_line(_chat(msgs, temperature=0.75))


def reply(mode: str, ctx: dict | None, topic: str, words: list[str],
          history: list[dict], said: str) -> str:
    if config.DEV:
        return _dev_reply(history + [{"role": "learner", "text": said}], words)
    msgs = [{"role": "system", "content": _system(mode, ctx, topic, words)}]
    for h in history[-config.TURNS_KEPT:]:
        msgs.append({"role": "assistant" if h["role"] == "tutor" else "user",
                     "content": h["text"]})
    msgs.append({"role": "user", "content": said})
    return _one_line(_chat(msgs))


# ------------------------------------------------------------------ the coach
# prompts/correction.en.txt; the rule explanation is one English sentence and the
# Arabic/Chinese version is the opt-in hint (prompts/correction.hint_*.txt).


def coach(said: str) -> dict:
    """`{fixed, why}`, empty when the sentence was fine as spoken."""
    said = (said or "").strip()
    if len(said.split()) < 3:
        return {"fixed": "", "why": ""}
    if config.DEV:
        if "passage" in said.lower():
            return {"fixed": "I think the passage *is* mainly about how the method works.",
                    "why": "A subject needs a verb: add the missing verb 'is'."}
        return {"fixed": "", "why": ""}
    try:
        raw = _chat([{"role": "user", "content": prompts.load("correction.en", said=said[:600])}],
                    temperature=0.1, predict=160, timeout=90)
    except Exception:
        return {"fixed": "", "why": ""}
    if not raw.strip() or raw.strip().upper().startswith("OK"):
        return {"fixed": "", "why": ""}
    fixed, why = "", ""
    for ln in raw.splitlines():
        s = ln.strip()
        if s.upper().startswith("FIXED:"):
            fixed = s[6:].strip()
        elif s.upper().startswith("WHY:"):
            why = s[4:].strip()
    if not fixed:
        return {"fixed": "", "why": ""}
    # a "correction" identical to the original is the model hedging; drop it
    norm = lambda t: re.sub(r"[*\s.,!?'\"]", "", t).lower()   # noqa: E731
    if norm(fixed) == norm(said):
        return {"fixed": "", "why": ""}
    return {"fixed": fixed[:400], "why": why[:300]}


def stamp() -> float:
    return time.time()
