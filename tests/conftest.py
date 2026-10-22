"""Shared fixtures.

The server reads its data directory at import time, so the whole session runs
against a throw-away PR_DATA and no test can touch a real user's caches.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SESSION_DATA = tempfile.mkdtemp(prefix="lumen-test-")
os.environ["PR_DATA"] = _SESSION_DATA
os.environ.setdefault("PR_NO_OPEN", "1")
os.environ.setdefault("PR_DEV", "1")        # the tone-generator voice, so no model is needed

import pytest  # noqa: E402


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """A fresh database, document folder and settings file for one test."""
    from server import cache, config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "reader.db")
    monkeypatch.setattr(config, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    (tmp_path / "docs").mkdir()
    monkeypatch.setattr(cache._local, "conn", None, raising=False)
    yield tmp_path
    c = getattr(cache._local, "conn", None)
    if c is not None:
        c.close()
        cache._local.conn = None


@pytest.fixture()
def client(isolated):
    from fastapi.testclient import TestClient
    from server.main import app
    return TestClient(app)


def make_pdf(path: Path, pages: list[list[str]], title: str = "Test document") -> Path:
    """A real PDF with one list of paragraphs per page."""
    import pymupdf
    doc = pymupdf.open()
    for paras in pages:
        page = doc.new_page()
        y = 72
        for text in paras:
            rect = pymupdf.Rect(72, y, 523, y + 90)
            page.insert_textbox(rect, text, fontsize=11, fontname="helv")
            y += 100
    doc.set_metadata({"title": title})
    doc.save(str(path))
    doc.close()
    return path


def make_scanned_pdf(path: Path, page_texts: list[str]) -> Path:
    """A PDF whose pages are pictures of text, so there is no text layer."""
    import io

    import pymupdf
    from PIL import Image, ImageDraw, ImageFont

    doc = pymupdf.open()
    font = None
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/opentype/inter/Inter-Regular.otf"):
        if Path(cand).exists():
            font = ImageFont.truetype(cand, 34)
            break
    font = font or ImageFont.load_default()
    for text in page_texts:
        img = Image.new("RGB", (1240, 1000), "white")
        d = ImageDraw.Draw(img)
        y = 60
        for line in text.split("\n"):
            d.text((60, y), line, fill="black", font=font)
            y += 52
        buf = io.BytesIO()
        img.save(buf, "PNG")
        page = doc.new_page(width=595, height=480)
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(str(path))
    doc.close()
    return path
