# Models and licenses

Nothing here is bundled. Weights download from their publishers on first use; check each model card
before redistributing anything.

| Role | Model | License | Notes |
|---|---|---|---|
| Translation → Arabic (default) | `Helsinki-NLP/opus-mt-en-ar` | CC-BY-4.0 | needs the `>>ara<<` target token; handled by `server/mt/opus_ar.py` |
| Translation → Arabic (better, slower) | `facebook/nllb-200-distilled-600M`, `-1.3B` | **CC-BY-NC-4.0** | non-commercial only |
| Translation → Chinese | `Helsinki-NLP/opus-mt-en-zh` | CC-BY-4.0 | unchanged from upstream |
| Voice | Kokoro-82M | Apache-2.0 | English reading voice |
| Optional Arabic voice | Piper voices from `rhasspy/piper-voices/ar` | per voice card | optional, never needed for reading |
| Speech recognition | Whisper via faster-whisper | MIT | |
| Pronunciation | `facebook/wav2vec2-lv-60-espeak-cv-ft` | Apache-2.0 | |
| Tutor | Llama / Qwen / Gemma via Ollama | per model card | e.g. Llama 3.2 Community License, Apache-2.0 |
| OCR | Tesseract + `eng`, `ara` data | Apache-2.0 | separate install |
| Dictionary (optional) | ECDICT | MIT | built with `tools/build_ecdict.py` |
| Fonts | Inter, Cairo, Noto Naskh Arabic, Source Serif 4, IBM Plex Mono | SIL OFL 1.1 | bundled in `web/fonts/` |

The code is MIT. Select the translation model with `PR_MT_MODEL_AR` / `PR_MT_BACKEND_AR`, or in
Settings → Translation aid.

## Android app

| Role | Component | License |
|---|---|---|
| Translation, OCR | Google ML Kit (on-device) | Google APIs Terms of Service; models download on first use |
| PDF text | PdfBox-Android | Apache-2.0 |
| IPA | CMU Pronouncing Dictionary (via `cmu-pronouncing-dictionary`) | BSD-style / ISC |
| Definitions | Princeton WordNet 3.0 (via `wordnet-db`) | WordNet licence (permissive) |
| Voice, speech recognition | the phone's system services | — |
