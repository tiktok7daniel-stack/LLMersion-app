package app.lumenread

import java.text.BreakIterator
import java.util.Locale

data class Span(val start: Int, val end: Int)

object TextUtil {
    private val arabic = Regex("[\\u0600-\\u06FF\\u0750-\\u077F\\u08A0-\\u08FF\\uFB50-\\uFDFF\\uFE70-\\uFEFF]")
    private val terminal = ".!?:;؟۔…\"'”)"

    fun arabicRatio(s: String): Double {
        val chars = s.filterNot { it.isWhitespace() }
        if (chars.isEmpty()) return 0.0
        return chars.count { arabic.matches(it.toString()) }.toDouble() / chars.length
    }

    /** Sentence boundaries, trimmed of surrounding spaces. */
    fun sentences(text: String): List<Span> {
        val it = BreakIterator.getSentenceInstance(Locale.US)
        it.setText(text)
        val out = mutableListOf<Span>()
        var start = it.first()
        var end = it.next()
        while (end != BreakIterator.DONE) {
            var s = start
            var e = end
            while (s < e && text[s].isWhitespace()) s++
            while (e > s && text[e - 1].isWhitespace()) e--
            if (e > s) out += Span(s, e)
            start = end
            end = it.next()
        }
        return out
    }

    /** The word under character offset `i`, or null. */
    fun wordAt(text: String, i: Int): Span? {
        if (i < 0 || i >= text.length) return null
        fun isW(c: Char) = c.isLetter() && c.code < 0x0590 || c == '\'' || c == '’' || c == '-'
        if (!text[i].isLetter() || text[i].code >= 0x0590) return null
        var s = i
        var e = i
        while (s > 0 && isW(text[s - 1])) s--
        while (e < text.length && isW(text[e])) e++
        while (s < e && !text[s].isLetter()) s++
        while (e > s && !text[e - 1].isLetter()) e--
        return if (e > s) Span(s, e) else null
    }

    /**
     * Rebuild paragraphs from extracted page text: blank lines (or the paragraph
     * marker PDFBox writes) split paragraphs, hyphenated line breaks are joined,
     * a short line with no closing punctuation becomes a heading.
     */
    fun paragraphs(page: Int, raw: String): List<Para> {
        val text = raw.replace("\r", "")
            .replace(Regex("([A-Za-z])-\\n([a-z])"), "$1$2")
        val out = mutableListOf<Para>()
        for (chunk in text.split(Regex("\\u2029|\\n\\s*\\n"))) {
            val lines = chunk.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
            if (lines.isEmpty()) continue
            val body = lines.joinToString(" ").replace(Regex("\\s+"), " ").trim()
            if (body.length < 2) continue
            val letters = body.count { it.isLetter() }
            val kind = when {
                letters < body.replace(" ", "").length * 0.5 -> "other"
                lines.size == 1 && body.length < 90 && body.last() !in terminal -> "heading"
                else -> "body"
            }
            out += Para(page, kind, body, "ltr")
        }
        return out
    }

    /** Direction and language tags; Arabic paragraphs are shown RTL and not spoken. */
    fun annotate(paras: List<Para>): Pair<List<Para>, String> {
        var ar = 0
        val out = paras.map {
            val r = arabicRatio(it.text)
            val dir = if (r > 0.3) "rtl" else "ltr"
            val kind = if (r > 0.5 && it.kind != "toc") "ar" else it.kind
            if (kind == "ar") ar++
            it.copy(kind = kind, dir = dir)
        }
        val lang = if (out.isNotEmpty() && ar * 2 > out.size) "ar" else "en"
        return out to lang
    }
}
