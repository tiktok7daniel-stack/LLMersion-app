"""Optional OCR for scanned PDFs, through Tesseract.

Everything here is optional and degrades quietly: no `pytesseract`, no Tesseract
binary or no language pack just means `status()` says so and the reader tells the
learner what to install, instead of failing. Nothing leaves the machine.

Languages: English (`eng`) always; Arabic (`ara`) when the learner turns on
"Arabic OCR" in Settings *and* the pack is installed. If Arabic was asked for but
the pack is missing we fall back to English-only and say so in the result, rather
than refusing to read the document.
"""
from __future__ import annotations

import io
import re
from typing import Callable, Optional

from . import config

Progress = Callable[[int, int], None]


class OCRUnavailable(RuntimeError):
    """Tesseract (or its English pack) is not usable. `code` is an i18n key suffix."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def _tess():
    try:
        import pytesseract
    except ImportError as exc:
        raise OCRUnavailable("no_pytesseract", "pip install pytesseract pillow") from exc
    if config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    return pytesseract


def status() -> dict:
    """{available, langs, has_eng, has_ara, version, reason}; never raises."""
    out = {"available": False, "langs": [], "has_eng": False, "has_ara": False,
           "version": "", "reason": ""}
    try:
        t = _tess()
        out["version"] = str(t.get_tesseract_version())
        langs = sorted(t.get_languages(config=""))
    except OCRUnavailable as exc:
        out["reason"] = exc.code
        return out
    except Exception as exc:  # noqa: BLE001 — TesseractNotFoundError and friends
        out["reason"] = "no_tesseract"
        out["detail"] = f"{type(exc).__name__}"
        return out
    out.update(langs=langs, has_eng="eng" in langs, has_ara="ara" in langs)
    out["available"] = out["has_eng"]
    if not out["has_eng"]:
        out["reason"] = "no_eng_pack"
    return out


def choose_langs(arabic: bool, st: Optional[dict] = None) -> tuple[str, str]:
    """(tesseract `lang` string, note) — note is '' or 'ara_missing'."""
    st = st or status()
    if not st["available"]:
        raise OCRUnavailable(st["reason"] or "no_tesseract")
    if arabic and st["has_ara"]:
        return "eng+ara", ""
    return "eng", ("ara_missing" if arabic else "")


def recognize(png: bytes, lang: str) -> str:
    """OCR one page image. A seam: tests replace this."""
    from PIL import Image
    t = _tess()
    with Image.open(io.BytesIO(png)) as img:
        return t.image_to_string(img, lang=lang, config="--psm 3")


def ocr_pages(path: str, pages: list[int], lang: str,
              progress: Optional[Progress] = None) -> dict[int, str]:
    """Render and recognise the given 0-based pages. Returns {page: text}."""
    try:
        import pymupdf as fitz
    except ImportError:                                    # pragma: no cover
        import fitz
    doc = fitz.open(path)
    out: dict[int, str] = {}
    try:
        for n, pno in enumerate(pages):
            if progress:
                progress(n, len(pages))
            pix = doc[pno].get_pixmap(dpi=config.OCR_DPI)
            out[pno] = recognize(pix.tobytes("png"), lang)
        if progress:
            progress(len(pages), len(pages))
    finally:
        doc.close()
    return out


# ------------------------------------------------------------------ text -> paragraphs
_HYPHEN = re.compile(r"([A-Za-z])-\n([a-z])")
_SENT_END = ".!?:;؟۔…\"'”)"


def paragraphs_from_text(page: int, text: str) -> list[dict]:
    """Tesseract separates paragraphs with blank lines; rebuild reflowed ones."""
    from .pdf_parse import _clean
    text = _HYPHEN.sub(r"\1\2", text.replace("\r", ""))
    out = []
    for chunk in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        if not lines:
            continue
        body = _clean(" ".join(lines))
        if len(body) < 2:
            continue
        letters = sum(ch.isalpha() for ch in body)
        if letters / max(1, len(body.replace(" ", ""))) < 0.5:
            kind = "other"                     # page numbers, rules, stray marks
        elif len(lines) == 1 and len(body) < 90 and body[-1] not in _SENT_END:
            kind = "heading"
        else:
            kind = "body"
        out.append({"page": page, "kind": kind, "text": body, "bbox": None})
    return out
