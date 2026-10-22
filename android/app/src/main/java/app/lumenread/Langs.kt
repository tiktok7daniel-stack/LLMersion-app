package app.lumenread

import android.content.Context
import android.view.View
import com.google.mlkit.nl.translate.TranslateLanguage

/** The languages English can be translated into, and how each is laid out. */
object Langs {
    /** in the order they are shown */
    val ALL = listOf("ar", "it", "zh")

    fun mlkit(code: String): String = when (code) {
        "it" -> TranslateLanguage.ITALIAN
        "zh" -> TranslateLanguage.CHINESE
        else -> TranslateLanguage.ARABIC
    }

    fun isRtl(code: String) = code == "ar"

    fun textDirection(code: String) = if (isRtl(code)) View.TEXT_DIRECTION_RTL else View.TEXT_DIRECTION_LTR
    fun layoutDirection(code: String) = if (isRtl(code)) View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR

    fun name(c: Context, code: String): String = c.getString(when (code) {
        "it" -> R.string.target_it
        "zh" -> R.string.target_zh
        else -> R.string.target_ar
    })
}
