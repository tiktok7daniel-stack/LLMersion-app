package app.lumenread

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.slider.Slider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

class SettingsActivity : BaseActivity() {
    private lateinit var box: LinearLayout
    private var speaker: Speaker? = null
    private val dp get() = resources.displayMetrics.density

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scroll)
        toolbar(getString(R.string.settings))
        box = findViewById(R.id.content)
        speaker = Speaker(this) { render() }
        render()
    }

    override fun onDestroy() {
        speaker?.shutdown()
        super.onDestroy()
    }

    private fun render() {
        box.removeAllViews()
        section(R.string.s_language)
        choice(R.string.s_language, listOf("system" to R.string.lang_system, "en" to R.string.lang_en, "ar" to R.string.lang_ar),
            Prefs.uiLang) { Prefs.uiLang = it; Prefs.applyLanguage() }
        choice(R.string.s_theme, listOf("system" to R.string.theme_system, "light" to R.string.theme_light,
            "dark" to R.string.theme_dark, "black" to R.string.theme_black), Prefs.theme) {
            Prefs.theme = it; Prefs.applyNightMode(); recreate()
        }

        section(R.string.s_translation_section)
        switch(R.string.s_show_translation, Prefs.showTranslation) { Prefs.showTranslation = it }
        choice(R.string.s_target, listOf("ar" to R.string.target_ar, "zh" to R.string.target_zh), Prefs.target) {
            Prefs.target = it
        }

        section(R.string.s_reading_section)
        val voices = speaker?.englishVoices().orEmpty()
        row(getString(R.string.s_voice), Prefs.voice.ifEmpty { getString(R.string.voice_default) }) {
            val names = listOf(getString(R.string.voice_default)) + voices.map { it.name }
            MaterialAlertDialogBuilder(this).setTitle(R.string.s_voice)
                .setSingleChoiceItems(names.toTypedArray(), maxOf(0, names.indexOf(Prefs.voice))) { d, w ->
                    Prefs.voice = if (w == 0) "" else names[w]
                    speaker?.setVoice(Prefs.voice)
                    speaker?.speak("Read. Listen. Speak. Understand.", "demo")
                    d.dismiss(); render()
                }.show()
        }
        speedRow()

        section(R.string.s_pdf_section)
        switch(R.string.s_ocr, Prefs.ocr) { Prefs.ocr = it }
        note(R.string.s_ocr_note)

        section(R.string.s_server)
        note(R.string.s_server_note)
        row(getString(R.string.s_server), Prefs.serverUrl.ifEmpty { getString(R.string.not_set) }) {
            val input = EditText(this).apply {
                setText(Prefs.serverUrl); hint = getString(R.string.server_hint)
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                textDirection = View.TEXT_DIRECTION_LTR
            }
            MaterialAlertDialogBuilder(this).setTitle(R.string.s_server).setView(padded(input))
                .setPositiveButton(R.string.ok) { _, _ -> Prefs.serverUrl = input.text.toString().trim(); render() }
                .setNegativeButton(R.string.cancel, null).show()
        }

        section(R.string.s_data_section)
        row(getString(R.string.s_clear_translations), "") { confirmClear { Db.clearTrans() } }
        row(getString(R.string.s_clear_documents), "") {
            confirmClear { Db.clearDocs(); java.io.File(filesDir, "docs").deleteRecursively() }
        }
        note(R.string.privacy)
        row(getString(R.string.about), "") { startActivity(Intent(this, AboutActivity::class.java)) }
    }

    private fun padded(v: View) = FrameLayout(this).apply {
        val p = (20 * dp).toInt(); setPadding(p, p / 2, p, 0); addView(v)
    }

    private fun confirmClear(action: () -> Unit) {
        MaterialAlertDialogBuilder(this).setMessage(R.string.confirm_clear)
            .setPositiveButton(R.string.ok) { _, _ ->
                lifecycleScope.launch {
                    withContext(Dispatchers.IO) { action() }
                    toast(getString(R.string.cleared))
                }
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun section(title: Int) {
        box.addView(TextView(this).apply {
            setText(title); textSize = 13f; setTextColor(ContextCompat.getColor(context, R.color.primary))
            setPadding(0, (24 * dp).toInt(), 0, (6 * dp).toInt())
        })
    }

    private fun note(text: Int) {
        box.addView(TextView(this).apply {
            setText(text); textSize = 13f; setTextColor(ContextCompat.getColor(context, R.color.text3))
            setPadding(0, (2 * dp).toInt(), 0, (8 * dp).toInt())
        })
    }

    private fun row(title: String, value: String, onClick: () -> Unit) {
        val r = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, (12 * dp).toInt(), 0, (12 * dp).toInt())
            isClickable = true
            val tv = android.util.TypedValue()
            context.theme.resolveAttribute(android.R.attr.selectableItemBackground, tv, true)
            setBackgroundResource(tv.resourceId)
            setOnClickListener { onClick() }
        }
        r.addView(TextView(this).apply { text = title; textSize = 16f; setTextColor(ContextCompat.getColor(context, R.color.text)) })
        if (value.isNotEmpty()) r.addView(TextView(this).apply {
            text = value; textSize = 14f; setTextColor(ContextCompat.getColor(context, R.color.text2))
        })
        box.addView(r, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
    }

    private fun choice(title: Int, options: List<Pair<String, Int>>, current: String, set: (String) -> Unit) {
        val label = options.firstOrNull { it.first == current }?.second ?: options[0].second
        row(getString(title), getString(label)) {
            MaterialAlertDialogBuilder(this).setTitle(title)
                .setSingleChoiceItems(options.map { getString(it.second) }.toTypedArray(),
                    maxOf(0, options.indexOfFirst { it.first == current })) { d, w ->
                    d.dismiss(); set(options[w].first); render()
                }.show()
        }
    }

    private fun switch(title: Int, value: Boolean, set: (Boolean) -> Unit) {
        box.addView(MaterialSwitch(this).apply {
            setText(title); textSize = 16f; isChecked = value
            setPadding(0, (8 * dp).toInt(), 0, (8 * dp).toInt())
            setOnCheckedChangeListener { _, on -> set(on) }
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
    }

    private fun speedRow() {
        box.addView(TextView(this).apply {
            setText(R.string.s_speed); textSize = 16f; setTextColor(ContextCompat.getColor(context, R.color.text))
            setPadding(0, (12 * dp).toInt(), 0, 0)
        })
        box.addView(Slider(this).apply {
            valueFrom = 0.5f; valueTo = 1.5f; stepSize = 0.1f
            value = (Math.round(Prefs.speed * 10) / 10f).coerceIn(0.5f, 1.5f)
            setLabelFormatter { v -> "%.1f×".format(Locale.US, v) }
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            addOnChangeListener { _, v, fromUser -> if (fromUser) Prefs.speed = v }
        })
    }
}
