"""PDF import: per-page extraction, page boundaries, hash cache, OCR and its fallbacks."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from conftest import make_pdf, make_scanned_pdf
from server import cache, config, loaders, ocr, pdf_parse

P1 = ["Light travels faster than sound. This is why lightning is seen before thunder is heard."]
P2 = ["Reading every day builds vocabulary. Short sessions work better than long ones."]
P3 = ["The final page explains how to review new words before you go to sleep."]


@pytest.fixture()
def three_page_pdf(tmp_path):
    return make_pdf(tmp_path / "doc.pdf", [P1, P2, P3], title="Learning notes")


def upload(client, path: Path, **form):
    with open(path, "rb") as fh:
        return client.post("/api/open", files={"file": (path.name, fh, "application/pdf")}, data=form)


def test_text_is_extracted_per_page_with_page_numbers(three_page_pdf):
    parsed = loaders.load(three_page_pdf, "doc.pdf")
    pages = sorted({p["page"] for p in parsed["paragraphs"]})
    assert pages == [0, 1, 2], "page boundaries must be preserved"
    assert parsed["pages"] == 3 and parsed["title"] == "Learning notes"
    by_page = {p["page"]: p["text"] for p in parsed["paragraphs"]}
    assert "lightning" in by_page[0] and "vocabulary" in by_page[1] and "sleep" in by_page[2]
    assert all(p["dir"] == "ltr" for p in parsed["paragraphs"])
    assert parsed["meta"]["lang"] == "en"


def test_pdf_page_char_counts(three_page_pdf):
    assert all(n > 40 for n in pdf_parse.page_char_counts(str(three_page_pdf)))


def test_open_endpoint_returns_sentences_and_progress(client, three_page_pdf):
    r = upload(client, three_page_pdf)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pages"] == 3 and len(d["doc_id"]) == 16
    assert all(p["sents"] for p in d["paragraphs"])
    assert d["progress"] == {"para": 0, "sent": 0}


def test_text_is_cached_by_document_hash(client, three_page_pdf, monkeypatch):
    first = upload(client, three_page_pdf).json()
    real_load = loaders.load
    calls = []
    monkeypatch.setattr(loaders, "load", lambda *a, **k: (calls.append(1), real_load(*a, **k))[1])
    again = upload(client, three_page_pdf).json()
    assert not calls, "an identical file must not be parsed again"
    assert again["doc_id"] == first["doc_id"]
    # a different file gets a different hash
    other = make_pdf(three_page_pdf.parent / "other.pdf", [P2])
    assert upload(client, other).json()["doc_id"] != first["doc_id"]
    assert calls


def test_cached_documents_survive_a_restart_of_the_connection(isolated, three_page_pdf):
    parsed = loaders.load(three_page_pdf, "doc.pdf")
    cache.put_doc("abc", parsed["title"], parsed["pages"], parsed["meta"], parsed["paragraphs"])
    assert cache.get_doc("abc")["paragraphs"][0]["page"] == 0
    assert cache.clear_docs()["docs"] == 1
    assert cache.get_doc("abc") is None


def test_unsupported_extension_is_a_localisable_error(client, tmp_path):
    f = tmp_path / "x.exe"
    f.write_bytes(b"nope")
    r = client.post("/api/open", files={"file": ("x.exe", f.read_bytes())})
    assert r.status_code == 400
    assert r.json()["detail"]["key"] == "err.unsupported_type"


# ---------------------------------------------------------------- scanned PDFs / OCR
SCAN1 = "Light travels faster than sound.\nThat is why we see lightning first."
SCAN2 = "Practice a little every day.\nShort sessions work best."


@pytest.fixture()
def scanned_pdf(tmp_path):
    return make_scanned_pdf(tmp_path / "scan.pdf", [SCAN1, SCAN2])


def test_scanned_pdf_is_detected(scanned_pdf):
    assert loaders.pdf_ocr_pages(scanned_pdf) == [0, 1]


def test_scanned_pdf_with_ocr_off_gives_a_clear_error(client, scanned_pdf):
    client.post("/api/settings", json={"ocr_enabled": False})
    r = upload(client, scanned_pdf)
    assert r.status_code == 400
    assert r.json()["detail"]["key"] == "err.ocr_disabled"


def test_scanned_pdf_without_tesseract_falls_back_gracefully(client, scanned_pdf, monkeypatch):
    monkeypatch.setattr(ocr, "status", lambda: {"available": False, "reason": "no_tesseract",
                                                "langs": [], "has_eng": False, "has_ara": False, "version": ""})
    r = upload(client, scanned_pdf)
    assert r.status_code == 400
    assert r.json()["detail"]["key"] == "err.ocr_no_tesseract"


def test_mixed_pdf_reads_the_text_pages_when_ocr_is_unavailable(tmp_path, monkeypatch):
    """One scanned page in a text PDF must not stop the rest being read."""
    import pymupdf
    base = make_pdf(tmp_path / "t.pdf", [P1, P2])
    doc = pymupdf.open(str(base))
    doc.new_page()                                   # a blank page: no text layer
    doc.save(str(tmp_path / "mixed.pdf"))
    monkeypatch.setattr(ocr, "status", lambda: {"available": False, "reason": "no_tesseract",
                                                "langs": [], "has_eng": False, "has_ara": False, "version": ""})
    parsed = loaders.load(tmp_path / "mixed.pdf", "mixed.pdf", loaders.OcrOptions(enabled=True))
    assert sorted({p["page"] for p in parsed["paragraphs"]}) == [0, 1]
    assert parsed["meta"]["ocr"]["skipped"] == [2] and parsed["meta"]["ocr"]["note"] == "no_tesseract"


def _fake_status(has_ara):
    return lambda: {"available": True, "reason": "", "langs": ["eng"] + (["ara"] if has_ara else []),
                    "has_eng": True, "has_ara": has_ara, "version": "5.x"}


def test_ocr_job_reports_progress_and_builds_a_session(client, scanned_pdf, monkeypatch):
    monkeypatch.setattr(ocr, "status", _fake_status(False))
    texts = iter(["First page heading\n\nLight travels faster than sound.\nWe see lightning first.",
                  "Second page.\n\nPractice a little every day."])
    monkeypatch.setattr(ocr, "recognize", lambda png, lang: next(texts))
    r = upload(client, scanned_pdf)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "job" in body and body["job"]["total"] == 2
    for _ in range(100):
        j = client.get(f"/api/job/{body['job']['id']}").json()
        if j["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["state"] == "done", j
    assert (j["done"], j["total"]) == (2, 2), "progress must reach the last page"
    doc = client.get(f"/api/doc/{j['result']['doc_id']}").json()
    assert sorted({p["page"] for p in doc["paragraphs"]}) == [0, 1]
    assert doc["meta"]["ocr"]["used"] and doc["meta"]["ocr"]["lang"] == "eng"
    assert any("lightning" in p["text"] for p in doc["paragraphs"])
    assert all(p["sents"] for p in doc["paragraphs"])


def test_arabic_ocr_uses_ara_pack_when_installed_and_falls_back_when_not(client, scanned_pdf, monkeypatch):
    langs = []
    monkeypatch.setattr(ocr, "recognize", lambda png, lang: (langs.append(lang), "Some text here.")[1])
    client.post("/api/settings", json={"ocr_arabic": True})
    monkeypatch.setattr(ocr, "status", _fake_status(True))
    assert ocr.choose_langs(True) == ("eng+ara", "")
    monkeypatch.setattr(ocr, "status", _fake_status(False))
    assert ocr.choose_langs(True) == ("eng", "ara_missing")
    assert ocr.choose_langs(False) == ("eng", "")
    parsed = loaders.load(scanned_pdf, "scan.pdf", loaders.OcrOptions(enabled=True, arabic=True))
    assert langs and set(langs) == {"eng"}
    assert parsed["meta"]["ocr"]["note"] == "ara_missing"


def test_ocr_paragraph_rebuilding():
    paras = ocr.paragraphs_from_text(3, "Chapter One\n\nThe quick brown fox jumps\nover the lazy dog.\n\n42\n")
    assert [p["kind"] for p in paras] == ["heading", "body", "other"]
    assert paras[1]["text"] == "The quick brown fox jumps over the lazy dog."
    assert all(p["page"] == 3 for p in paras)


@pytest.mark.skipif(not ocr.status()["available"], reason="Tesseract with the eng pack is not installed")
def test_real_tesseract_reads_a_scanned_page(scanned_pdf):
    parsed = loaders.load(scanned_pdf, "scan.pdf", loaders.OcrOptions(enabled=True))
    text = " ".join(p["text"] for p in parsed["paragraphs"]).lower()
    assert "light" in text and "sound" in text
    assert sorted({p["page"] for p in parsed["paragraphs"]}) == [0, 1]


def test_arabic_document_is_marked_rtl_and_not_spoken(tmp_path):
    f = tmp_path / "ar.txt"
    f.write_text("مرحبا بكم في هذا الدرس.\n\nنتعلم اليوم كلمات جديدة كثيرة ومفيدة.\n\n"
                 "This line is English and stays left to right.", encoding="utf-8")
    parsed = loaders.load(f, "ar.txt")
    kinds = [(p["kind"], p["dir"]) for p in parsed["paragraphs"]]
    assert kinds[0] == ("ar", "rtl") and kinds[1] == ("ar", "rtl")
    assert kinds[2] == ("body", "ltr")
    assert parsed["meta"]["lang"] == "ar"        # most paragraphs are Arabic
    g = tmp_path / "en.txt"
    g.write_text("The first paragraph is in English.\n\nThe second one is too.\n\nمرحبا بكم.", encoding="utf-8")
    assert loaders.load(g, "en.txt")["meta"]["lang"] == "en"
