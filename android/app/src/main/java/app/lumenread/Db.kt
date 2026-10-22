package app.lumenread

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

data class Para(val page: Int, val kind: String, val text: String, val dir: String) {
    val speakable get() = kind == "body" || kind == "heading"
}

data class Doc(val hash: String, val title: String, val pages: Int, val paras: List<Para>,
               val lang: String = "en", val ocrSkipped: Int = 0)

data class Word(
    val word: String, val ar: String, val zh: String, val ipa: String, val context: String,
    val added: Long, val hits: Int, val known: Boolean, val box: Int, val due: Long,
) {
    fun gloss(target: String) = if (target == "zh") zh else ar
}

fun sha1(vararg parts: String): String {
    val md = MessageDigest.getInstance("SHA-1")
    parts.forEach { md.update(it.toByteArray()); md.update(0) }
    return md.digest().joinToString("") { "%02x".format(it) }
}

/** Documents (cached by file hash), translations, vocabulary and reading positions. */
object Db {
    private lateinit var helper: SQLiteOpenHelper
    private val db: SQLiteDatabase get() = helper.writableDatabase

    fun init(c: Context) {
        helper = object : SQLiteOpenHelper(c, "lumen.db", null, 1) {
            override fun onCreate(d: SQLiteDatabase) {
                d.execSQL("CREATE TABLE doc (hash TEXT PRIMARY KEY, title TEXT, pages INTEGER, json TEXT, added INTEGER)")
                d.execSQL("CREATE TABLE progress (hash TEXT PRIMARY KEY, unit INTEGER)")
                d.execSQL("CREATE TABLE trans (k TEXT PRIMARY KEY, v TEXT)")
                d.execSQL("CREATE TABLE vocab (word TEXT PRIMARY KEY, ar TEXT, zh TEXT, ipa TEXT, context TEXT, added INTEGER, hits INTEGER, known INTEGER, box INTEGER, due INTEGER)")
            }
            override fun onUpgrade(d: SQLiteDatabase, o: Int, n: Int) {}
        }
    }

    // ------------------------------------------------------------ documents
    fun putDoc(d: Doc) {
        val arr = JSONArray()
        d.paras.forEach {
            arr.put(JSONObject().put("p", it.page).put("k", it.kind).put("t", it.text).put("d", it.dir))
        }
        val json = JSONObject().put("paras", arr).put("lang", d.lang).put("skipped", d.ocrSkipped)
        db.insertWithOnConflict("doc", null, ContentValues().apply {
            put("hash", d.hash); put("title", d.title); put("pages", d.pages)
            put("json", json.toString()); put("added", System.currentTimeMillis())
        }, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun getDoc(hash: String): Doc? =
        db.rawQuery("SELECT title, pages, json FROM doc WHERE hash=?", arrayOf(hash)).use { c ->
            if (!c.moveToFirst()) return null
            val o = JSONObject(c.getString(2))
            val arr = o.getJSONArray("paras")
            val paras = (0 until arr.length()).map {
                val p = arr.getJSONObject(it)
                Para(p.getInt("p"), p.getString("k"), p.getString("t"), p.getString("d"))
            }
            Doc(hash, c.getString(0), c.getInt(1), paras, o.optString("lang", "en"), o.optInt("skipped", 0))
        }

    /** (hash, title, pages), newest first */
    fun listDocs(): List<Triple<String, String, Int>> =
        db.rawQuery("SELECT hash, title, pages FROM doc ORDER BY added DESC LIMIT 100", null).use { c ->
            buildList { while (c.moveToNext()) add(Triple(c.getString(0), c.getString(1), c.getInt(2))) }
        }

    fun deleteDoc(hash: String) {
        db.delete("doc", "hash=?", arrayOf(hash))
        db.delete("progress", "hash=?", arrayOf(hash))
    }

    fun clearDocs() {
        db.delete("doc", null, null)
        db.delete("progress", null, null)
    }

    fun getProgress(hash: String): Int =
        db.rawQuery("SELECT unit FROM progress WHERE hash=?", arrayOf(hash)).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    fun setProgress(hash: String, unit: Int) {
        db.insertWithOnConflict("progress", null, ContentValues().apply {
            put("hash", hash); put("unit", unit)
        }, SQLiteDatabase.CONFLICT_REPLACE)
    }

    // ------------------------------------------------------------ translations
    fun getTrans(key: String): String? =
        db.rawQuery("SELECT v FROM trans WHERE k=?", arrayOf(key)).use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }

    fun putTrans(key: String, v: String) {
        db.insertWithOnConflict("trans", null, ContentValues().apply { put("k", key); put("v", v) },
            SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun clearTrans() { db.delete("trans", null, null) }

    // ------------------------------------------------------------ vocabulary
    fun addWord(word: String, gloss: String, target: String, ipa: String, context: String) {
        val w = word.trim().lowercase()
        val existing = db.rawQuery("SELECT hits FROM vocab WHERE word=?", arrayOf(w)).use { c ->
            if (c.moveToFirst()) c.getInt(0) else -1
        }
        if (existing >= 0) {
            db.execSQL("UPDATE vocab SET hits=hits+1 WHERE word=?", arrayOf(w))
            if (gloss.isNotEmpty()) setGloss(w, target, gloss)
            return
        }
        db.insert("vocab", null, ContentValues().apply {
            put("word", w); put("ar", if (target == "ar") gloss else "")
            put("zh", if (target == "zh") gloss else ""); put("ipa", ipa); put("context", context)
            put("added", System.currentTimeMillis()); put("hits", 1); put("known", 0)
            put("box", 0); put("due", 0L)
        })
    }

    fun setGloss(word: String, target: String, gloss: String) {
        val col = if (target == "zh") "zh" else "ar"
        db.execSQL("UPDATE vocab SET $col=? WHERE word=? AND ($col IS NULL OR $col='')", arrayOf(gloss, word))
    }

    fun deleteWord(word: String) { db.delete("vocab", "word=?", arrayOf(word)) }

    fun setKnown(word: String, known: Boolean) {
        db.execSQL("UPDATE vocab SET known=? WHERE word=?", arrayOf(if (known) 1 else 0, word))
    }

    fun review(word: String, grade: Int) {
        val box = db.rawQuery("SELECT box FROM vocab WHERE word=?", arrayOf(word)).use { c ->
            if (c.moveToFirst()) c.getInt(0) else return
        }
        val (nb, due) = Srs.next(box, grade, System.currentTimeMillis())
        db.execSQL("UPDATE vocab SET box=?, due=? WHERE word=?", arrayOf(nb, due, word))
    }

    fun words(): List<Word> =
        db.rawQuery("SELECT word, ar, zh, ipa, context, added, hits, known, box, due FROM vocab ORDER BY added DESC", null).use { c ->
            buildList {
                while (c.moveToNext()) add(Word(c.getString(0), c.getString(1) ?: "", c.getString(2) ?: "",
                    c.getString(3) ?: "", c.getString(4) ?: "", c.getLong(5), c.getInt(6),
                    c.getInt(7) == 1, c.getInt(8), c.getLong(9)))
            }
        }
}

/** Leitner boxes: a correct card waits 1, 2, 4, 8, 16, 32 days; a miss comes back in 10 minutes. */
object Srs {
    private const val MIN = 60_000L
    private const val DAY = 86_400_000L
    private val waits = longArrayOf(10 * MIN, DAY, 2 * DAY, 4 * DAY, 8 * DAY, 16 * DAY, 32 * DAY)

    fun next(box: Int, grade: Int, now: Long): Pair<Int, Long> {
        val b = box.coerceIn(0, waits.size - 1)
        val nb = when (grade) {
            0 -> 0
            1 -> b
            2 -> minOf(b + 1, waits.size - 1)
            else -> minOf(b + 2, waits.size - 1)
        }
        var wait = waits[nb]
        if (grade == 1) wait = maxOf(wait, DAY)
        return nb to now + wait
    }
}
