package app.lumenread

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
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
        toolbar("", back = false)
        list = findViewById(R.id.docs)
        empty = findViewById(R.id.empty)
        list.layoutManager = LinearLayoutManager(this)
        list.adapter = DocAdapter()

        findViewById<View>(R.id.openBtn).setOnClickListener {
            picker.launch(arrayOf("application/pdf", "text/plain", "text/markdown"))
        }
        findViewById<View>(R.id.pasteBtn).setOnClickListener { pasteDialog() }
        findViewById<View>(R.id.vocabBtn).setOnClickListener { startActivity(Intent(this, VocabActivity::class.java)) }
        findViewById<View>(R.id.settingsBtn).setOnClickListener { startActivity(Intent(this, SettingsActivity::class.java)) }

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

    private fun refresh() {
        lifecycleScope.launch {
            docs = withContext(Dispatchers.IO) { Db.listDocs() }
            list.adapter?.notifyDataSetChanged()
            empty.visibility = if (docs.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, R.string.tutor).setIcon(R.drawable.ic_chat)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        menu.add(0, 2, 1, R.string.about).setIcon(R.drawable.ic_info)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> startActivity(Intent(this, TutorActivity::class.java))
            2 -> startActivity(Intent(this, AboutActivity::class.java))
            else -> return super.onOptionsItemSelected(item)
        }
        return true
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
        val langs = arrayOf(getString(R.string.lang_system), getString(R.string.lang_en), getString(R.string.lang_ar))
        val codes = arrayOf("system", "en", "ar")
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
