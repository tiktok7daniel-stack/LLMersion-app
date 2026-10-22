"""RTL: the stylesheets use CSS logical properties only.

A physical property (left, margin-right, text-align: left …) lays out correctly in
English and wrongly in Arabic, so none may appear in web/style.css or in the CSS
the conversation panel carries inside talk/web/panel.js.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PHYSICAL = [
    (r"(?<![-\w])(?:left|right)\s*:", "left/right"),
    (r"margin-(?:left|right)\s*:", "margin-left/right"),
    (r"padding-(?:left|right)\s*:", "padding-left/right"),
    (r"border-(?:left|right)(?:-\w+)?\s*:", "border-left/right"),
    (r"border-(?:top|bottom)-(?:left|right)-radius", "physical corner radius"),
    (r"text-align\s*:\s*(?:left|right)\b", "text-align left/right"),
    (r"(?<![-\w])float\s*:\s*(?:left|right)", "float"),
    (r"(?<![-\w])clear\s*:\s*(?:left|right)", "clear"),
]


def panel_css() -> str:
    src = (ROOT / "talk" / "web" / "panel.js").read_text(encoding="utf-8")
    start = src.index("const CSS = `") + len("const CSS = `")
    return src[start:src.index("`;", start)]


def lint(css: str) -> list[str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for pat, name in PHYSICAL:
        for m in re.finditer(pat, css):
            line = css[:m.start()].count("\n") + 1
            out.append(f"{name} at css line {line}: {css[m.start():m.start() + 50].strip()!r}")
    return out


def test_reader_stylesheet_is_logical_only():
    assert not lint((ROOT / "web" / "style.css").read_text(encoding="utf-8"))


def test_talk_panel_stylesheet_is_logical_only():
    assert not lint(panel_css())


def test_directional_icons_mirror_in_rtl():
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert re.search(r':root\[dir="rtl"\]\s+\.mirror\s*\{[^}]*scaleX\(-1\)', css)
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for btn in ("prevPara", "prevSent", "nextSent", "nextPara"):
        m = re.search(rf'id="{btn}".*?</button>', html, re.S)
        assert m and 'class="mirror"' in m.group(0), f"{btn} icon is not mirrored in RTL"
    # play / pause is a media symbol and deliberately not mirrored
    assert 'class="mirror"' not in re.search(r'id="play".*?</button>', html, re.S).group(0)


def test_document_direction_is_set_by_one_controller():
    """Only layout.js writes <html dir>; nothing else may."""
    offenders = []
    for p in list((ROOT / "web").rglob("*.js")) + [ROOT / "talk" / "web" / "panel.js"]:
        if p.name == "layout.js":
            continue
        if re.search(r'documentElement\.(?:setAttribute\(["\']dir|dir\s*=)', p.read_text(encoding="utf-8")):
            offenders.append(p.name)
    assert not offenders, f"these files set <html dir> themselves: {offenders}"


def test_reader_content_direction_follows_the_document_not_the_ui():
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "el.dir = p.dir" in js, "each paragraph must carry the document's own direction"
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.tr:lang\(ar\)", css), "Arabic translation text needs its own face"


def test_arabic_and_english_font_stacks_are_bundled():
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    fonts = (ROOT / "web" / "fonts" / "fonts.css").read_text(encoding="utf-8")
    for fam in ("Inter", "Cairo", "Noto Naskh Arabic"):
        assert f'"{fam}"' in css, f"{fam} missing from the font stacks"
        assert f'font-family: "{fam}"' in fonts, f"{fam} is not bundled in fonts.css"
    for url in re.findall(r"url\(\"([^\"]+)\"\)", fonts):
        assert (ROOT / "web" / "fonts" / url).exists(), f"missing font file {url}"
    assert "fonts.googleapis" not in css + fonts + (ROOT / "web" / "index.html").read_text(encoding="utf-8")
