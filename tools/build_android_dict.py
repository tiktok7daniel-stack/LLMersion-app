#!/usr/bin/env python3
"""Build the offline dictionary bundled in the Android app.

    npm install cmu-pronouncing-dictionary wordnet-db      (anywhere)
    python tools/build_android_dict.py <node_modules dir>

Writes android/app/src/main/assets/dict.tsv.gz, one line per word:

    word <TAB> IPA <TAB> definition(s)

IPA comes from the CMU Pronouncing Dictionary (converted from ARPAbet, General
American); definitions are the most frequent WordNet 3.0 senses, with a part-of-
speech label. Both sources are permissively licensed (CMUdict: BSD-style, npm
package ISC; WordNet: Princeton WordNet licence) — see docs/MODELS.md.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "android" / "app" / "src" / "main" / "assets" / "dict.tsv.gz"

ARPA = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ", "B": "b", "CH": "tʃ",
    "D": "d", "DH": "ð", "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h",
    "IH": "ɪ", "IY": "i", "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ",
    "UH": "ʊ", "UW": "u", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}


# two-consonant clusters that can start an English syllable (maximal onset, simplified)
ONSETS = {("P", "Y"), ("B", "Y"), ("K", "Y"), ("F", "Y"), ("M", "Y"), ("HH", "Y"), ("V", "Y"),
          ("P", "L"), ("P", "R"), ("B", "L"), ("B", "R"), ("T", "R"), ("D", "R"), ("K", "L"),
          ("K", "R"), ("G", "L"), ("G", "R"), ("F", "L"), ("F", "R"), ("TH", "R"), ("SH", "R"),
          ("S", "P"), ("S", "T"), ("S", "K"), ("S", "M"), ("S", "N"), ("S", "L"), ("S", "W"),
          ("T", "W"), ("K", "W"), ("D", "W"), ("G", "W")}


def to_ipa(arpa: str) -> str:
    """ARPAbet with stress digits -> IPA, with the stress mark before the syllable onset."""
    phones = [(m.group(1), m.group(2)) for m in (re.match(r"([A-Z]+)(\d?)", p) for p in arpa.split()) if m]
    syms = []
    for base, stress in phones:
        sym = ARPA.get(base, "")
        if base == "AH" and stress == "0":
            sym = "ə"
        elif base == "ER" and stress == "0":
            sym = "ɚ"
        syms.append(sym)
    marks: dict[int, str] = {}
    for i, (base, stress) in enumerate(phones):
        if base not in VOWELS or stress not in ("1", "2"):
            continue
        start = i
        # consonants directly before this vowel, back to the previous vowel
        cons = []
        j = i - 1
        while j >= 0 and phones[j][0] not in VOWELS:
            cons.insert(0, j)
            j -= 1
        if cons:
            if j < 0:                                   # word-initial: the whole cluster is the onset
                start = cons[0]
            elif len(cons) >= 2 and (phones[cons[-2]][0], phones[cons[-1]][0]) in ONSETS:
                start = cons[-2]
            else:
                start = cons[-1]
        marks[start] = "ˈ" if stress == "1" else "ˌ"
    # a single-syllable word gets no secondary marks and its primary mark is conventional
    return "".join(marks.get(i, "") + s for i, s in enumerate(syms))


POS = {"noun": "n.", "verb": "v.", "adj": "adj.", "adv": "adv."}


def wordnet(dict_dir: Path) -> dict[str, list[tuple[int, str, str]]]:
    """lemma -> [(tagged-sense count, pos label, gloss)] for its first two senses per POS."""
    out: dict[str, list[tuple[int, str, str]]] = {}
    for pos, label in POS.items():
        data = (dict_dir / f"data.{pos}").read_bytes()
        for line in (dict_dir / f"index.{pos}").read_text(encoding="latin-1").splitlines():
            if not line or line.startswith(" "):
                continue
            f = line.split()
            lemma = f[0].replace("_", " ")
            p_cnt = int(f[3])
            synset_cnt = int(f[2])
            tagsense = int(f[5 + p_cnt])
            offsets = f[6 + p_cnt:6 + p_cnt + synset_cnt][:2]
            glosses = []
            for off in offsets:
                o = int(off)
                end = data.index(b"\n", o)
                rec = data[o:end].decode("latin-1")
                g = rec.split("|", 1)[1].strip() if "|" in rec else ""
                g = re.split(r';\s*"', g)[0].strip()          # drop example sentences
                if g:
                    glosses.append(g)
            if glosses:
                out.setdefault(lemma, []).append((tagsense, label, "; ".join(glosses)))
    return out


def main(nm: str) -> None:
    nm_dir = Path(nm)
    src = (nm_dir / "cmu-pronouncing-dictionary" / "index.js").read_text(encoding="utf-8")
    body = src[src.index("export const dictionary = {") + len("export const dictionary = "):]
    cmu = json.loads(body[:body.rindex("}") + 1])
    wn = wordnet(nm_dir / "wordnet-db" / "dict")
    words = {w for w in cmu if re.fullmatch(r"[a-z][a-z'\-]*", w)} | {w for w in wn if " " not in w}
    lines = []
    for w in sorted(words):
        ipa = to_ipa(cmu[w]) if w in cmu else ""
        senses = sorted(wn.get(w, []), key=lambda s: -s[0])[:2]
        definition = " | ".join(f"{label} {g}" for _, label, g in senses)
        if not ipa and not definition:
            continue
        lines.append(f"{w}\t{ipa}\t{definition}".replace("\n", " "))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{len(lines)} words -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "node_modules")
