package app.lumenread

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import java.util.Locale

/**
 * The phone's own text-to-speech, in English. One utterance per sentence, so the
 * reader knows exactly which sentence is being spoken and can highlight it.
 */
class Speaker(context: Context, private val onReady: (Boolean) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    var onStart: (String) -> Unit = {}
    var onDone: (String) -> Unit = {}
    private var ok = false

    private lateinit var tts: TextToSpeech

    init {
        // the init callback may run before the constructor returns, so `tts` is assigned first
        tts = TextToSpeech(context.applicationContext) { status -> main.post { configure(status) } }
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            // this@Speaker: the bare names would call the listener's own methods
            override fun onStart(id: String) { main.post { this@Speaker.onStart(id) } }
            override fun onDone(id: String) { main.post { this@Speaker.onDone(id) } }
            @Deprecated("Deprecated in Java")
            override fun onError(id: String) { main.post { this@Speaker.onDone(id) } }
        })
    }

    private fun configure(status: Int) {
        ok = status == TextToSpeech.SUCCESS
        if (ok) {
            val r = tts.setLanguage(Locale.US)
            ok = r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED
            if (ok) {
                englishVoices().firstOrNull { it.name == Prefs.voice }?.let { tts.voice = it }
                tts.setSpeechRate(Prefs.speed)
            }
        }
        onReady(ok)
    }

    val ready get() = ok

    fun englishVoices(): List<Voice> = try {
        tts.voices.orEmpty().filter { it.locale.language == "en" && !it.isNetworkConnectionRequired }
            .sortedBy { it.name }
    } catch (e: Exception) { emptyList() }

    fun setRate(r: Float) { tts.setSpeechRate(r) }

    fun setVoice(name: String) {
        englishVoices().firstOrNull { it.name == name }?.let { tts.voice = it }
    }

    fun speak(text: String, id: String, flush: Boolean = true) {
        tts.speak(text, if (flush) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null, id)
    }

    fun stop() { tts.stop() }

    fun shutdown() { tts.stop(); tts.shutdown() }
}
