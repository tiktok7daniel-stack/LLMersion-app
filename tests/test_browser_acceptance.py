"""End-to-end acceptance in a real browser (Chromium via Playwright).

Starts the actual server in-process with the dev tone voice, a tiny dictionary and
a stand-in translation model, then drives the UI like a learner would: English and
Arabic, RTL, PDF import (text and scanned), read-along, word tap, flashcards,
settings, About. Skipped when Playwright or Chromium is unavailable.

Set LUMEN_SHOTS=<dir> to keep screenshots of every step.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from conftest import ROOT, make_pdf, make_scanned_pdf       # noqa: E402

EN = json.loads((ROOT / "web" / "i18n" / "en.json").read_text(encoding="utf-8"))
AR = json.loads((ROOT / "web" / "i18n" / "ar.json").read_text(encoding="utf-8"))
SHOTS = Path(os.environ["LUMEN_SHOTS"]) if os.environ.get("LUMEN_SHOTS") else None

PAGE1 = ["Light travels faster than sound. This is why lightning is seen before thunder is heard.",
         "A luminous beam can cross a dark room in an instant."]
PAGE2 = ["Reading every day builds vocabulary. Short sessions work better than long ones."]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    import uvicorn

    from server import cache, config, dictionary, ocr
    from server.mt import MANAGER, REGISTRY
    from server.mt.base import MTBackend

    root = tmp_path_factory.mktemp("browser")
    saved = (config.DB_PATH, config.DOCS_DIR, config.SETTINGS_PATH, config.DICT_DB,
             dict(config.MT_PREFS["ar"]), dict(config.MT_PREFS["zh"]))
    config.DB_PATH = root / "reader.db"
    config.DOCS_DIR = root / "docs"
    config.SETTINGS_PATH = root / "settings.json"
    config.DOCS_DIR.mkdir()
    cache._local.conn = None

    # a tiny ECDICT: IPA + English definitions
    db = root / "ecdict.db"
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE entry (word TEXT PRIMARY KEY, phonetic TEXT, definition TEXT, translation TEXT,
                          pos TEXT, collins INTEGER, oxford INTEGER, tag TEXT, bnc INTEGER, frq INTEGER, exchange TEXT);
      CREATE TABLE lemma (form TEXT PRIMARY KEY, base TEXT);
      INSERT INTO entry VALUES ('luminous','ˈluːmɪnəs','giving off light; bright or shining','a. 发光的',
                                '',0,0,'',0,0,'');
      INSERT INTO entry VALUES ('light','laɪt','the natural agent that makes things visible','n. 光',
                                '',0,0,'',0,0,'');
    """)
    c.commit(); c.close()
    config.DICT_DB = db
    dictionary._local.dict = None

    class StandInMT(MTBackend):
        id, label, rank, targets = "standin", "Stand-in MT", 0, ("ar", "zh")

        @classmethod
        def list_models(cls):
            return [{"id": "standin-1", "label": "Stand-in model", "license": "test"}]

        def translate(self, texts, model, target="zh"):
            glossary = {"luminous": "مضيء", "light": "ضوء"}
            return [glossary.get(t.lower(), ("ترجمة: " if target == "ar" else "译文：") + t) for t in texts]

    REGISTRY["standin"] = StandInMT
    MANAGER._checks.clear()
    MANAGER._live.clear()
    config.MT_PREFS["ar"] = {"backend": "standin", "model": "standin-1"}
    config.MT_PREFS["zh"] = {"backend": "standin", "model": "standin-1"}

    from server.main import app
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    files = {
        "text": make_pdf(root / "text.pdf", [PAGE1, PAGE2], title="Notes on light"),
        "scan": make_scanned_pdf(root / "scan.pdf", ["Light travels faster than sound.\nWe see lightning first."]),
    }
    yield {"url": f"http://127.0.0.1:{port}", "files": files, "root": root}
    server.should_exit = True
    t.join(timeout=5)
    REGISTRY.pop("standin", None)
    # leave the process as we found it for the other test modules
    (config.DB_PATH, config.DOCS_DIR, config.SETTINGS_PATH, config.DICT_DB) = saved[:4]
    config.MT_PREFS["ar"], config.MT_PREFS["zh"] = saved[4], saved[5]
    cache._local.conn = None
    dictionary._local.dict = None
    MANAGER._checks.clear()
    MANAGER._live.clear()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        args = ["--autoplay-policy=no-user-gesture-required"]
        # CI images ship their own Chromium; LUMEN_CHROMIUM points at it when the
        # Playwright-managed download is not there (see docs/INSTALL.md)
        exe = os.environ.get("LUMEN_CHROMIUM") or next(
            (str(c) for c in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)
        try:
            b = p.chromium.launch(args=args)
        except Exception:                                         # noqa: BLE001
            try:
                b = p.chromium.launch(args=args, executable_path=exe)
            except Exception as exc:                              # noqa: BLE001
                pytest.skip(f"Chromium is not available: {exc}")
        yield b
        b.close()


@pytest.fixture(scope="module")
def page(browser, site):
    ctx = browser.new_context(locale="en-US", viewport={"width": 1180, "height": 800})
    pg = ctx.new_page()
    pg.errors, pg.requests = [], []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.on("request", lambda r: pg.requests.append(r.url))
    pg.goto(site["url"])
    pg.wait_for_selector("#splash", state="detached", timeout=15000)
    yield pg
    ctx.close()


def shot(page, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"))


def text(page, sel):
    # textContent, not innerText: the latter reflects CSS text-transform
    return (page.text_content(sel) or "").strip()


def set_language(page, pref):
    page.select_option("#langSwitch", pref)
    expected = "ar" if pref == "ar" else "en"
    page.wait_for_function(f"document.documentElement.lang === '{expected}'")
    page.wait_for_timeout(120)


# ------------------------------------------------------------------ the checklist
def test_01_starts_with_lumenread_branding_and_logo(page):
    assert page.title() == EN["app.title"] == "LumenRead"
    assert page.get_attribute("html", "lang") == "en" and page.get_attribute("html", "dir") == "ltr"
    assert text(page, ".brand-name") == "LumenRead"
    assert page.locator("lumen-header svg.logo").count() == 1
    assert page.get_attribute('link[rel="icon"]', "href") == "/brand/favicon.ico"
    assert page.get_attribute('link[rel="manifest"]', "href") == "/manifest.webmanifest"
    assert text(page, ".empty h2") == EN["empty.title"]
    assert text(page, ".empty .empty-sub") == EN["app.subtitle"]
    # logo actually renders (non-empty box)
    box = page.locator("lumen-header svg.logo").bounding_box()
    assert box["width"] >= 28 and box["height"] >= 28


def test_02_onboarding_then_nothing_leaves_the_machine(page, site):
    assert page.is_visible("#onboard")
    shot(page, "01-onboarding-en")
    page.click("#onGo")
    page.wait_for_selector("#onboard", state="hidden")
    hosts = {re.match(r"https?://([^/:]+)", u).group(1) for u in page.requests if u.startswith("http")}
    assert hosts <= {"127.0.0.1"}, f"requests left the machine: {hosts}"
    assert not [e for e in page.errors if "favicon" not in e], page.errors


def test_03_switching_to_arabic_rerenders_everything_and_goes_rtl(page):
    set_language(page, "ar")
    assert page.get_attribute("html", "dir") == "rtl" and page.get_attribute("html", "lang") == "ar"
    assert text(page, ".empty h2") == AR["empty.title"]
    assert text(page, ".empty .empty-sub") == AR["app.subtitle"]
    assert text(page, "#writeBtn") == AR["header.write"]
    assert text(page, "#vocabBtn").startswith(AR["header.vocab"])
    assert page.get_attribute("#settingsBtn", "title") == AR["header.settings"]
    assert page.get_attribute("#langSwitch", "title") == AR["lang.switch"]
    assert text(page, ".brand-name") == "LumenRead", "the brand stays English"
    # the layout is really mirrored: the brand sits on the right, the controls on the left
    brand = page.locator(".brand").bounding_box()
    ctrls = page.locator(".bar-end").bounding_box()
    assert brand["x"] > ctrls["x"], "RTL: the brand must be on the inline-start (right) side"
    shot(page, "02-empty-ar-rtl")


def test_04_directional_icons_are_mirrored_in_rtl_only(page):
    page.evaluate("document.getElementById('transport').hidden = false")
    tf = lambda sel: page.eval_on_selector(sel, "e => getComputedStyle(e).transform")   # noqa: E731
    assert tf("#nextSent svg") == "matrix(-1, 0, 0, 1, 0, 0)"
    assert tf("#prevPara svg") == "matrix(-1, 0, 0, 1, 0, 0)"
    assert tf("#playIcon") == "none", "play/pause is a media symbol and is not mirrored"
    set_language(page, "en")
    assert tf("#nextSent svg") == "none"
    page.evaluate("document.getElementById('transport').hidden = true")


def test_05_every_visible_string_comes_from_the_dictionaries(page):
    """In both languages, every element with data-i18n shows exactly its dictionary text."""
    for lang, d in (("en", EN), ("ar", AR)):
        set_language(page, lang)
        bad = page.evaluate("""(d) => {
            const out = [];
            document.querySelectorAll('[data-i18n]').forEach(e => {
              const k = e.getAttribute('data-i18n');
              if (e.getAttribute('data-i18n-params')) return;
              if (!(k in d) && !(k + '_other' in d)) { out.push('missing ' + k); return; }
              if (k in d && e.textContent !== d[k]) out.push(k + ' -> ' + JSON.stringify(e.textContent));
            });
            return out;
        }""", d)
        assert not bad, f"{lang}: {bad[:8]}"
    set_language(page, "en")


def test_06_pdf_import_extracts_pages_and_shows_translation_under_paragraphs(page, site):
    page.set_input_files("#fileInput", str(site["files"]["text"]))
    page.wait_for_selector(".para .sent", timeout=15000)
    assert text(page, "#docTitle") == "Notes on light"
    assert page.locator(".pagebreak").count() == 2
    assert text(page, ".pagebreak >> nth=0") == "Page 1" and text(page, ".pagebreak >> nth=1") == "Page 2"
    assert page.locator(".para.body").count() == 3
    # Arabic translation appears under the paragraphs although the UI is English
    page.wait_for_function("document.querySelector('.tr') && !document.querySelector('.tr').classList.contains('pending')",
                           timeout=15000)
    tr = page.locator(".tr").first
    assert tr.get_attribute("lang") == "ar" and tr.get_attribute("dir") == "rtl"
    assert "ترجمة" in tr.inner_text()
    assert page.get_attribute(".para.body >> nth=0", "dir") == "ltr", "English paragraphs stay LTR"
    shot(page, "03-reader-en")


def test_07_translation_is_also_shown_in_the_arabic_ui_and_english_text_stays_ltr(page):
    set_language(page, "ar")
    assert page.get_attribute("html", "dir") == "rtl"
    assert page.get_attribute(".para.body >> nth=0", "dir") == "ltr"
    assert page.get_attribute(".para .en >> nth=0", "lang") == "en"
    assert text(page, ".pagebreak >> nth=0") == AR["reader.page_n"].replace("{n}", "1")
    assert page.is_visible(".tr >> nth=0")
    ui_dir = page.eval_on_selector(".para .en", "e => getComputedStyle(e).direction")
    assert ui_dir == "ltr", "reader content follows the document, not the UI language"
    shot(page, "04-reader-ar-rtl")
    set_language(page, "en")


def test_08_toggle_hides_and_shows_the_translation(page):
    page.click("#zhToggle")
    assert not page.is_visible(".tr >> nth=0")
    assert page.get_attribute("#zhToggle", "aria-pressed") == "false"
    page.click("#zhToggle")
    assert page.is_visible(".tr >> nth=0")


def test_09_default_speed_is_slow_and_range_is_half_to_one_and_a_half(page):
    assert page.input_value("#speed") == "0.8"
    values = page.eval_on_selector_all("#speed option", "os => os.map(o => o.value)")
    assert values[0] == "0.5" and values[-1] == "1.5"


def test_10_reading_aloud_highlights_the_sentence(page):
    page.click("#play")
    page.wait_for_selector(".sent.speaking", timeout=20000)
    assert page.get_attribute("#play", "aria-pressed") == "true"
    page.wait_for_timeout(600)
    fill = page.eval_on_selector(".sent.speaking", "e => e.style.getPropertyValue('--fill')")
    assert fill != "", "the pen fill follows the voice"
    shot(page, "05-reading-highlight")
    page.click("#play")
    assert page.get_attribute("#play", "aria-pressed") == "false"


def test_11_page_jump(page):
    page.fill("#pageJump", "2")
    page.press("#pageJump", "Enter")
    page.wait_for_function("document.querySelector('.para.active, .sent') !== null")
    cur = page.evaluate("window.LumenApp.S.units[window.LumenApp.P.idx].pi")
    assert page.evaluate(f"window.LumenApp.S.doc.paragraphs[{cur}].page") == 1
    assert text(page, "#pageTotal") == "2"


def _tap_word(page, word):
    page.evaluate("""(w) => {
        const el = [...document.querySelectorAll('.sent')].find(s => s.textContent.includes(w));
        const node = el.firstChild, i = node.textContent.indexOf(w);
        const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + w.length);
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        document.getElementById('reader').dispatchEvent(new MouseEvent('mouseup', {bubbles: true, detail: 1}));
    }""", word)


def test_12_word_tap_shows_ipa_definition_and_arabic_gloss(page):
    page.click("#zhToggle"); page.click("#zhToggle")          # keep state simple
    _tap_word(page, "luminous")
    page.wait_for_function("document.getElementById('popGloss').textContent.includes('مضيء')", timeout=10000)
    assert page.is_visible("#pop")
    assert text(page, "#popPhon") == "/ˈluːmɪnəs/"
    assert "giving off light" in text(page, "#popDef")
    assert page.get_attribute("#popGloss", "lang") == "ar" and page.get_attribute("#popGloss", "dir") == "rtl"
    assert page.get_attribute("#popDef", "dir") == "ltr"
    shot(page, "06-word-tap")
    page.mouse.click(5, 400)


def test_13_saved_words_become_flashcards_english_front_arabic_back(page):
    page.click("#vocabBtn")
    page.wait_for_selector(".vrow")
    assert "luminous" in text(page, ".vrow .vword")
    page.wait_for_function("document.querySelector('.vrow .vgloss').textContent.includes('مضيء')", timeout=10000)
    shot(page, "07-vocabulary")
    page.click("#flashBtn")
    assert page.is_visible("#flash")
    assert page.get_attribute("#flashWord", "dir") == "ltr" and page.get_attribute("#flashWord", "lang") == "en"
    assert not page.is_visible("#flashBack")
    page.keyboard.press("ArrowDown")
    page.wait_for_selector("#flashBack", state="visible")
    assert page.get_attribute("#flashGlossEl", "lang") == "ar" and page.get_attribute("#flashGlossEl", "dir") == "rtl"
    assert "مضيء" in text(page, "#flashGlossEl")
    shot(page, "08-flashcard-en-ui")
    page.keyboard.press("3")                                   # grade: good
    page.wait_for_function("window.LumenApp.V.items.length > 0")
    page.keyboard.press("Escape")
    page.wait_for_selector("#flash", state="hidden")
    due = page.evaluate("fetch('/api/vocab').then(r => r.json()).then(d => d.items.find(i => i.word === 'luminous').box)")
    assert due == 1, "grading schedules the next review"


def test_14_flashcard_directionality_in_the_arabic_ui(page):
    set_language(page, "ar")
    page.click("#flashBtn")
    assert page.is_visible("#flash")
    assert page.get_attribute("#flashWord", "dir") == "ltr", "English front stays LTR in the Arabic UI"
    keys = text(page, "#flashKeys")
    assert "→" in keys and "←" in keys
    page.keyboard.press("ArrowDown")
    page.wait_for_selector("#flashBack", state="visible")
    assert page.get_attribute("#flashGlossEl", "dir") == "rtl"
    shot(page, "09-flashcard-ar-ui")
    page.click("#flashClose")
    page.click("#closeVocab")
    set_language(page, "en")


def test_15_settings_panel_and_target_switch(page):
    page.evaluate("window.scrollTo(0, 0)")        # translations are lazy: only visible paragraphs are done
    page.click("#settingsBtn")
    assert page.is_visible("#settingsPanel")
    assert page.is_checked("#setShowTr") and page.input_value("#setTarget") == "ar"
    assert page.input_value("#setSpeed") == "0.8"
    assert "Tesseract" in text(page, "#ocrStatus")
    assert page.locator("#mtList .mopt").count() >= 1
    shot(page, "10-settings-en")
    page.select_option("#setTarget", "zh")
    page.wait_for_function("document.querySelector('.tr').lang === 'zh-Hans'")
    page.wait_for_function("document.querySelector('.tr').textContent.startsWith('译文')", timeout=10000)
    assert page.get_attribute(".tr >> nth=0", "dir") == "ltr"
    page.select_option("#setTarget", "ar")
    page.wait_for_function("document.querySelector('.tr').textContent.startsWith('ترجمة')", timeout=10000)
    page.select_option("#setLang", "ar")
    page.wait_for_function("document.documentElement.dir === 'rtl'")
    assert text(page, "#settingsTitle") == AR["settings.title"]
    shot(page, "11-settings-ar")
    page.select_option("#setLang", "en")
    page.wait_for_function("document.documentElement.dir === 'ltr'")
    page.click("#closeSettings")


def test_16_language_and_settings_persist_across_reload(page, site):
    set_language(page, "ar")
    saved = json.loads((site["root"] / "settings.json").read_text(encoding="utf-8"))
    assert saved["ui_lang"] == "ar"
    page.reload()
    page.wait_for_selector("#splash", state="detached", timeout=15000)
    assert page.get_attribute("html", "dir") == "rtl" and page.get_attribute("html", "lang") == "ar"
    assert page.input_value("#langSwitch") == "ar"
    set_language(page, "en")


def test_17_about_is_bilingual_and_keeps_upstream_attribution(page):
    page.click("#settingsBtn"); page.click("#aboutBtn")
    page.wait_for_function("document.querySelectorAll('#aboutModels tr').length > 3")
    assert text(page, "#aboutTitle") == EN["about.title"]
    body = text(page, ".about")
    assert "LLMersion" in body and "MIT" in body and "CC-BY-4.0" in body and "Apache-2.0" in body
    assert page.get_attribute("#aboutRepo", "href") == "https://github.com/QM378/LLMersion"
    assert text(page, "#aboutVer") == "1.0.0"
    shot(page, "12-about-en")
    set_language(page, "ar")
    page.wait_for_function("document.querySelectorAll('#aboutModels tr').length > 3")
    assert text(page, "#aboutTitle") == AR["about.title"]
    assert AR["about.privacy"][:30] in text(page, ".about")
    shot(page, "13-about-ar")
    page.click("#closeAbout"); page.click("#closeSettings")
    set_language(page, "en")


def test_18_dark_theme_and_arabic_rtl_screenshot(page):
    page.select_option("#langSwitch", "ar")
    page.wait_for_function("document.documentElement.dir === 'rtl'")
    page.click("#themeToggle")
    assert page.get_attribute("html", "data-theme") in ("dark", "light")
    page.evaluate("window.LumenApp.applyTheme('dark')")
    assert page.get_attribute("html", "data-theme") == "dark"
    shot(page, "14-reader-ar-dark")
    page.evaluate("window.LumenApp.applyTheme('light')")
    set_language(page, "en")


def test_19_writing_feedback_is_english_with_an_optional_arabic_hint(page, monkeypatch):
    from server import llm
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda p, **k:
                        "استخدم صيغة الماضي: went بدلاً من goed." if "IN ARABIC" in p
                        else "**Corrected version** I went home.\n**Notes** Use the past tense.")
    page.click("#writeBtn")
    page.fill("#writeText", "I goed home yesterday and I am very tired after that long day.")
    page.click("#writeGo")
    page.wait_for_selector("#writeOut", state="visible", timeout=10000)
    assert "Corrected version" in text(page, "#writeOut")
    assert page.get_attribute("#writeOut", "dir") == "ltr" and page.get_attribute("#writeOut", "lang") == "en"
    assert not page.is_visible("#writeHint")
    assert text(page, "#writeHintBtn") == EN["hint.show"].replace("{lang}", EN["hint.lang_ar"])
    page.click("#writeHintBtn")
    page.wait_for_function("document.getElementById('writeHint').textContent.includes('استخدم')", timeout=10000)
    assert page.get_attribute("#writeHint", "dir") == "rtl" and page.get_attribute("#writeHint", "lang") == "ar"
    set_language(page, "ar")
    assert text(page, "#writeHintBtn") == AR["hint.hide"]
    shot(page, "15-writing-hint-ar")
    page.keyboard.press("Escape")
    set_language(page, "en")


def test_20_scanned_pdf_is_read_with_ocr_and_progress(page, site):
    from server import ocr
    if not ocr.status()["available"]:
        pytest.skip("Tesseract is not installed")
    page.set_input_files("#fileInput", str(site["files"]["scan"]))
    page.wait_for_function("document.getElementById('docTitle').textContent !== 'Notes on light'", timeout=60000)
    page.wait_for_selector(".para .sent", timeout=30000)
    body = " ".join(page.eval_on_selector_all(".para .en", "es => es.map(e => e.textContent)")).lower()
    assert "light" in body and "sound" in body
    assert not page.is_visible("#ocrBox")


def test_21_talk_panel_is_localised_with_arabic_hint_buttons(page):
    if not page.is_visible("#talkBtn"):
        pytest.skip("the conversation module is not mounted")
    set_language(page, "ar")
    page.click("#talkBtn")
    page.wait_for_function("!!window.mountTalkPanel")
    page.wait_for_timeout(500)
    got = page.evaluate("""() => {
        const host = [...document.body.children].find(e => e.shadowRoot);
        const win = host.shadowRoot.querySelector('.win');
        return {dir: win.dir, title: host.shadowRoot.querySelector('.title').textContent,
                free: host.shadowRoot.querySelector('.mode').textContent};
    }""")
    assert got["dir"] == "rtl" and got["title"].startswith(AR["talk.title"]) and got["free"] == AR["talk.mode_free"]
    shot(page, "16-talk-ar")
    page.click("#talkBtn")
    set_language(page, "en")
