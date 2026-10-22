"""Logo and brand assets: every size exists, is the right size, and is referenced."""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "web" / "brand"


def test_logo_files_and_sizes():
    assert (BRAND / "logo.svg").exists() and (BRAND / "logo-mark.svg").exists()
    for n in (512, 192, 48, 32):
        with Image.open(BRAND / f"logo-{n}.png") as im:
            assert im.size == (n, n), f"logo-{n}.png is {im.size}"
    with Image.open(BRAND / "apple-touch-icon.png") as im:
        assert im.size == (180, 180)


def test_favicon_ico_holds_16_32_48():
    data = (BRAND / "favicon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    sizes = set()
    for i in range(count):
        w, h = struct.unpack("BB", data[6 + 16 * i:8 + 16 * i])
        sizes.add((w or 256, h or 256))
    assert {(16, 16), (32, 32), (48, 48)} <= sizes


def test_logo_svg_is_flat_textless_and_on_palette():
    svg = (BRAND / "logo.svg").read_text(encoding="utf-8")
    assert "<text" not in svg, "no text inside the icon"
    assert "Gradient" not in svg and "filter" not in svg, "flat shapes only"
    for colour in ("#1D4ED8", "#F59E0B", "#F8FAFC"):
        assert colour in svg
    assert 'viewBox="0 0 512 512"' in svg


def test_manifest_icons_exist_and_name_is_brand():
    m = json.loads((ROOT / "web" / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["name"] == "LumenRead" and m["theme_color"] == "#1D4ED8"
    purposes = {i["purpose"] for i in m["icons"]}
    assert {"any", "maskable"} <= purposes
    for icon in m["icons"]:
        assert (ROOT / "web" / icon["src"].lstrip("/")).exists(), icon["src"]


def test_inline_header_logo_matches_logo_svg():
    """header.js inlines the mark so it can be themed; its shapes must be logo.svg's."""
    svg = (BRAND / "logo.svg").read_text(encoding="utf-8")
    header = (ROOT / "web" / "js" / "header.js").read_text(encoding="utf-8")
    paths = re.findall(r'<path d="([^"]+)"', svg)
    assert len(paths) >= 6
    for d in paths:
        assert d in header, f"header.js is missing logo path {d[:30]}…"


def test_logo_applied_everywhere():
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon" href="/brand/favicon.ico"' in index          # favicon
    assert 'rel="manifest"' in index and "apple-touch-icon" in index
    assert 'id="splash"' in index and "/brand/logo.svg" in index      # splash screen
    assert "<lumen-header>" in index                                   # header component
    header = (ROOT / "web" / "js" / "header.js").read_text(encoding="utf-8")
    assert "LumenRead" in header and "viewBox=\"0 0 512 512\"" in header
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "web/brand/logo" in readme                                  # README


def test_old_product_name_is_gone_from_the_ui():
    """LLMersion may only appear as attribution (About, README, licence)."""
    for rel in ("web/index.html", "web/js/header.js", "web/app.js", "web/i18n/en.json"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        text = re.sub(r"github\.com/QM378/LLMersion|LLMersion[- ]1|LLMersion", "UPSTREAM", text)
        assert "UPSTREAM" not in text or rel in ("web/index.html", "web/i18n/en.json"), rel
    en = json.loads((ROOT / "web" / "i18n" / "en.json").read_text(encoding="utf-8"))
    mentions = [k for k, v in en.items() if "LLMersion" in v]
    assert set(mentions) <= {"about.upstream", "about.upstream_title", "about.license"}, mentions
