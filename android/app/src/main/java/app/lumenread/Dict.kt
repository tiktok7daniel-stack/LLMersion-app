package app.lumenread

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.zip.GZIPInputStream

data class Entry(val word: String, val ipa: String, val definition: String, val lemmaOf: String = "")

/**
 * Offline English dictionary: IPA (CMU Pronouncing Dictionary) and definitions (WordNet 3.0),
 * shipped as assets/dict.bin (gzip) and unpacked into SQLite on first run. Built by
 * tools/build_android_dict.py.
 */
object Dict {
    private var helper: SQLiteOpenHelper? = null
    @Volatile var ready = false
        private set

    private fun db(c: Context): SQLiteDatabase {
        val h = helper ?: object : SQLiteOpenHelper(c.applicationContext, "dict.db", null, 1) {
            override fun onCreate(d: SQLiteDatabase) {
                d.execSQL("CREATE TABLE dict (word TEXT PRIMARY KEY, ipa TEXT, def TEXT)")
            }
            override fun onUpgrade(d: SQLiteDatabase, o: Int, n: Int) {}
        }.also { helper = it }
        return h.writableDatabase
    }

    /** Unpack the bundled dictionary once. Blocking; call off the main thread. */
    @Synchronized
    fun ensureLoaded(c: Context) {
        if (ready) return
        val d = db(c)
        val n = d.rawQuery("SELECT COUNT(*) FROM dict", null).use { if (it.moveToFirst()) it.getInt(0) else 0 }
        if (n > 0) { ready = true; return }
        d.beginTransaction()
        try {
            val st = d.compileStatement("INSERT OR REPLACE INTO dict (word, ipa, def) VALUES (?,?,?)")
            BufferedReader(InputStreamReader(GZIPInputStream(c.assets.open("dict.bin")), Charsets.UTF_8)).use { r ->
                r.lineSequence().forEach { line ->
                    val f = line.split('\t')
                    if (f.size >= 3) {
                        st.clearBindings()
                        st.bindString(1, f[0]); st.bindString(2, f[1]); st.bindString(3, f[2])
                        st.executeInsert()
                    }
                }
            }
            d.setTransactionSuccessful()
        } finally {
            d.endTransaction()
        }
        ready = true
    }

    private val irregular = mapOf(
        "went" to "go", "gone" to "go", "was" to "be", "were" to "be", "is" to "be", "are" to "be",
        "been" to "be", "am" to "be", "had" to "have", "has" to "have", "did" to "do", "done" to "do",
        "said" to "say", "made" to "make", "took" to "take", "taken" to "take", "saw" to "see",
        "seen" to "see", "came" to "come", "knew" to "know", "known" to "know", "got" to "get",
        "gave" to "give", "given" to "give", "found" to "find", "thought" to "think", "told" to "tell",
        "became" to "become", "left" to "leave", "felt" to "feel", "brought" to "bring", "began" to "begin",
        "kept" to "keep", "held" to "hold", "wrote" to "write", "written" to "write", "stood" to "stand",
        "heard" to "hear", "meant" to "mean", "met" to "meet", "ran" to "run", "paid" to "pay",
        "sat" to "sit", "spoke" to "speak", "spoken" to "speak", "led" to "lead", "read" to "read",
        "grew" to "grow", "grown" to "grow", "lost" to "lose", "fell" to "fall", "fallen" to "fall",
        "sent" to "send", "built" to "build", "understood" to "understand", "children" to "child",
        "men" to "man", "women" to "woman", "people" to "person", "feet" to "foot", "teeth" to "tooth",
        "mice" to "mouse", "better" to "good", "best" to "good", "worse" to "bad", "worst" to "bad",
    )

    /** Candidate base forms for an inflected word ("studies" -> "study"). */
    fun lemmas(w: String): List<String> {
        val out = mutableListOf<String>()
        irregular[w]?.let { out += it }
        val rules = listOf("ies" to listOf("y"), "es" to listOf("", "e"), "s" to listOf(""),
            "ied" to listOf("y"), "ed" to listOf("", "e"), "ing" to listOf("", "e"),
            "est" to listOf("", "e"), "er" to listOf("", "e"), "ly" to listOf(""))
        for ((suf, reps) in rules) {
            if (w.endsWith(suf) && w.length > suf.length + 2) {
                val stem = w.dropLast(suf.length)
                reps.forEach { out += stem + it }
                if (stem.length > 2 && stem[stem.length - 1] == stem[stem.length - 2]) out += stem.dropLast(1)
            }
        }
        return out
    }

    fun lookup(c: Context, raw: String): Entry? {
        val w = raw.trim().lowercase().trim('\'', '’', '-')
        if (w.isEmpty()) return null
        ensureLoaded(c)
        val d = db(c)
        fun row(x: String): Entry? =
            d.rawQuery("SELECT ipa, def FROM dict WHERE word=?", arrayOf(x)).use {
                if (it.moveToFirst()) Entry(x, it.getString(0) ?: "", it.getString(1) ?: "") else null
            }
        val direct = row(w)
        if (direct != null && direct.definition.isNotEmpty()) return direct
        for (l in lemmas(w)) {
            val e = row(l) ?: continue
            if (e.definition.isNotEmpty()) {
                return e.copy(ipa = direct?.ipa?.takeIf { it.isNotEmpty() } ?: e.ipa, lemmaOf = l)
            }
        }
        return direct
    }
}
