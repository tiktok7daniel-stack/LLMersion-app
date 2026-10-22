# LumenRead for Android

A standalone phone app (Kotlin, Material 3). It does **not** need a computer or a browser:

| Feature | How it works on the phone |
|---|---|
| Read aloud, 0.5×–1.5× (default 0.8×), sentence highlight | the phone's own English text-to-speech, one utterance per sentence |
| Translation under each paragraph (Arabic, Italian or Chinese) | Google ML Kit on-device translation; the language model downloads once (~30 MB), then works offline |
| Tap a word: IPA, English definition, and the meaning in Arabic **and** Italian together (choose the languages in Settings) | bundled dictionary (CMU pronunciations + WordNet definitions, `assets/dict.bin`) + ML Kit |
| PDF import, page by page, "go to page" | PdfBox-Android; files cached by hash |
| Scanned PDFs | ML Kit on-device OCR (Latin script; Arabic scans are not supported on the phone) |
| Vocabulary + spaced-repetition flashcards | SQLite; English front, Arabic back (optional) |
| Pronunciation practice | the phone's speech recognition; word-by-word score of the sentence you read |
| English / Arabic / Italian interface (Arabic is RTL), light / dark / black | Android resources (`values`, `values-ar`), `supportsRtl`, auto-mirrored icons |

The conversation tutor and writing correction need a large language model that a phone cannot
run; they are an optional extra screen that connects to the LumenRead server if you run one
(Settings → Tutor server).

## Get the APK

GitHub → Actions → **Android APK** → run it (or push to `android/`). The APK is attached to the
`apk-latest` release and to the run's artifacts. On the phone: download, allow "install unknown
apps", install.

## Build locally

JDK 17, Android SDK 34, Gradle 8.9: `cd android && gradle assembleDebug` →
`app/build/outputs/apk/debug/app-debug.apk`.

Regenerate the bundled dictionary with `tools/build_android_dict.py` and the launcher icons with
`tools/build_brand.py`.
