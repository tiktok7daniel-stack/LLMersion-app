package app.lumenread

import android.content.Context
import android.content.SharedPreferences
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat

/** User settings. Defaults follow the LumenRead spec: system language, Arabic
 *  translation shown, 0.8x reading speed, OCR on. */
object Prefs {
    private lateinit var sp: SharedPreferences

    fun init(c: Context) {
        sp = c.getSharedPreferences("lumenread", Context.MODE_PRIVATE)
    }

    private fun str(k: String, d: String) = sp.getString(k, d) ?: d
    private fun put(k: String, v: String) = sp.edit().putString(k, v).apply()
    private fun bool(k: String, d: Boolean) = sp.getBoolean(k, d)
    private fun put(k: String, v: Boolean) = sp.edit().putBoolean(k, v).apply()

    /** system | en | ar | it */
    var uiLang: String
        get() = str("ui_lang", "system")
        set(v) = put("ui_lang", v)

    /** system | light | dark | black */
    var theme: String
        get() = str("theme", "system")
        set(v) = put("theme", v)

    var showTranslation: Boolean
        get() = bool("show_tr", true)
        set(v) = put("show_tr", v)

    /** ar | it | zh — the language of the translation under each paragraph */
    var target: String
        get() = str("target", "ar")
        set(v) = put("target", v)

    /** 0.5 .. 1.5 */
    var speed: Float
        get() = sp.getFloat("speed", 0.8f)
        set(v) = sp.edit().putFloat("speed", v.coerceIn(0.5f, 1.5f)).apply()

    /** languages shown together when a word is tapped (default: Arabic and Italian) */
    var wordLangs: List<String>
        get() = str("word_langs", "ar,it").split(',').filter { it in Langs.ALL }
            .ifEmpty { listOf(target) }
            .sortedBy { Langs.ALL.indexOf(it) }
        set(v) = put("word_langs", v.joinToString(","))

    var voice: String
        get() = str("voice", "")
        set(v) = put("voice", v)

    var ocr: Boolean
        get() = bool("ocr", true)
        set(v) = put("ocr", v)

    var flashGloss: Boolean
        get() = bool("flash_gloss", true)
        set(v) = put("flash_gloss", v)

    var serverUrl: String
        get() = str("server", "")
        set(v) = put("server", v)

    var onboarded: Boolean
        get() = bool("onboarded", false)
        set(v) = put("onboarded", v)

    fun applyNightMode() {
        AppCompatDelegate.setDefaultNightMode(
            when (theme) {
                "light" -> AppCompatDelegate.MODE_NIGHT_NO
                "dark", "black" -> AppCompatDelegate.MODE_NIGHT_YES
                else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
            }
        )
    }

    /** Arabic sets the whole app right-to-left (android:supportsRtl). A system
     *  language that is neither English nor Arabic falls back to English, the
     *  default resources. */
    fun applyLanguage() {
        AppCompatDelegate.setApplicationLocales(
            if (uiLang == "system") LocaleListCompat.getEmptyLocaleList()
            else LocaleListCompat.forLanguageTags(uiLang)
        )
    }
}
