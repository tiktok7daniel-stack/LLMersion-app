#!/usr/bin/env python3
"""Generate the LumenRead logo set from one geometry definition.

    pip install cairosvg pillow
    python tools/build_brand.py

Writes into web/brand/:
    logo.svg              the full mark (tile + book + beam), brand colours
    logo-mark.svg         the glyph alone on a transparent ground, for headers
    logo-mono.svg         one-colour version for print / watermark
    logo-{512,192,48,32}.png
    apple-touch-icon.png  180 px
    icon-192.png, icon-512.png, icon-maskable-512.png   web app manifest icons
    favicon.ico           16 / 32 / 48

Concept: an open book whose pages rise into a soft beam of light (the "lumen");
the beam is shaped like a speech bubble with its tail resting on the spine, so
reading and speaking are one gesture. Flat shapes only, no text, and every
element is at least ~8% of the canvas so it still reads at 32 px.

Palette: primary #1D4ED8, accent #F59E0B, ink #0F172A, paper #F8FAFC, dark #0B1220.
"""
from __future__ import annotations

import io
from pathlib import Path

PRIMARY, ACCENT, INK, PAPER, DARK = "#1D4ED8", "#F59E0B", "#0F172A", "#F8FAFC", "#0B1220"
PAPER_SHADE = "#DBEAFE"      # the right page, a touch cooler, so the book has volume
ACCENT_SOFT = "#FCD34D"      # the bright core of the beam

OUT = Path(__file__).resolve().parent.parent / "web" / "brand"

# --- geometry on a 512 x 512 canvas ---------------------------------------
# beam: a cone of light leaving the spine and widening upward, soft rounded top
BEAM = "M226 316 L 132 118 Q 256 66 380 118 L 286 316 Z"
BEAM_CORE = "M240 306 L 176 128 Q 256 100 336 128 L 272 306 Z"
# speech bubble riding in the beam: rounded body, tail pointing back down to the book
BUBBLE = ("M222 138 H 290 Q 316 138 316 164 V 186 Q 316 212 290 212 H 252 "
          "L 226 240 L 230 212 H 222 Q 196 212 196 186 V 164 Q 196 138 222 138 Z")
# open book: two pages meeting at the spine, outer edges lifted
PAGE_L = "M256 414 L 76 364 L 76 258 Q 76 246 90 250 L 256 306 Z"
PAGE_R = "M256 414 L 436 364 L 436 258 Q 436 246 422 250 L 256 306 Z"
SPINE = "M256 306 L 256 414"


def _glyph(tile: bool, page_l=PAPER, page_r=PAPER_SHADE, beam=ACCENT, core=ACCENT_SOFT,
           spine=PRIMARY) -> str:
    # A thin cover under the pages gives the book a base that survives 32 px.
    cover = f'<path d="M64 358 L256 412 L448 358 L448 380 L256 436 L64 380 Z" fill="{PAPER}" opacity=".55"/>'
    return (f'<path d="{BEAM}" fill="{beam}"/>'
            f'<path d="{BEAM_CORE}" fill="{core}"/>'
            f'<path d="{BUBBLE}" fill="{PAPER}"/>'
            f'{cover}'
            f'<path d="{PAGE_L}" fill="{page_l}"/>'
            f'<path d="{PAGE_R}" fill="{page_r}"/>'
            f'<path d="{SPINE}" stroke="{spine}" stroke-width="6" stroke-linecap="round" fill="none" opacity=".35"/>')


def svg_full(size: int = 512, maskable: bool = False) -> str:
    """Tile + glyph. `maskable` is full-bleed with the glyph pulled into the safe zone."""
    if maskable:
        tile = f'<rect width="512" height="512" fill="{PRIMARY}"/>'
        inner = f'<g transform="translate(256 256) scale(.78) translate(-256 -256)">{_glyph(True)}</g>'
    else:
        tile = f'<rect width="512" height="512" rx="112" fill="{PRIMARY}"/>'
        inner = _glyph(True)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" '
            f'height="{size}" role="img" aria-label="LumenRead">'
            f'<title>LumenRead</title>{tile}{inner}</svg>\n')


def svg_mark() -> str:
    """Glyph only; colours pull from CSS custom properties when inlined in the page."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" '
            'aria-label="LumenRead">'
            f'<title>LumenRead</title>'
            f'<rect width="512" height="512" rx="112" fill="{PRIMARY}"/>{_glyph(True)}</svg>\n')


def svg_mono(color: str = INK) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" '
            'aria-label="LumenRead"><title>LumenRead</title>'
            f'<path d="{PAGE_L}" fill="{color}"/><path d="{PAGE_R}" fill="{color}" opacity=".7"/>'
            f'<path d="{BEAM}" fill="{color}"/></svg>\n')


def png(svg: str, size: int) -> bytes:
    import cairosvg
    return cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "logo.svg").write_text(svg_full(), encoding="utf-8")
    (OUT / "logo-mark.svg").write_text(svg_mark(), encoding="utf-8")
    (OUT / "logo-mono.svg").write_text(svg_mono(), encoding="utf-8")
    full = svg_full()
    for n in (512, 192, 48, 32):
        (OUT / f"logo-{n}.png").write_bytes(png(full, n))
    (OUT / "apple-touch-icon.png").write_bytes(png(full, 180))
    (OUT / "icon-192.png").write_bytes(png(full, 192))
    (OUT / "icon-512.png").write_bytes(png(full, 512))
    (OUT / "icon-maskable-512.png").write_bytes(png(svg_full(maskable=True), 512))

    from PIL import Image
    base = Image.open(io.BytesIO(png(full, 256))).convert("RGBA")
    base.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
