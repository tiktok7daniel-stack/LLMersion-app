package app.lumenread

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.SpannableString
import android.text.Spannable
import android.text.style.ForegroundColorSpan
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.ProgressBar
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.materialswitch.MaterialSwitch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Library: open a PDF or text file, paste text, reopen recent documents. */
class MainActivity : BaseActivity() {
    private lateinit var list: RecyclerView
    private lateinit var empty: TextView
    private var docs: List<Triple<String, String, Int>> = emptyList()

    private val picker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) openUri(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.Theme_LumenRead)          // leave the splash theme
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        NavBar.bind(this, NavBar.Tab.HOME)
        headline()
        list = findViewById(R.id.docs)
        empty = findViewById(R.id.empty)
        list.layoutManager = LinearLayoutManager(this)
        list.adapter = DocAdapter()

        findViewById<View>(R.id.openBtn).setOnClickListener {
            picker.launch(arrayOf("application/pdf", "text/plain", "text/markdown"))
        }
        findViewById<View>(R.id.pasteBtn).setOnClickListener { pasteDialog() }
        findViewById<View>(R.id.tutorBtn).setOnClickListener { startActivity(Intent(this, TutorActivity::class.java)) }
        findViewById<View>(R.id.aboutBtn).setOnClickListener { startActivity(Intent(this, AboutActivity::class.java)) }
        findViewById<View>(R.id.statDueBox).setOnClickListener { startActivity(Intent(this, FlashcardActivity::class.java)) }

        // unpack the offline dictionary in the background on first run
        lifecycleScope.launch(Dispatchers.IO) { runCatching { Dict.ensureLoaded(applicationContext) } }

        if (!Prefs.onboarded) onboarding()
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun handleIntent(i: Intent?) {
        val uri: Uri? = when (i?.action) {
            Intent.ACTION_VIEW -> i.data
            Intent.ACTION_SEND ->
                if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else @Suppress("DEPRECATION") i.getParcelableExtra(Intent.EXTRA_STREAM)
            else -> null
        }
        if (uri != null) openUri(uri)
        else if (i?.action == Intent.ACTION_SEND) {
            i.getStringExtra(Intent.EXTRA_TEXT)?.let { openText(getString(R.string.pasted_title), it) }
        }
    }

    /** "Read. Listen. Speak. Understand." with the last word in the brand gold. */
    private fun headline() {
        val text = getString(R.string.tagline).replace(". ", ".\n")
        val s = SpannableString(text)
        val lastStart = text.trimEnd('.', ' ').lastIndexOf('\n') + 1
        s.setSpan(ForegroundColorSpan(ContextCompat.getColor(this, R.color.accent)),
            lastStart, text.length, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
        findViewById<TextView>(R.id.headline).text = s
    }

    private fun refresh() {
        lifecycleScope.launch {
            docs = withContext(Dispatchers.IO) { Db.listDocs() }
            val words = withContext(Dispatchers.IO) { Db.words() }
            list.adapter?.notifyDataSetChanged()
            empty.visibility = if (docs.isEmpty()) View.VISIBLE else View.GONE

            val now = System.currentTimeMillis()
            findViewById<TextView>(R.id.statWords).text = words.size.toString()
            findViewById<TextView>(R.id.statLearned).text = words.count { it.known }.toString()
            findViewById<TextView>(R.id.statDue).text = words.count { !it.known && it.due <= now }.toString()

            // the hero card continues the most recent document, or invites you to open one
            val hero = findViewById<View>(R.id.hero)
            val first = docs.firstOrNull()
            if (first == null) {
                findViewById<TextView>(R.id.heroLabel).setText(R.string.start_reading)
                findViewById<TextView>(R.id.heroTitle).setText(R.string.start_reading_sub)
                findViewById<TextView>(R.id.heroMeta).text = ""
                findViewById<ProgressBar>(R.id.heroProgress).visibility = View.GONE
                hero.setOnClickListener { picker.launch(arrayOf("application/pdf", "text/plain", "text/markdown")) }
            } else {
                val (hash, title, pages) = first
                val (done, total) = withContext(Dispatchers.IO) { readingProgress(hash) }
                findViewById<TextView>(R.id.heroLabel).setText(R.string.continue_reading)
                findViewById<TextView>(R.id.heroTitle).text = title
                findViewById<TextView>(R.id.heroMeta).text =
                    getString(R.string.pages_n, pages) + "  ·  " + (if (total > 0) 100 * done / total else 0) + "%"
                findViewById<ProgressBar>(R.id.heroProgress).apply {
                    visibility = View.VISIBLE; max = maxOf(1, total); progress = done
                }
                hero.setOnClickListener { openReader(hash) }
            }
        }
    }

    /** (sentences read, sentences in total) for a cached document */
    private fun readingProgress(hash: String): Pair<Int, Int> {
        val d = Db.getDoc(hash) ?: return 0 to 0
        val total = d.paras.filter { it.speakable }.sumOf { TextUtil.sentences(it.text).size }
        return Db.getProgress(hash).coerceAtMost(total) to total
    }

    // ------------------------------------------------------------ opening
    private fun openUri(uri: Uri) {
        val status = TextView(this).apply { setPadding(64, 48, 64, 16); setText(R.string.opening) }
        val dlg = MaterialAlertDialogBuilder(this).setView(status).setCancelable(false).show()
        lifecycleScope.launch {
            try {
                val doc = DocLoader.open(this@MainActivity, uri) { done, total ->
                    runOnUiThread { status.text = getString(R.string.ocr_progress, done, total) }
                }
                dlg.dismiss()
                if (doc.ocrSkipped > 0) toast(getString(R.string.ocr_skipped))
                openReader(doc.hash)
            } catch (e: NoTextException) {
                dlg.dismiss()
                toast(getString(if (e.scanned) R.string.scanned_no_ocr else R.string.no_text))
            } catch (e: Exception) {
                dlg.dismiss()
                toast(getString(R.string.open_failed, e.message ?: e.javaClass.simpleName))
            }
        }
    }

    private fun openText(title: String, body: String) {
        lifecycleScope.launch {
            try {
                val doc = withContext(Dispatchers.IO) { DocLoader.fromText(title, body) }
                openReader(doc.hash)
            } catch (e: Exception) {
                toast(getString(R.string.no_text))
            }
        }
    }

    private fun openReader(hash: String) {
        startActivity(Intent(this, ReaderActivity::class.java).putExtra("hash", hash))
    }

    private fun pasteDialog() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 16, 48, 0) }
        val title = EditText(this).apply { setHint(R.string.doc_title_hint); isSingleLine = true }
        val body = EditText(this).apply {
            setHint(R.string.paste_hint); minLines = 5; maxLines = 12
            textDirection = View.TEXT_DIRECTION_LTR
        }
        box.addView(title); box.addView(body)
        MaterialAlertDialogBuilder(this).setTitle(R.string.paste_title).setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                val t = body.text.toString()
                if (t.isNotBlank()) openText(title.text.toString().ifBlank { getString(R.string.pasted_title) }, t)
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    // ------------------------------------------------------------ first run
    private fun onboarding() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(56, 8, 56, 0) }
        box.addView(TextView(this).apply { setText(R.string.welcome_body); setPadding(0, 0, 0, 24) })
        val tr = MaterialSwitch(this).apply { setText(R.string.welcome_translation); isChecked = Prefs.showTranslation }
        box.addView(tr)
        val langs = arrayOf(getString(R.string.lang_system), getString(R.string.lang_en),
            getString(R.string.lang_ar), getString(R.string.lang_it))
        val codes = arrayOf("system", "en", "ar", "it")
        var chosen = codes.indexOf(Prefs.uiLang).coerceAtLeast(0)
        val dlg: AlertDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.welcome)
            .setSingleChoiceItems(langs, chosen) { _, which -> chosen = which }
            .setView(box)
            .setCancelable(false)
            .setPositiveButton(R.string.get_started) { _, _ ->
                Prefs.showTranslation = tr.isChecked
                Prefs.onboarded = true
                if (Prefs.uiLang != codes[chosen]) {
                    Prefs.uiLang = codes[chosen]
                    Prefs.applyLanguage()          // recreates the activity in the new language
                }
            }
            .create()
        dlg.show()
    }

    // ------------------------------------------------------------ list
    private inner class DocAdapter : RecyclerView.Adapter<DocAdapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val title: TextView = v.findViewById(R.id.title)
            val meta: TextView = v.findViewById(R.id.meta)
        }
        override fun onCreateViewHolder(p: ViewGroup, t: Int) =
            H(LayoutInflater.from(p.context).inflate(R.layout.item_doc, p, false))
        override fun getItemCount() = docs.size
        override fun onBindViewHolder(h: H, i: Int) {
            val (hash, title, pages) = docs[i]
            h.title.text = title
            h.meta.text = getString(R.string.pages_n, pages)
            h.itemView.setOnClickListener { openReader(hash) }
            h.itemView.setOnLongClickListener {
                MaterialAlertDialogBuilder(this@MainActivity).setTitle(title)
                    .setPositiveButton(R.string.delete_doc) { _, _ ->
                        lifecycleScope.launch { withContext(Dispatchers.IO) { Db.deleteDoc(hash) }; refresh() }
                    }
                    .setNegativeButton(R.string.cancel, null).show()
                true
            }
        }
    }
}
