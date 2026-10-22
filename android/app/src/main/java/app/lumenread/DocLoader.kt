package app.lumenread

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.File

class NoTextException(val scanned: Boolean) : Exception()

/**
 * Turns a PDF or text file into a reading session. Text is extracted page by page
 * (page numbers are kept for "go to page"), scanned pages are read with on-device
 * OCR when it is enabled, and the result is cached by the file's hash so a document
 * is only ever processed once.
 */
object DocLoader {
    private const val MIN_CHARS = 25
    private const val CHARS_PER_PAGE = 1800

    fun displayName(c: Context, uri: Uri): String {
        c.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) return it.getString(0) ?: "document"
        }
        return uri.lastPathSegment ?: "document"
    }

    suspend fun open(c: Context, uri: Uri, progress: (Int, Int) -> Unit): Doc = withContext(Dispatchers.IO) {
        val bytes = c.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            ?: throw IllegalStateException("cannot read")
        val hash = java.security.MessageDigest.getInstance("SHA-1").digest(bytes)
            .joinToString("") { "%02x".format(it) }.take(16)
        Db.getDoc(hash)?.let { return@withContext it }
        val name = displayName(c, uri)
        val isPdf = name.lowercase().endsWith(".pdf") ||
            (bytes.size > 4 && String(bytes, 0, 4, Charsets.ISO_8859_1) == "%PDF")
        val doc = if (isPdf) pdf(c, bytes, hash, name, progress)
                  else text(hash, name.substringBeforeLast('.'), String(bytes, Charsets.UTF_8))
        Db.putDoc(doc)
        doc
    }

    fun fromText(title: String, body: String): Doc {
        val hash = sha1(title, body).take(16)
        Db.getDoc(hash)?.let { return it }
        val doc = text(hash, title, body)
        Db.putDoc(doc)
        return doc
    }

    private fun text(hash: String, title: String, body: String): Doc {
        val raw = TextUtil.paragraphs(0, body.replace("\n", "\n\n").replace(Regex("\\n{3,}"), "\n\n"))
        // plain text has no pages; invent them so "go to page" still works
        var page = 0
        var used = 0
        val paged = raw.map {
            if (used > 0 && used + it.text.length > CHARS_PER_PAGE) { page++; used = 0 }
            used += it.text.length
            it.copy(page = page)
        }
        if (paged.isEmpty()) throw NoTextException(false)
        val (paras, lang) = TextUtil.annotate(paged)
        return Doc(hash, title.ifBlank { "Untitled" }, page + 1, paras, lang)
    }

    private suspend fun pdf(c: Context, bytes: ByteArray, hash: String, name: String,
                            progress: (Int, Int) -> Unit): Doc {
        val dir = File(c.filesDir, "docs").apply { mkdirs() }
        val file = File(dir, "$hash.pdf").apply { if (!exists()) writeBytes(bytes) }
        val perPage = mutableMapOf<Int, List<Para>>()
        val blank = mutableListOf<Int>()
        var title = ""
        var pages = 0
        PDDocument.load(file).use { pd ->
            pages = pd.numberOfPages
            title = pd.documentInformation?.title?.trim().orEmpty()
            val stripper = PDFTextStripper()
            stripper.setSortByPosition(true)
            stripper.setParagraphStart("\u2029")
            for (p in 1..pages) {
                stripper.setStartPage(p)
                stripper.setEndPage(p)
                val t = stripper.getText(pd)
                if (t.trim().length < MIN_CHARS) blank += p - 1
                else perPage[p - 1] = TextUtil.paragraphs(p - 1, t)
            }
        }
        var skipped = 0
        if (blank.isNotEmpty()) {
            if (Prefs.ocr) ocr(file, blank, progress).forEach { (p, t) -> perPage[p] = TextUtil.paragraphs(p, t) }
            else skipped = blank.size
        }
        val all = (0 until pages).flatMap { perPage[it].orEmpty() }
        if (all.isEmpty()) throw NoTextException(scanned = blank.size == pages && !Prefs.ocr)
        val (paras, lang) = TextUtil.annotate(all)
        if (title.length < 3) title = paras.firstOrNull { it.kind == "heading" }?.text?.take(120)
            ?: name.substringBeforeLast('.')
        return Doc(hash, title, pages, paras, lang, skipped)
    }

    /** Render the given pages and read them with ML Kit (Latin script). */
    private suspend fun ocr(file: File, pages: List<Int>, progress: (Int, Int) -> Unit): Map<Int, String> {
        val out = mutableMapOf<Int, String>()
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
            PdfRenderer(fd).use { renderer ->
                pages.forEachIndexed { i, p ->
                    progress(i + 1, pages.size)
                    val page = renderer.openPage(p)
                    val scale = 2
                    val bmp = Bitmap.createBitmap(page.width * scale, page.height * scale, Bitmap.Config.ARGB_8888)
                    bmp.eraseColor(Color.WHITE)
                    page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    page.close()
                    val result = recognizer.process(InputImage.fromBitmap(bmp, 0)).await()
                    bmp.recycle()
                    out[p] = result.textBlocks.joinToString("\n\n") { it.text }
                }
            }
        }
        recognizer.close()
        return out
    }
}
