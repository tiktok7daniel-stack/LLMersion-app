"""HTTP API + static frontend."""
from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (cache, config, dictionary, hints, jobs, llm, loaders, ocr as ocr_mod,
               pronounce, settings, textseg, translate, tts, version)

app = FastAPI(title=version.APP_NAME, version=version.__version__)


@app.middleware("http")
async def gate(request, call_next):
    """Optional shared-secret gate, off unless PR_TOKEN is set."""
    if config.TOKEN:
        given = (request.query_params.get("token")
                 or request.headers.get("x-reader-token")
                 or request.cookies.get("reader_token", ""))
        if given != config.TOKEN:
            return JSONResponse({"detail": "bad or missing token"}, status_code=401)
        response = await call_next(request)
        response.set_cookie("reader_token", config.TOKEN, max_age=30 * 86400,
                            samesite="lax")
        return response
    return await call_next(request)
POOL = ThreadPoolExecutor(max_workers=4)
WEB = config.ROOT / "web"


def fail(status: int, key: str, msg: str = "") -> HTTPException:
    """An error the browser can localise: `detail.key` is an i18n key (en.json
    `err.*`), `detail.msg` is the English fallback. Use as `raise fail(...)`."""
    return HTTPException(status, detail={"key": key, "msg": msg or key})


# ------------------------------------------------------------------ meta
@app.get("/api/config")
def api_config() -> dict:
    return {
        "app": {"name": version.APP_NAME, "version": version.__version__},
        "settings": settings.load(),
        "tts": tts.info(),
        "mt": translate.info(),
        "dict": {"available": dictionary.available()},
        "ocr": ocr_mod.status(),
        "speed": settings.get("tts_speed"),
        "speed_range": [config.TTS_SPEED_MIN, config.TTS_SPEED_MAX],
        "unit": config.TTS_UNIT,
        "formats": loaders.EXTENSIONS,
        "gop": pronounce.info(),
    }


@app.get("/api/about")
def api_about() -> dict:
    return version.about()


@app.get("/api/settings")
def api_settings_get() -> dict:
    return settings.load()


@app.post("/api/settings")
def api_settings_set(payload: dict = Body(...)) -> dict:
    """Merge the given keys into the stored settings; unknown keys are ignored."""
    return settings.save(payload)


@app.post("/api/cache/clear")
def api_cache_clear(payload: dict = Body(...)) -> dict:
    """Settings -> Clear translation cache / Clear document cache."""
    what = payload.get("what")
    if what == "translations":
        return {"ok": True, "removed": cache.clear_trans()}
    if what == "documents":
        return {"ok": True, **cache.clear_docs()}
    raise fail(400, "err.bad_request", "what must be 'translations' or 'documents'")


@app.post("/api/rescan")
def api_rescan() -> dict:
    """Re-read models/voices and models/tts after you drop new files in."""
    from .engines import MANAGER as TTS_MANAGER
    from .mt import MANAGER as MT_MANAGER
    TTS_MANAGER._checks.clear()
    MT_MANAGER.refresh()
    return api_config()


@app.post("/api/unit")
def api_unit(payload: dict = Body(...)) -> dict:
    """Switch between paragraph-at-once and sentence-at-a-time synthesis."""
    unit = payload.get("unit", "paragraph")
    if unit not in ("paragraph", "sentence"):
        raise fail(400, "err.bad_request", "unit must be paragraph or sentence")
    config.TTS_UNIT = unit
    return {"ok": True, "unit": unit}


@app.post("/api/tts/unload")
def api_tts_unload() -> dict:
    from .engines import MANAGER as TTS_MANAGER
    TTS_MANAGER.unload_all()
    return {"ok": True}


@app.get("/api/docs")
def api_docs() -> dict:
    return {"items": cache.list_docs()}


# ------------------------------------------------------------------ document
class IngestError(Exception):
    """Reading a file failed in a way the learner can act on."""

    def __init__(self, key: str, msg: str = ""):
        super().__init__(msg or key)
        self.key = key


def _ingest(path: Path, name: str, doc_id: str, opts: loaders.OcrOptions) -> None:
    """Parse `path` and store the result under `doc_id` (the file's hash)."""
    try:
        parsed = loaders.load(path, name, opts)
    except loaders.OCRRequired as exc:
        raise IngestError(f"err.ocr_{exc.code}", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise IngestError("err.read_failed", str(exc)) from exc
    if not parsed["paragraphs"]:
        raise IngestError("err.scanned_pdf" if path.suffix.lower() == ".pdf"
                          else "err.no_text")
    title = parsed["title"] or Path(name).stem
    cache.put_doc(doc_id, title, parsed["pages"], parsed["meta"], parsed["paragraphs"])


def _doc_payload(doc_id: str) -> dict:
    d = cache.get_doc(doc_id)
    if not d:
        raise fail(404, "err.doc_not_found", "Document not found")
    for p in d["paragraphs"]:
        if "sents" not in p:
            p["sents"] = textseg.split_sentences(p["text"])
    d["progress"] = cache.get_progress(doc_id)
    return d


@app.post("/api/open")
async def api_open(file: UploadFile = File(...), ocr: str = Form("")) -> dict:
    """Import a document. Text is extracted once per file hash and cached.

    A scanned PDF is read with OCR in a background job when OCR is switched on in
    Settings: the response is then `{job, doc_id}` and the browser polls
    `/api/job/{id}` for page-by-page progress. Pass `ocr=off` to skip it.
    """
    raw = await file.read()
    name = file.filename or "document.pdf"
    ext = Path(name).suffix.lower()
    if ext not in loaders.LOADERS:
        raise fail(400, "err.unsupported_type",
                   f"Unsupported file type '{ext}'. Supported: {', '.join(loaders.EXTENSIONS)}")
    doc_id = hashlib.sha1(raw).hexdigest()[:16]
    path = config.DOCS_DIR / f"{doc_id}{ext}"
    if not path.exists():
        path.write_bytes(raw)

    cached = cache.get_doc(doc_id)
    stale = cached is not None and cached["meta"].get("parser") != loaders.PARSER_VERSION
    if stale:
        print(f"[open] re-parsing {doc_id}: parser "
              f"{cached['meta'].get('parser')} -> {loaders.PARSER_VERSION}")
    if cached is not None and not stale:
        return _doc_payload(doc_id)

    st = settings.load()
    opts = loaders.OcrOptions(enabled=bool(st["ocr_enabled"]) and ocr != "off",
                              arabic=bool(st["ocr_arabic"]))
    if ext == ".pdf" and opts.enabled and ocr_mod.status()["available"]:
        try:
            blank = loaders.pdf_ocr_pages(path)
        except Exception as exc:  # noqa: BLE001
            raise fail(400, "err.read_failed", str(exc)) from exc
        if blank:
            def run(job: jobs.Job) -> dict:
                opts.progress = lambda done, total: job.progress(done, total, "ocr")
                _ingest(path, name, doc_id, opts)
                return {"doc_id": doc_id}
            job = jobs.start("ocr", run)
            job.total = len(blank)
            return {"job": job.as_dict(), "doc_id": doc_id}

    try:
        _ingest(path, name, doc_id, opts)
    except IngestError as exc:
        raise fail(400, exc.key, str(exc)) from exc
    return _doc_payload(doc_id)


@app.get("/api/job/{job_id}")
def api_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise fail(404, "err.job_not_found", "Unknown or expired job")
    return job.as_dict()


@app.get("/api/doc/{doc_id}")
def api_doc(doc_id: str) -> dict:
    return _doc_payload(doc_id)


@app.get("/api/doc/{doc_id}/file")
def api_doc_file(doc_id: str):
    hit = next(iter(config.DOCS_DIR.glob(f"{doc_id}.*")), None)
    if hit is None:
        raise fail(404, "err.file_not_found", "File not found")
    return FileResponse(hit)


def _speed(value) -> float:
    """Clamp to the supported 0.5x-1.5x range; default is the learner's setting."""
    try:
        v = float(value) if value is not None else float(settings.get("tts_speed"))
    except (TypeError, ValueError):
        v = config.TTS_SPEED
    return min(config.TTS_SPEED_MAX, max(config.TTS_SPEED_MIN, v))


# ------------------------------------------------------------------ tts
@app.post("/api/tts")
def api_tts(payload: dict = Body(...)) -> dict:
    texts: list[str] = [t for t in payload.get("texts", []) if t and t.strip()]
    engine: str = payload.get("engine", "")
    voice: str = payload.get("voice", "")
    speed: float = _speed(payload.get("speed"))
    if not texts:
        return {"items": []}

    def one(t: str) -> dict:
        try:
            return {"ok": True, **tts.render(t, engine, voice, speed)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    return {"items": list(POOL.map(one, texts))}


@app.post("/api/speak")
def api_speak(payload: dict = Body(...)) -> dict:
    """Paragraph-level synthesis: one file per block, with sentence marks."""
    engine: str = payload.get("engine", "")
    voice: str = payload.get("voice", "")
    speed: float = _speed(payload.get("speed"))
    blocks_in: list[dict] = payload.get("blocks", [])

    def one(b: dict) -> dict:
        try:
            return {"ok": True, **tts.render_block(b.get("text", ""), b.get("sents", []),
                                                   engine, voice, speed)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    return {"items": list(POOL.map(one, blocks_in))}


@app.get("/api/audio/{fname}")
def api_audio(fname: str):
    path = (config.AUDIO_DIR / fname).resolve()
    if config.AUDIO_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "Audio not found")
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": "public, max-age=604800"})


# ------------------------------------------------------------------ translation
@app.post("/api/translate")
def api_translate(payload: dict = Body(...)) -> dict:
    """English -> `target` (ar | zh; default: the learner's setting). Cached."""
    texts: list[str] = payload.get("texts", [])
    if not texts:
        return {"items": []}
    try:
        return {"items": translate.translate(texts, payload.get("backend", ""),
                                             payload.get("model", ""),
                                             payload.get("target", ""))}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"items": ["" for _ in texts], "error": str(exc),
                             "error_key": "err.translate_failed"}, status_code=200)


# ------------------------------------------------------------------ dictionary
@app.get("/api/lookup")
def api_lookup(q: str = Query(..., min_length=1, max_length=200),
               target: str = Query("")) -> dict:
    return dictionary.lookup(q, target)


# ------------------------------------------------------------------ progress + vocab
@app.post("/api/progress")
def api_progress(payload: dict = Body(...)) -> dict:
    doc_id = payload.get("doc_id")
    if not doc_id:
        raise fail(400, "err.bad_request", "doc_id required")
    cache.set_progress(doc_id, int(payload.get("para", 0)), int(payload.get("sent", 0)))
    return {"ok": True}


@app.post("/api/writing")
def api_writing(payload: dict):
    """LLM feedback on learner writing, aware of their active vocabulary.

    The feedback is English. An Arabic (or Chinese) hint for the top errors is a
    separate, opt-in call: POST /api/hint {kind: "writing", feedback: ...}.
    """
    text = (payload.get("text") or "").strip()
    if len(text) < 20:
        return {"error_key": "err.write_too_short", "error": "Write a few sentences first."}
    if not llm.available():
        return {"error_key": "err.llm_unavailable", "error": "Ollama is not running."}
    words = [v["word"] for v in cache.list_vocab(200) if not v.get("known")][:30]
    prompt = llm.write_prompt(", ".join(words) or "(none saved yet)", text[:4000])
    try:
        return {"feedback": llm.chat(prompt)}
    except Exception as exc:  # noqa: BLE001
        return {"error_key": "err.llm_failed", "error": exc.__class__.__name__}


@app.post("/api/simplify")
def api_simplify(payload: dict):
    """Re-render one paragraph at an easier difficulty, on request."""
    text = (payload.get("text") or "").strip()
    if not text:
        return {"error_key": "err.bad_request", "error": "empty"}
    if not llm.available():
        return {"error_key": "err.llm_unavailable", "error": "Ollama is not running."}
    try:
        return {"text": llm.chat(llm.simplify_prompt(text[:3000]), temperature=0.2)}
    except Exception as exc:  # noqa: BLE001
        return {"error_key": "err.llm_failed", "error": exc.__class__.__name__}


@app.post("/api/hint")
def api_hint(payload: dict = Body(...)) -> dict:
    """An opt-in hint in the learner's language for one card.

    kind: tutor | correction | pronunciation | writing; lang: ar | zh (default:
    the translation target). The remaining fields are the card's own content.
    """
    kind = payload.get("kind", "")
    ctx = {k: v for k, v in payload.items() if k not in ("kind", "lang")}
    try:
        return hints.make(kind, payload.get("lang", ""), ctx)
    except hints.HintError as exc:
        return {"error_key": exc.key, "error": str(exc)}


@app.post("/api/pronounce")
async def api_pronounce(file: UploadFile = File(...), word: str = Form(...),
                        engine: str = Form(""), voice: str = Form("")) -> dict:
    """Score a recording of `word` against the TTS reference for the same word."""
    ok, why = pronounce.available()
    if not ok:
        raise fail(400, "err.pronounce_unavailable", why)
    user_wav = await file.read()
    ref = tts.render(word, engine, voice, 1.0)
    ref_path = config.AUDIO_DIR / ref["url"].split("/")[-1]
    try:
        result = pronounce.compare(user_wav, ref_path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        raise fail(500, "err.score_failed", str(exc)) from exc
    if result.get("ok"):
        cache.record_score(word, result["score"])
    return result


@app.post("/api/pronounce/unload")
def api_pronounce_unload() -> dict:
    pronounce.unload()
    return {"ok": True}


@app.get("/api/vocab")
def api_vocab_list() -> dict:
    return {"items": cache.list_vocab()}


@app.post("/api/vocab")
def api_vocab_add(payload: dict = Body(...)) -> dict:
    cache.add_vocab(payload["word"], payload.get("zh", ""), payload.get("phonetic", ""),
                    payload.get("context", ""), payload.get("doc_id", ""),
                    payload.get("ar", ""))
    return {"ok": True}


@app.post("/api/vocab/gloss")
def api_vocab_gloss(payload: dict = Body(...)) -> dict:
    """Fill in a saved word's gloss for `lang` if it was saved without one."""
    word = payload["word"]
    lang = payload.get("lang") or translate.current_target()
    d = dictionary.lookup(word, lang)
    cache.set_gloss(word, lang, d.get("gloss", ""))
    return {"word": word, "lang": lang, "gloss": d.get("gloss", ""),
            "phonetic": d.get("phonetic", "")}


@app.post("/api/vocab/review")
def api_vocab_review(payload: dict = Body(...)) -> dict:
    """Grade a flashcard: 0 again, 1 hard, 2 good, 3 easy."""
    return cache.review_vocab(payload["word"], int(payload.get("grade", 2)))


@app.post("/api/vocab/merge")
def api_vocab_merge() -> dict:
    return cache.merge_vocab(dictionary.base_form)


@app.post("/api/vocab/known")
def api_vocab_known(payload: dict = Body(...)) -> dict:
    cache.set_known(payload["word"], int(payload.get("known", 1)))
    return {"ok": True}


@app.get("/api/vocab/export.csv")
def api_vocab_export():
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["word", "phonetic", "arabic", "chinese", "context", "added", "hits", "known"])
    for r in cache.list_vocab():
        w.writerow([r["word"], r["phonetic"], (r.get("ar") or "").replace("\n", " / "),
                    (r["zh"] or "").replace("\n", " / "),
                    r["context"], time.strftime("%Y-%m-%d", time.localtime(r["ts"] or 0)),
                    r["hits"], r["known"]])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="vocab.csv"'})


@app.delete("/api/vocab/{word}")
def api_vocab_del(word: str) -> dict:
    cache.del_vocab(word)
    return {"ok": True}


# ------------------------------------------------------------------ talk
# The conversation module is optional: if talk/ is not there, or its own
# dependencies are missing, the reader loads exactly as before and the button
# in the toolbar hides itself. Mounted before the catch-all below, because the
# first matching mount wins.
TALK_WEB = config.ROOT / "talk" / "web"
HAS_TALK = False
try:
    if TALK_WEB.exists():
        from talk import bridge as talk_bridge
        from talk.api import router as talk_router
        talk_bridge.set_in_process(True)   # voice and scorer are already here
        app.include_router(talk_router)
        app.mount("/talk", StaticFiles(directory=TALK_WEB, html=True), name="talk")
        HAS_TALK = True
except Exception as exc:  # noqa: BLE001
    print(f"[talk] not loaded: {exc.__class__.__name__}: {exc}")


@app.get("/api/talk-available")
def api_talk_available() -> dict:
    return {"available": HAS_TALK}


# ------------------------------------------------------------------ static
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def banner() -> None:
    """Print what is and is not available, so a missing piece is obvious."""
    print(f"\n  {version.APP_NAME} {version.__version__}  ·  Read. Listen. Speak. Understand.")
    print(f"  {'-' * 58}")
    t = tts.info()
    for e in t["engines"]:
        mark = "ok " if e["available"] else "-- "
        detail = f"{e['voices']} voices" if e["available"] else f"{e['reason']}"
        print(f"  {mark}{e['label']:<26} {detail}")
        if not e["available"] and e["notes"]:
            print(f"     {' ' * 26} {e['notes']}")
    d = t["default"]
    print(f"  {'-' * 58}")
    print(f"  voice      {d['label'] + ' (' + d['engine'] + ')' if d else 'NONE — reading will not work'}")
    m = translate.info()
    for target, md in m["defaults"].items():
        name = {"ar": "Arabic", "zh": "Chinese"}.get(target, target)
        if md["model"]:
            print(f"  translate  {name}: {md['model']} via {md['backend']}")
        else:
            why = "; ".join(f"{b['id']}: {b['reason']}" for b in m["backends"]
                            if not b["available"] and target in b["targets"])
            print(f"  translate  {name}: NONE — {why}")
    o = ocr_mod.status()
    print(f"  ocr        {'Tesseract ' + o['version'] + ' (' + ', '.join(l for l in o['langs'] if l in ('eng', 'ara')) + ')' if o['available'] else 'off — scanned PDFs need Tesseract (docs/INSTALL.md)'}")
    print(f"  dictionary {'ECDICT' if dictionary.available() else 'NONE — run tools/build_ecdict.py'}")
    print(f"  talk       {'ready' if HAS_TALK else 'not installed'}")
    print(f"  data       {config.DATA}")
    print(f"  {'-' * 58}")
    where = "127.0.0.1" if config.HOST == "0.0.0.0" else config.HOST
    suffix = f"/?token={config.TOKEN}" if config.TOKEN else ""
    print(f"  http://{where}:{config.PORT}{suffix}")
    if not config.is_local():
        print(f"  bound to {config.HOST} — reachable from other machines"
              + ("" if config.TOKEN else "  ⚠ no PR_TOKEN set"))
        print("  microphone scoring needs HTTPS or an SSH tunnel; see DEPLOY.md")
    print()


def main() -> None:
    import threading
    import uvicorn
    import webbrowser

    banner()
    # a remote host has no browser to open, and no display to open it on
    if os.environ.get("PR_NO_OPEN") != "1" and config.is_local():
        url = f"http://{config.HOST}:{config.PORT}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    # quiet by default; PR_LOG=info shows every request, which is the fastest
    # way to tell "the browser is not talking to me" from "synthesis is slow"
    uvicorn.run(app, host=config.HOST, port=config.PORT,
                log_level=os.environ.get("PR_LOG", "warning"))


if __name__ == "__main__":
    main()
