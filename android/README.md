# LumenRead for Android

A native shell (Java, `android.webkit.WebView`, no third-party libraries) around the LumenRead web
interface served by **your own computer**. The translation, voice, tutor and OCR models run there; the
phone shows the bilingual (English / Arabic, RTL) interface, records your voice, and opens PDFs with the
system file picker.

1. On the computer: `PR_HOST=0.0.0.0 PR_TOKEN=choose-a-secret python -m server.main`
2. Install the APK (`gradle assembleDebug`, or download the artifact from the *Android APK* workflow).
3. Open the app, enter `http://<computer-ip>:8848` (and the token). Change it later from the error
   screen or by clearing the app's data.

Microphone: Android only exposes it to `https://` pages or `http://localhost`. Run
`adb reverse tcp:8848 tcp:8848` and use `http://localhost:8848`, or serve the app over HTTPS.

Requirements: JDK 17, Android SDK 34, Gradle 8.9. `minSdk 24`. The launcher icon is generated from
`web/brand` (see `tools/build_brand.py`). **Not yet compiled in the environment this was written in.**
