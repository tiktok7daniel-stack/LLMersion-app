package app.lumenread

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.InputType
import android.text.Spannable
import android.text.SpannableString
import android.text.style.BackgroundColorSpan
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.graphics.Typeface
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.floatingactionbutton.FloatingActionButton
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.slider.Slider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Read-along: the phone's English voice reads sentence by sentence, the spoken sentence is
 * highlighted, the translation sits under each paragraph, any word can be tapped.
 *
 * The *content* keeps the direction of its own language: English paragraphs are always
 * left-to-right even when the interface is Arabic, and the Arabic translation is always
 * right-to-left even when the interface is English.
 */
class ReaderActivity : BaseActivity() {
    private sealed class Row {
        data class Page(val page: Int) : Row()
        data class P(val index: Int) : Row()
    }
    private data class Unit_(val para: Int, val start: Int, val end: Int)

    private lateinit var doc: Doc
    private lateinit var list: RecyclerView
    private lateinit var lm: LinearLayoutManager
    private lateinit var play: FloatingActionButton
    private lateinit var progress: LinearProgressIndicator
    private lateinit var speedBtn: TextView
    private var speaker: Speaker? = null

    private val rows = mutableListOf<Row>()
    private val rowOfPara = mutableMapOf<Int, Int>()
    private val units = mutableListOf<Unit_>()
    private var cur = 0
    private var playing = false
    private val translations = mutableMapOf<Int, String>()
    private val inFlight = mutableSetOf<Int>()
    private var warnedModel = false
    private var recognizer: SpeechRecognizer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = Db.getDoc(intent.getStringExtra("hash") ?: "")
        if (d == null) { finish(); return }
        doc = d
        setContentView(R.layout.activity_reader)
        toolbar(doc.title)
        list = findViewById(R.id.list)
        lm = LinearLayoutManager(this)
        list.layoutManager = lm
        play = findViewById(R.id.play)
        progress = findViewById(R.id.progress)
        speedBtn = findViewById(R.id.speed)

        build()
        list.adapter = Adapter()

        cur = Db.getProgress(doc.hash).coerceIn(0, maxOf(0, units.size - 1))
        if (cur > 0) {
            list.post { scrollToUnit(cur) }
            toast(getString(R.string.resumed))
        }
        if (doc.lang == "ar") toast(getString(R.string.arabic_doc))
        updateProgress()

        speaker = Speaker(this) { ok -> if (!ok) ttsMissing() }.also { sp ->
            sp.onStart = { id -> id.toIntOrNull()?.let { highlight(it) } }
            sp.onDone = { id ->
                val i = id.toIntOrNull()
                if (playing && i != null && i == cur) {
                    if (cur + 1 < units.size) speakUnit(cur + 1) else setPlaying(false)
                }
            }
        }

        play.setOnClickListener { if (playing) setPlaying(false) else startAt(cur) }
        findViewById<View>(R.id.prevSent).setOnClickListener { startAt(cur - 1) }
        findViewById<View>(R.id.nextSent).setOnClickListener { startAt(cur + 1) }
        findViewById<View>(R.id.prevPara).setOnClickListener { stepPara(-1) }
        findViewById<View>(R.id.nextPara).setOnClickListener { stepPara(1) }
        findViewById<View>(R.id.practice).setOnClickListener { practice() }
        speedBtn.setOnClickListener { speedDialog() }
        showSpeed()
    }

    override fun onPause() {
        super.onPause()
        if (::doc.isInitialized) Db.setProgress(doc.hash, cur)
        if (playing) setPlaying(false)
    }

    override fun onDestroy() {
        speaker?.shutdown()
        recognizer?.destroy()
        super.onDestroy()
    }

    // ------------------------------------------------------------ structure
    private fun build() {
        var lastPage = -1
        doc.paras.forEachIndexed { i, p ->
            if (p.page != lastPage) { lastPage = p.page; rows += Row.Page(p.page) }
            rowOfPara[i] = rows.size
            rows += Row.P(i)
            if (p.speakable) TextUtil.sentences(p.text).forEach { units += Unit_(i, it.start, it.end) }
        }
    }

    private fun showSpeed() {
        speedBtn.text = getString(R.string.speed_value, "%.1f".format(java.util.Locale.US, Prefs.speed))
    }

    private fun updateProgress() {
        progress.max = maxOf(1, units.size - 1)
        progress.progress = cur
    }

    // ------------------------------------------------------------ playback
    private fun setPlaying(on: Boolean) {
        playing = on
        play.setImageResource(if (on) R.drawable.ic_pause else R.drawable.ic_play)
        play.contentDescription = getString(if (on) R.string.pause else R.string.play)
        if (!on) speaker?.stop()
    }

    private fun startAt(i: Int) {
        if (units.isEmpty()) return
        val sp = speaker ?: return
        if (!sp.ready) { ttsMissing(); return }
        setPlaying(true)
        speakUnit(i.coerceIn(0, units.size - 1))
    }

    private fun speakUnit(i: Int) {
        val u = units[i]
        cur = i
        highlight(i)
        val text = doc.paras[u.para].text.substring(u.start, u.end)
        speaker?.setRate(Prefs.speed)
        speaker?.speak(text, i.toString(), flush = true)
    }

    private fun stepPara(d: Int) {
        if (units.isEmpty()) return
        val p = units[cur].para
        val target = if (d < 0 && units[cur].start > 0) p else p + d
        val idx = units.indexOfFirst { if (d < 0) it.para >= target else it.para >= target }
        if (idx >= 0) { if (playing) startAt(idx) else { highlight(idx) } }
    }

    private var lastHighlighted = -1
    private fun highlight(i: Int) {
        if (i !in units.indices) return
        val oldPara = if (lastHighlighted in units.indices) units[lastHighlighted].para else -1
        cur = i
        lastHighlighted = i
        val p = units[i].para
        if (oldPara >= 0 && oldPara != p) rowOfPara[oldPara]?.let { list.adapter?.notifyItemChanged(it) }
        rowOfPara[p]?.let { list.adapter?.notifyItemChanged(it) }
        scrollToUnit(i)
        updateProgress()
    }

    private fun scrollToUnit(i: Int) {
        val row = rowOfPara[units.getOrNull(i)?.para ?: return] ?: return
        val first = lm.findFirstCompletelyVisibleItemPosition()
        val last = lm.findLastCompletelyVisibleItemPosition()
        if (row < first || row > last) lm.scrollToPositionWithOffset(row, list.height / 4)
    }

    private fun ttsMissing() {
        MaterialAlertDialogBuilder(this).setMessage(R.string.tts_missing)
            .setPositiveButton(R.string.tts_settings) { _, _ ->
                runCatching { startActivity(Intent("com.android.settings.TTS_SETTINGS")) }
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    // ------------------------------------------------------------ menu: page, translation
    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, R.string.go_to_page).setIcon(R.drawable.ic_page)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        menu.add(0, 2, 1, R.string.translation).setIcon(R.drawable.ic_translate)
            .setCheckable(true).setChecked(Prefs.showTranslation)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        return true
    }

    @SuppressLint("NotifyDataSetChanged")
    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> pageDialog()
            2 -> {
                Prefs.showTranslation = !Prefs.showTranslation
                item.isChecked = Prefs.showTranslation
                list.adapter?.notifyDataSetChanged()
            }
            else -> return super.onOptionsItemSelected(item)
        }
        return true
    }

    private fun pageDialog() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            hint = getString(R.string.page_number_hint, doc.pages)
            textDirection = View.TEXT_DIRECTION_LTR
        }
        val pad = (20 * resources.displayMetrics.density).toInt()
        val frame = android.widget.FrameLayout(this).apply { setPadding(pad, pad / 2, pad, 0); addView(input) }
        MaterialAlertDialogBuilder(this).setTitle(R.string.go_to_page).setView(frame)
            .setPositiveButton(R.string.go) { _, _ ->
                val n = (input.text.toString().toIntOrNull() ?: 1).coerceIn(1, doc.pages)
                val row = rows.indexOfFirst { it is Row.Page && it.page + 1 >= n }
                if (row >= 0) lm.scrollToPositionWithOffset(row, 0)
                val u = units.indexOfFirst { doc.paras[it.para].page + 1 >= n }
                if (u >= 0) { if (playing) startAt(u) else { cur = u; lastHighlighted = -1; updateProgress() } }
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun speedDialog() {
        val slider = Slider(this).apply {
            valueFrom = 0.5f; valueTo = 1.5f; stepSize = 0.1f
            value = (Math.round(Prefs.speed * 10) / 10f).coerceIn(0.5f, 1.5f)
            setLabelFormatter { v -> "%.1f×".format(java.util.Locale.US, v) }
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        val pad = (20 * resources.displayMetrics.density).toInt()
        val frame = android.widget.FrameLayout(this).apply { setPadding(pad, pad, pad, 0); addView(slider) }
        MaterialAlertDialogBuilder(this).setTitle(R.string.speed).setView(frame)
            .setPositiveButton(R.string.ok) { _, _ ->
                Prefs.speed = slider.value
                speaker?.setRate(Prefs.speed)
                showSpeed()
                if (playing) startAt(cur)
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    // ------------------------------------------------------------ translation
    private fun translationFor(pi: Int, pos: Int): String? {
        translations[pi]?.let { return it }
        if (pi in inFlight) return null
        inFlight += pi
        lifecycleScope.launch {
            val target = Prefs.target
            if (!Tr.isReady(target) && !warnedModel) { warnedModel = true; toast(getString(R.string.downloading_model)) }
            try {
                translations[pi] = Tr.translate(doc.paras[pi].text, target)
                list.adapter?.notifyItemChanged(pos)
            } catch (e: Exception) {
                if (!warnedModel || Tr.isReady(target)) toast(getString(R.string.translation_failed, e.message ?: ""))
                warnedModel = true
            } finally {
                inFlight -= pi
            }
        }
        return null
    }

    // ------------------------------------------------------------ word tap
    private fun showWord(word: String, para: Int, offset: Int) {
        val sheet = BottomSheetDialog(this)
        val v = layoutInflater.inflate(R.layout.sheet_word, null)
        sheet.setContentView(v)
        v.findViewById<TextView>(R.id.word).text = word
        val ipa = v.findViewById<TextView>(R.id.ipa)
        val gloss = v.findViewById<TextView>(R.id.gloss)
        val def = v.findViewById<TextView>(R.id.def)
        val target = Prefs.target
        gloss.textDirection = if (target == "ar") View.TEXT_DIRECTION_RTL else View.TEXT_DIRECTION_LTR
        gloss.textAlignment = View.TEXT_ALIGNMENT_VIEW_START
        gloss.text = "…"
        speaker?.speak(word, "word", flush = true)
        v.findViewById<View>(R.id.listen).setOnClickListener { speaker?.speak(word, "word", flush = true) }
        v.findViewById<View>(R.id.readHere).setOnClickListener {
            sheet.dismiss()
            val u = units.indexOfFirst { it.para == para && offset < it.end }
            if (u >= 0) startAt(u)
        }
        var base = word.lowercase()
        v.findViewById<TextView>(R.id.remove).setOnClickListener { btn ->
            lifecycleScope.launch(Dispatchers.IO) { Db.deleteWord(base) }
            (btn as TextView).setText(R.string.removed); btn.isEnabled = false
        }
        sheet.show()

        val sentence = units.firstOrNull { it.para == para && offset < it.end }
            ?.let { doc.paras[para].text.substring(it.start, it.end) } ?: ""
        lifecycleScope.launch {
            val e = withContext(Dispatchers.IO) { runCatching { Dict.lookup(this@ReaderActivity, word) }.getOrNull() }
            if (e != null) {
                base = e.lemmaOf.ifEmpty { e.word }
                ipa.text = if (e.ipa.isNotEmpty()) "/${e.ipa}/" else ""
                def.text = e.definition.replace(" | ", "\n")
            }
            val g = try { Tr.translate(base, target) } catch (ex: Exception) { "" }
            gloss.text = g.ifEmpty { getString(R.string.not_found) }
            withContext(Dispatchers.IO) { Db.addWord(base, g, target, e?.ipa ?: "", sentence) }
        }
    }

    // ------------------------------------------------------------ speaking practice
    private val micPermission = registerForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) practice() else toast(getString(R.string.mic_denied)) }

    private fun practice() {
        if (units.isEmpty()) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            micPermission.launch(Manifest.permission.RECORD_AUDIO); return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) { toast(getString(R.string.no_recognizer)); return }
        if (playing) setPlaying(false)
        val u = units[cur]
        val target = doc.paras[u.para].text.substring(u.start, u.end)
        highlight(cur)

        val msg = TextView(this).apply {
            val pad = (24 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            setText(R.string.listening)
        }
        val dlg = MaterialAlertDialogBuilder(this).setTitle(R.string.practice).setView(msg)
            .setNegativeButton(R.string.cancel) { _, _ -> recognizer?.cancel() }.show()

        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).also { r ->
            r.setRecognitionListener(object : RecognitionListener {
                override fun onResults(results: Bundle) {
                    val heard = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull() ?: ""
                    dlg.dismiss()
                    showScore(target, heard)
                }
                override fun onError(error: Int) {
                    dlg.dismiss()
                    toast(getString(R.string.no_speech))
                }
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onPartialResults(partialResults: Bundle?) {}
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
            r.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            })
        }
    }

    /** Word-level comparison of what was said with the sentence (longest common subsequence). */
    private fun showScore(target: String, heard: String) {
        val norm = { s: String -> Regex("[A-Za-z']+").findAll(s.lowercase()).map { it.value }.toList() }
        val t = norm(target)
        val h = norm(heard)
        val dp = Array(t.size + 1) { IntArray(h.size + 1) }
        for (i in t.indices.reversed()) for (j in h.indices.reversed())
            dp[i][j] = if (t[i] == h[j]) dp[i + 1][j + 1] + 1 else maxOf(dp[i + 1][j], dp[i][j + 1])
        val matched = BooleanArray(t.size)
        var i = 0; var j = 0
        while (i < t.size && j < h.size) {
            when {
                t[i] == h[j] -> { matched[i] = true; i++; j++ }
                dp[i + 1][j] >= dp[i][j + 1] -> i++
                else -> j++
            }
        }
        val score = if (t.isEmpty()) 0 else (100 * matched.count { it } / t.size)
        val missed = t.filterIndexed { k, _ -> !matched[k] }.distinct()

        // the sentence with missed words in red
        val shown = SpannableString(target)
        var from = 0
        Regex("[A-Za-z']+").findAll(target).forEachIndexed { k, m ->
            if (k < matched.size && !matched[k]) {
                shown.setSpan(ForegroundColorSpan(ContextCompat.getColor(this, R.color.poor)),
                    m.range.first, m.range.last + 1, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                shown.setSpan(StyleSpan(Typeface.BOLD), m.range.first, m.range.last + 1, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
            from = m.range.last + 1
        }
        val body = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            val pad = (24 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            addView(TextView(context).apply { text = shown; textSize = 18f; textDirection = View.TEXT_DIRECTION_LTR })
            addView(TextView(context).apply {
                text = getString(R.string.you_said) + ": " + heard.ifEmpty { "—" }
                setPadding(0, pad / 2, 0, 0); setTextColor(ContextCompat.getColor(context, R.color.text2))
                textDirection = View.TEXT_DIRECTION_LOCALE
            })
            addView(TextView(context).apply {
                text = if (missed.isEmpty()) getString(R.string.all_words_ok)
                       else getString(R.string.missed_words, missed.joinToString(", "))
                setPadding(0, pad / 2, 0, 0)
            })
        }
        MaterialAlertDialogBuilder(this).setTitle(getString(R.string.score_n, score)).setView(body)
            .setPositiveButton(R.string.try_again) { _, _ -> practice() }
            .setNeutralButton(R.string.listen) { _, _ -> speaker?.speak(target, "practice", true) }
            .setNegativeButton(R.string.ok, null).show()
    }

    // ------------------------------------------------------------ adapter
    private inner class Adapter : RecyclerView.Adapter<RecyclerView.ViewHolder>() {
        inner class PageH(v: View) : RecyclerView.ViewHolder(v) { val t: TextView = v.findViewById(R.id.page) }
        inner class ParaH(v: View) : RecyclerView.ViewHolder(v) {
            val en: TextView = v.findViewById(R.id.en)
            val tr: TextView = v.findViewById(R.id.tr)
        }

        override fun getItemViewType(position: Int) = if (rows[position] is Row.Page) 0 else 1
        override fun getItemCount() = rows.size

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
            val inf = LayoutInflater.from(parent.context)
            return if (viewType == 0) PageH(inf.inflate(R.layout.item_page, parent, false))
                   else ParaH(inf.inflate(R.layout.item_para, parent, false))
        }

        @SuppressLint("ClickableViewAccessibility")
        override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
            when (val row = rows[position]) {
                is Row.Page -> (holder as PageH).t.text = getString(R.string.page_n, row.page + 1)
                is Row.P -> bindPara(holder as ParaH, row.index, position)
            }
        }

        @SuppressLint("ClickableViewAccessibility")
        private fun bindPara(h: ParaH, pi: Int, position: Int) {
            val p = doc.paras[pi]
            // the paragraph keeps the direction of its own language
            val rtl = p.dir == "rtl"
            h.en.textDirection = if (rtl) View.TEXT_DIRECTION_RTL else View.TEXT_DIRECTION_LTR
            h.en.layoutDirection = if (rtl) View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR
            h.en.textAlignment = View.TEXT_ALIGNMENT_VIEW_START
            h.en.textSize = when (p.kind) { "heading" -> 21f; "other" -> 14f; else -> 19f }
            h.en.setTypeface(Typeface.SERIF, if (p.kind == "heading") Typeface.BOLD else Typeface.NORMAL)

            val s = SpannableString(p.text)
            val u = units.getOrNull(cur)
            if (u != null && u.para == pi && lastHighlighted >= 0) {
                s.setSpan(BackgroundColorSpan(ContextCompat.getColor(this@ReaderActivity, R.color.highlight)),
                    u.start, u.end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
            h.en.text = s

            var downX = 0f; var downY = 0f; var downT = 0L
            h.en.setOnTouchListener { v, e ->
                when (e.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { downX = e.x; downY = e.y; downT = e.eventTime }
                    MotionEvent.ACTION_UP -> {
                        val moved = Math.abs(e.x - downX) + Math.abs(e.y - downY)
                        if (moved < 24 && e.eventTime - downT < 400 && p.kind != "ar") {
                            val off = (v as TextView).getOffsetForPosition(e.x, e.y)
                            TextUtil.wordAt(p.text, off)?.let { w ->
                                showWord(p.text.substring(w.start, w.end), pi, w.start)
                            }
                        }
                    }
                }
                false
            }

            val showTr = Prefs.showTranslation && p.speakable && doc.lang != "ar"
            h.tr.visibility = if (showTr) View.VISIBLE else View.GONE
            if (showTr) {
                val ar = Prefs.target == "ar"
                h.tr.textDirection = if (ar) View.TEXT_DIRECTION_RTL else View.TEXT_DIRECTION_LTR
                h.tr.layoutDirection = if (ar) View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR
                h.tr.textAlignment = View.TEXT_ALIGNMENT_VIEW_START
                h.tr.text = translationFor(pi, position) ?: getString(R.string.translating)
            }
        }
    }
}
