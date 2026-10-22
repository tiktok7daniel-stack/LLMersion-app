package app.lumenread

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.materialswitch.MaterialSwitch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** The self-building vocabulary: every tapped word lands here. */
class VocabActivity : BaseActivity() {
    private var words: List<Word> = emptyList()
    private lateinit var list: RecyclerView
    private var speaker: Speaker? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_list)
        toolbar(getString(R.string.vocabulary), back = false)
        NavBar.bind(this, NavBar.Tab.WORDS)
        list = findViewById(R.id.list)
        list.layoutManager = LinearLayoutManager(this)
        list.adapter = Adapter()
        speaker = Speaker(this) {}
        findViewById<MaterialSwitch>(R.id.glossSwitch).apply {
            isChecked = Prefs.flashGloss
            setOnCheckedChangeListener { _, on -> Prefs.flashGloss = on }
        }
        findViewById<View>(R.id.flashBtn).setOnClickListener {
            startActivity(Intent(this, FlashcardActivity::class.java))
        }
    }

    override fun onResume() {
        super.onResume()
        load()
    }

    override fun onDestroy() {
        speaker?.shutdown()
        super.onDestroy()
    }

    @SuppressLint("NotifyDataSetChanged")
    private fun load() {
        lifecycleScope.launch {
            words = withContext(Dispatchers.IO) { Db.words() }
            findViewById<TextView>(R.id.stat).text =
                getString(R.string.vocab_count, words.size, words.count { it.known })
            findViewById<View>(R.id.empty).visibility = if (words.isEmpty()) View.VISIBLE else View.GONE
            list.adapter?.notifyDataSetChanged()
            fillGlosses()
        }
    }

    /** Words saved while the other translation language was active get their gloss now. */
    private suspend fun fillGlosses() {
        for (lang in Prefs.wordLangs) {
            words.filter { it.gloss(lang).isEmpty() }.take(40).forEach { w ->
                val g = try { Tr.translate(w.word, lang) } catch (e: Exception) { return }
                withContext(Dispatchers.IO) { Db.setGloss(w.word, lang, g) }
                val i = words.indexOfFirst { it.word == w.word }
                if (i >= 0) {
                    words = words.toMutableList().also { it[i] = it[i].withGloss(lang, g) }
                    list.adapter?.notifyItemChanged(i)
                }
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, R.string.share_csv).setIcon(R.drawable.ic_share)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId != 1) return super.onOptionsItemSelected(item)
        val csv = buildString {
            append("word,ipa,arabic,italian,chinese,context\n")
            words.forEach { w ->
                listOf(w.word, w.ipa, w.ar, w.it, w.zh, w.context).joinTo(this, ",") { "\"" + it.replace("\"", "\"\"") + "\"" }
                append('\n')
            }
        }
        val f = java.io.File(cacheDir, "vocabulary.csv").apply { writeText("﻿" + csv) }
        val uri = FileProvider.getUriForFile(this, "$packageName.files", f)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/csv"; putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, getString(R.string.share_csv)))
        return true
    }

    private inner class Adapter : RecyclerView.Adapter<Adapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val word: TextView = v.findViewById(R.id.word)
            val gloss: TextView = v.findViewById(R.id.gloss)
        }
        override fun onCreateViewHolder(p: ViewGroup, t: Int) =
            H(LayoutInflater.from(p.context).inflate(R.layout.item_word, p, false))
        override fun getItemCount() = words.size
        override fun onBindViewHolder(h: H, i: Int) {
            val w = words[i]
            h.word.text = if (w.ipa.isNotEmpty()) "${w.word}  /${w.ipa}/" else w.word
            h.word.alpha = if (w.known) 0.5f else 1f
            // e.g. "مضيء · luminoso" — each meaning keeps its own direction (Unicode isolates)
            h.gloss.text = Prefs.wordLangs.map { w.gloss(it) }.filter { it.isNotEmpty() }
                .joinToString("  ·  ") { "\u2068$it\u2069" }
            h.gloss.textDirection = View.TEXT_DIRECTION_LOCALE
            h.gloss.textAlignment = View.TEXT_ALIGNMENT_VIEW_START
            h.itemView.findViewById<View>(R.id.say).setOnClickListener { speaker?.speak(w.word, "w") }
            h.itemView.findViewById<View>(R.id.del).setOnClickListener {
                lifecycleScope.launch { withContext(Dispatchers.IO) { Db.deleteWord(w.word) }; load() }
            }
        }
    }
}
