"""i18n: both languages are complete, and the UI only uses keys that exist.

A key missing from en.json or ar.json fails the build, as does a placeholder that
differs between the two, an untranslated string, or any literal text in the HTML.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "web" / "i18n"
PLURAL = re.compile(r"_(zero|one|two|few|many|other)$")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
ARABIC = re.compile(r"[؀-ۿ]")

# strings that are legitimately identical in both languages
SAME_IN_BOTH = {"app.title", "lang.en", "lang.ar"}


def load(name: str) -> dict:
    return json.loads((I18N / f"{name}.json").read_text(encoding="utf-8"))


def base_key(k: str) -> str:
    return PLURAL.sub("", k)


EN, AR = load("en"), load("ar")


def test_both_files_exist_and_are_flat_string_maps():
    for name, d in (("en", EN), ("ar", AR)):
        assert d, f"{name}.json is empty"
        for k, v in d.items():
            assert isinstance(v, str) and v.strip(), f"{name}.json: {k} is empty or not a string"


def test_key_parity_en_ar():
    """Every key exists in both files. Plural variants may differ (Arabic has six
    plural forms, English two) but each plural group must exist in both."""
    en, ar = {base_key(k) for k in EN}, {base_key(k) for k in AR}
    assert not en - ar, f"missing from ar.json: {sorted(en - ar)}"
    assert not ar - en, f"missing from en.json: {sorted(ar - en)}"
    plain_en = {k for k in EN if not PLURAL.search(k)}
    plain_ar = {k for k in AR if not PLURAL.search(k)}
    assert plain_en == plain_ar


def test_every_plural_group_has_an_other_form():
    for name, d in (("en", EN), ("ar", AR)):
        groups: dict[str, set[str]] = {}
        for k in d:
            m = PLURAL.search(k)
            if m:
                groups.setdefault(base_key(k), set()).add(m.group(1))
        for g, forms in groups.items():
            assert "other" in forms, f"{name}.json: {g} has plural forms but no _other"
        if name == "ar":
            for g, forms in groups.items():
                assert {"one", "two", "few", "many", "other"} <= forms, \
                    f"ar.json: {g} needs all of one/two/few/many/other, has {sorted(forms)}"


def test_placeholders_match_between_languages():
    def grouped(d):
        out: dict[str, set[str]] = {}
        for k, v in d.items():
            out.setdefault(base_key(k), set()).update(PLACEHOLDER.findall(v))
        return out
    en, ar = grouped(EN), grouped(AR)
    for k in en:
        assert en[k] == ar[k], f"{k}: placeholders differ en={sorted(en[k])} ar={sorted(ar[k])}"


def test_arabic_is_actually_translated():
    same = [k for k in EN if k in AR and EN[k] == AR[k] and k not in SAME_IN_BOTH]
    assert not same, f"ar.json repeats the English text for: {same}"
    # prose keys must contain Arabic script (technical ones are mostly Latin)
    for k, v in AR.items():
        if len(v) > 25 and not k.startswith("about.upstream"):
            assert ARABIC.search(v), f"ar.json: {k} contains no Arabic: {v!r}"


def test_markup_in_strings_is_limited_to_bold():
    for name, d in (("en", EN), ("ar", AR)):
        for k, v in d.items():
            tags = set(re.findall(r"</?(\w+)", v))
            assert tags <= {"b"}, f"{name}.json: {k} uses markup other than <b>: {tags}"


def test_exact_tagline_and_subtitle():
    assert EN["app.tagline"] == "Read. Listen. Speak. Understand."
    assert EN["app.subtitle"] == "Learn English by listening, speaking, and reading."
    assert AR["app.tagline"] == "اقرأ. استمع. تحدث. افهم."
    assert AR["app.subtitle"] == "تعلّم الإنجليزية بالاستماع والتحدث والقراءة."


# --------------------------------------------------------------- keys used by the code
CODE_FILES = [ROOT / "web" / "index.html", ROOT / "web" / "app.js",
              ROOT / "web" / "js" / "header.js", ROOT / "web" / "js" / "settings.js",
              ROOT / "web" / "js" / "talk-loader.js", ROOT / "web" / "js" / "i18n.js",
              ROOT / "talk" / "web" / "panel.js", ROOT / "talk" / "web" / "index.html"]
NAMESPACES = ("app|a11y|common|lang|header|empty|keys|reader|transport|pop|open|ocr|tr|voice|"
              "vocab|flash|score|hint|write|simplify|settings|about|onboard|boot|err|talk")
LITERAL = re.compile(rf'["\']((?:{NAMESPACES})\.[a-z0-9_]+)["\']')
ATTR = re.compile(rf'(?:data-i18n="|(?:title|aria-label|placeholder):)((?:{NAMESPACES})\.[a-z0-9_]+)')
# keys built at run time: template -> the values it can take
DYNAMIC = {
    "header.translation_": ["ar", "zh"],
    "hint.lang_": ["ar", "zh"],
    "settings.ocr_": ["no_tesseract", "no_pytesseract", "no_eng_pack"],
    "about.role_": ["translation", "voice", "speech", "pronunciation", "tutor", "ocr", "dictionary"],
    "err.ocr_": ["disabled", "no_tesseract", "no_pytesseract", "no_eng_pack", "empty", "failed"],
}


def used_keys() -> set[str]:
    keys: set[str] = set()
    for f in CODE_FILES:
        text = f.read_text(encoding="utf-8")
        keys |= set(LITERAL.findall(text)) | set(ATTR.findall(text))
        for part in re.findall(r'data-i18n-attr="([^"]+)"', text):
            keys |= {p.split(":", 1)[1].strip() for p in part.split(";") if ":" in p}
    for prefix, values in DYNAMIC.items():
        keys |= {prefix + v for v in values}
    # error keys raised by the server
    for f in list((ROOT / "server").glob("*.py")) + list((ROOT / "talk").glob("*.py")):
        keys |= set(re.findall(r'["\'](err\.[a-z0-9_]+)["\']', f.read_text(encoding="utf-8")))
    return keys


def test_every_key_the_code_uses_exists_in_both_languages():
    en, ar = {base_key(k) for k in EN}, {base_key(k) for k in AR}
    used = {base_key(k) for k in used_keys()}
    assert used, "found no keys — the scanner is broken"
    missing_en = sorted(used - en)
    missing_ar = sorted(used - ar)
    assert not missing_en, f"used but not in en.json: {missing_en}"
    assert not missing_ar, f"used but not in ar.json: {missing_ar}"


def test_no_orphan_keys():
    """Keys nothing uses are dead weight; delete them (or add them to DYNAMIC)."""
    used = {base_key(k) for k in used_keys()}
    # keys passed to helpers by name rather than literal, e.g. L(el, "talk.mode_topic")
    text = "\n".join(f.read_text(encoding="utf-8") for f in CODE_FILES)
    orphans = [k for k in {base_key(k) for k in EN}
               if k not in used and f'"{k}"' not in text and f"'{k}'" not in text]
    assert not orphans, f"unused keys: {sorted(orphans)}"


# --------------------------------------------------------------- no literal text in markup
class TextFinder(HTMLParser):
    VOID = {"input", "img", "br", "meta", "link", "hr"}
    SKIP = {"script", "style", "title", "kbd", "svg", "path", "circle", "output", "bdi"}

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, bool]] = []     # (tag, covered by i18n / exempt)
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        exempt = ("data-i18n" in a or a.get("translate") == "no" or tag in self.SKIP
                  or (self.stack and self.stack[-1][1]))
        if tag not in self.VOID:
            self.stack.append((tag, bool(exempt)))
        for name in ("title", "placeholder", "aria-label", "alt"):
            if name in a and a[name].strip() and "data-i18n-attr" not in a:
                self.found.append(f"<{tag} {name}={a[name]!r}>")

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_data(self, data):
        text = data.strip()
        if not text or (self.stack and self.stack[-1][1]):
            return
        if re.search(r"[A-Za-z؀-ۿ一-鿿]", text):
            self.found.append(text)


def test_index_html_has_no_literal_text():
    p = TextFinder()
    p.feed((ROOT / "web" / "index.html").read_text(encoding="utf-8"))
    assert not p.found, f"literal text in index.html (use data-i18n): {p.found}"


def test_header_template_has_no_literal_text():
    src = (ROOT / "web" / "js" / "header.js").read_text(encoding="utf-8")
    start = src.index("const TEMPLATE = `") + len("const TEMPLATE = `")
    template = src[start:src.index("`;", start)]
    p = TextFinder()
    p.feed(re.sub(r"\$\{[^}]*(?:\{[^}]*\}[^}]*)*\}", "", template))
    assert not p.found, f"literal text in header.js template: {p.found}"


@pytest.mark.parametrize("path", [
    "web/app.js", "web/index.html", "web/style.css", "web/js/header.js", "web/js/settings.js",
    "web/js/layout.js", "web/js/i18n.js", "web/js/flashcards.js", "web/js/talk-loader.js",
    "talk/web/panel.js", "talk/web/index.html"])
def test_no_hardcoded_chinese_in_ui_code(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert not re.search(r"[一-鿿]", text), f"{path} still contains Chinese literals"


@pytest.mark.parametrize("path", ["web/app.js", "web/js/settings.js", "talk/web/panel.js"])
def test_no_english_sentences_assigned_to_the_page(path):
    """textContent / innerHTML / toast must not be fed a sentence literal."""
    text = (ROOT / path).read_text(encoding="utf-8")
    bad = re.findall(r'(?:textContent|innerHTML|placeholder|title)\s*=\s*"([A-Z][a-z]+ [a-z][^"]{3,})"', text)
    assert not bad, f"{path}: hardcoded text assigned to the DOM: {bad}"
