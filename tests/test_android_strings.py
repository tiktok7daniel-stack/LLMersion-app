"""Android app: every string exists in English and Arabic, and the code only uses strings that exist."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"
SRC = ROOT / "android" / "app" / "src" / "main" / "java"


def names(path: Path, translatable_only: bool = False) -> set[str]:
    out = set()
    for m in re.finditer(r'<string name="(\w+)"([^>]*)>', path.read_text(encoding="utf-8")):
        if translatable_only and 'translatable="false"' in m.group(2):
            continue
        out.add(m.group(1))
    return out


import pytest


@pytest.mark.parametrize("lang", ["ar", "it"])
def test_android_string_parity(lang):
    en = names(RES / "values" / "strings.xml", translatable_only=True)
    other = names(RES / f"values-{lang}" / "strings.xml")
    assert not en - other, f"missing from values-{lang}: {sorted(en - other)}"
    assert not other - en, f"only in values-{lang}: {sorted(other - en)}"


@pytest.mark.parametrize("lang", ["ar", "it"])
def test_android_placeholders_match(lang):
    def ph(path):
        return {n: sorted(re.findall(r"%\d\$[sd]", v)) for n, v in
                re.findall(r'<string name="(\w+)"[^>]*>(.*?)</string>', path.read_text(encoding="utf-8"), re.S)}
    en, other = ph(RES / "values" / "strings.xml"), ph(RES / f"values-{lang}" / "strings.xml")
    for k in other:
        assert en[k] == other[k], f"{k}: {en[k]} vs {other[k]}"


def test_android_italian_apostrophes_are_escaped():
    """An unescaped ' in an Android string resource breaks the build."""
    for lang in ("", "-ar", "-it"):
        for n, v in re.findall(r'<string name="(\w+)"[^>]*>(.*?)</string>',
                               (RES / f"values{lang}" / "strings.xml").read_text(encoding="utf-8"), re.S):
            assert not re.search(r"(?<!\\)'", v), f"values{lang}/{n} has an unescaped apostrophe"


def test_android_code_uses_only_existing_strings():
    defined = names(RES / "values" / "strings.xml")
    used = set()
    for f in list(SRC.rglob("*.kt")) + list((RES / "layout").glob("*.xml")):
        t = f.read_text(encoding="utf-8")
        used |= set(re.findall(r"R\.string\.(\w+)", t)) | set(re.findall(r"@string/(\w+)", t))
    assert used, "scanner found nothing"
    assert not used - defined, f"undefined strings: {sorted(used - defined)}"


def test_android_layouts_have_no_literal_text():
    for f in (RES / "layout").glob("*.xml"):
        lits = re.findall(r'android:(?:text|hint|contentDescription)="([^@"][^"]*)"', f.read_text(encoding="utf-8"))
        assert not lits, f"{f.name}: literal text {lits}"


def test_android_app_supports_rtl_and_mirrors_direction_icons():
    manifest = (ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:supportsRtl="true"' in manifest
    for icon in ("ic_next", "ic_prev", "ic_back", "ic_chevron"):
        assert 'autoMirrored="true"' in (RES / "drawable" / f"{icon}.xml").read_text(encoding="utf-8")
    for icon in ("ic_play", "ic_pause"):
        assert 'autoMirrored="false"' in (RES / "drawable" / f"{icon}.xml").read_text(encoding="utf-8")


def test_android_offline_dictionary_is_bundled():
    import gzip
    d = ROOT / "android" / "app" / "src" / "main" / "assets" / "dict.bin"
    rows = {l.split("\t")[0]: l.rstrip("\n").split("\t") for l in gzip.open(d, "rt", encoding="utf-8")}
    assert len(rows) > 100_000
    assert rows["light"][1] == "ˈlaɪt" and rows["light"][2].startswith("n.")
    assert rows["computer"][1] == "kəmˈpjutɚ"
