package app.lumenread

import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext

/**
 * English -> Arabic, Italian or Chinese translation, on the device, with Google ML Kit.
 * The language model downloads once (~30 MB); after that it works offline.
 * Every result is cached by target + text, so a paragraph is translated once.
 */
object Tr {
    private val clients = mutableMapOf<String, Translator>()
    private val ready = mutableSetOf<String>()
    private val lock = Mutex()

    private fun client(target: String): Translator = clients.getOrPut(target) {
        Translation.getClient(
            TranslatorOptions.Builder()
                .setSourceLanguage(TranslateLanguage.ENGLISH)
                .setTargetLanguage(Langs.mlkit(target))
                .build()
        )
    }

    fun isReady(target: String) = target in ready

    /** Download the model if needed. Throws when it cannot be fetched. */
    suspend fun prepare(target: String) = lock.withLock {
        if (target !in ready) {
            client(target).downloadModelIfNeeded(DownloadConditions.Builder().build()).await()
            ready += target
        }
    }

    suspend fun translate(text: String, target: String = Prefs.target): String {
        val key = sha1(target, text)
        withContext(Dispatchers.IO) { Db.getTrans(key) }?.let { return it }
        prepare(target)
        val out = client(target).translate(text).await()
        withContext(Dispatchers.IO) { Db.putTrans(key, out) }
        return out
    }
}
