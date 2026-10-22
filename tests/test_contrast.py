"""Accessibility: text/background pairs meet WCAG AA in both themes."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8")


def tokens(block_selector: str) -> dict[str, str]:
    m = re.search(re.escape(block_selector) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert m, f"no {block_selector} block"
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", m.group(1)))


LIGHT = tokens(":root")
DARK = {**LIGHT, **tokens(':root[data-theme="dark"], :root[data-theme="black"]')}
BLACK = {**DARK, **tokens(':root[data-theme="black"]')}


def lum(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4   # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (foreground, background, minimum): 4.5 for body text, 3 for large text / UI graphics
PAIRS = [
    ("ink", "surface", 4.5), ("ink", "card", 4.5),
    ("graphite", "surface", 4.5), ("graphite", "card", 4.5),
    ("faint", "surface", 4.5), ("faint", "card", 4.5),
    ("on-primary", "primary", 4.5), ("on-accent", "accent", 4.5),
    ("link", "surface", 4.5), ("link", "card", 4.5),
    ("ink", "marker-soft", 4.5),
    ("good", "card", 4.5), ("mid", "card", 4.5), ("poor", "card", 4.5),
    ("primary", "surface", 3.0), ("logo-tile", "surface", 3.0),
]


@pytest.mark.parametrize("theme,t", [("light", LIGHT), ("dark", DARK), ("black", BLACK)])
@pytest.mark.parametrize("fg,bg,minimum", PAIRS)
def test_pair_meets_wcag(theme, t, fg, bg, minimum):
    r = ratio(t[fg], t[bg])
    assert r >= minimum, f"{theme}: {fg} {t[fg]} on {bg} {t[bg]} = {r:.2f}:1, needs {minimum}:1"


def test_brand_palette_is_used():
    assert LIGHT["primary"].upper() == "#1D4ED8"
    assert LIGHT["accent"].upper() == "#F59E0B"
    assert LIGHT["ink"].upper() == "#0F172A"
    assert LIGHT["surface"].upper() == "#F8FAFC"
    assert DARK["surface"].upper() == "#0B1220"
