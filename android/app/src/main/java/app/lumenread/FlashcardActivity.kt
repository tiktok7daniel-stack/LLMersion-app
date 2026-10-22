package app.lumenread

import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import com.google.android.material.progressindicator.LinearProgressIndicator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Spaced-repetition flashcards. Front: the English word (always left-to-right).
 * Back: the meaning in Arabic (right-to-left) or Chinese — optional, switched in the
 * vocabulary screen — plus the sentence it came from.
 */
class FlashcardActivity : BaseActivity() {
    private var cards: List<Word> = emptyList()
    private var i = 0
    private var back = false
    private var speaker: Speaker? = null
    private lateinit var word: TextView
    private lateinit var ipa: TextView
    private lateinit var gloss: TextView
    private lateinit var ctx: TextView
    private lateinit var hint: TextView
    private lateinit var grades: View
    private lateinit var rail: LinearProgressIndicator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_flash)
        toolbar(getString(R.string.flashcards))
        word = findViewById(R.id.word); ipa = findViewById(R.id.ipa); gloss = findViewById(R.id.gloss)
        ctx = findViewById(R.id.ctx); hint = findViewById(R.id.hint); grades = findViewById(R.id.grades)
        rail = findViewById(R.id.rail)
        speaker = Speaker(this) {}

        findViewById<View>(R.id.card).setOnClickListener { back = !back; paint() }
        findViewById<View>(R.id.say).setOnClickListener { cards.getOrNull(i)?.let { speaker?.speak(it.word, "w") } }
        findViewById<View>(R.id.prev).setOnClickListener { step(-1) }
        findViewById<View>(R.id.next).setOnClickListener { step(1) }
        listOf(R.id.g0, R.id.g1, R.id.g2, R.id.g3).forEachIndexed { g, id ->
            findViewById<View>(id).setOnClickListener { grade(g) }
        }

        lifecycleScope.launch {
            val now = System.currentTimeMillis()
            cards = withContext(Dispatchers.IO) { Db.words() }
                .filter { !it.known }
                .sortedWith(compareBy<Word> { it.due > now }.thenBy { it.due }.thenBy { it.added })
            if (cards.isEmpty()) { toast(getString(R.string.no_cards)); finish(); return@launch }
            paint()
        }
    }

    override fun onDestroy() {
        speaker?.shutdown()
        super.onDestroy()
    }

    private fun step(d: Int) {
        if (cards.isEmpty()) return
        i = (i + d + cards.size) % cards.size
        back = false
        paint()
    }

    private fun grade(g: Int) {
        val w = cards.getOrNull(i) ?: return
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { Db.review(w.word, g) }
            step(1)
        }
    }

    private fun paint() {
        val w = cards.getOrNull(i) ?: return
        supportActionBar?.subtitle = getString(R.string.card_n, i + 1, cards.size)
        rail.max = cards.size
        rail.progress = i + 1
        word.text = w.word
        ipa.text = if (w.ipa.isNotEmpty()) "/${w.ipa}/" else ""
        val target = Prefs.target
        gloss.textDirection = if (target == "ar") View.TEXT_DIRECTION_RTL else View.TEXT_DIRECTION_LTR
        gloss.visibility = if (back && Prefs.flashGloss) View.VISIBLE else View.GONE
        ctx.visibility = if (back && w.context.isNotEmpty()) View.VISIBLE else View.GONE
        ctx.text = w.context
        hint.visibility = if (back) View.GONE else View.VISIBLE
        grades.alpha = if (back) 1f else 0.4f
        grades.isEnabled = back
        gloss.text = w.gloss(target).ifEmpty { "…" }
        if (back && Prefs.flashGloss && w.gloss(target).isEmpty()) {
            lifecycleScope.launch {
                val g = try { Tr.translate(w.word, target) } catch (e: Exception) { "" }
                if (g.isNotEmpty()) {
                    withContext(Dispatchers.IO) { Db.setGloss(w.word, target, g) }
                    cards = cards.toMutableList().also {
                        it[i] = if (target == "zh") w.copy(zh = g) else w.copy(ar = g)
                    }
                }
                if (cards.getOrNull(i)?.word == w.word) gloss.text = g.ifEmpty { getString(R.string.not_found) }
            }
        }
    }
}
