package io.github.snakemax.airag

import android.content.Context
import android.media.AudioManager
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * window.AIRAGAudio in the web page: the phone's media volume (AIRAG's master volume on Android)
 * and reading text aloud with the phone's own text-to-speech voices.
 */
class AudioBridge(private val activity: MainActivity, private val web: WebView) {
    private val audio = activity.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var tts: TextToSpeech? = null
    private var ready = false
    private val waiting = mutableListOf<() -> Unit>()

    @JavascriptInterface
    fun getMediaVolume(): Int {
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        return Math.round(audio.getStreamVolume(AudioManager.STREAM_MUSIC) * 100f / max)
    }

    @JavascriptInterface
    fun setMediaVolume(key: String, percent: Int) {
        if (!NativeKey.ok(key)) return
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        val v = Math.round(percent.coerceIn(0, 100) * max / 100f)
        try { audio.setStreamVolume(AudioManager.STREAM_MUSIC, v, 0) } catch (_: SecurityException) { /* Do Not Disturb */ }
    }

    // ------------------------------------------------------------ text to speech
    private fun withTts(block: () -> Unit) {
        activity.runOnUiThread {
            if (ready) { block(); return@runOnUiThread }
            waiting.add(block)
            if (tts != null) return@runOnUiThread
            tts = TextToSpeech(activity) { status ->
                ready = status == TextToSpeech.SUCCESS
                if (!ready) { send("error", "", "unavailable"); waiting.clear(); return@TextToSpeech }
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(id: String) = send("start", id)
                    override fun onDone(id: String) = send("done", id)
                    @Deprecated("old API") override fun onError(id: String) = send("error", id, "error")
                    override fun onError(id: String, code: Int) = send("error", id, "error$code")
                    override fun onStop(id: String, interrupted: Boolean) = send("stopped", id)
                    // the word being spoken (start offset in the text), so Resume can carry on from it
                    override fun onRangeStart(id: String, start: Int, end: Int, frame: Int) = send("range", id, start.toString())
                })
                waiting.toList().forEach { it() }
                waiting.clear()
            }
        }
    }

    /** Warms the engine up and reports the voices to window.airagTts({type: "voices", voices: [...]}). */
    @JavascriptInterface
    fun ttsVoices() {
        withTts {
            val arr = JSONArray()
            try {
                tts?.voices?.filter { it.features?.contains("notInstalled") != true }
                    ?.sortedBy { it.name }
                    ?.forEach { v ->
                        arr.put(JSONObject().put("id", v.name).put("name", v.name).put("lang", v.locale.toLanguageTag())
                            .put("network", v.isNetworkConnectionRequired).put("quality", v.quality))
                    }
            } catch (_: Exception) { }
            val payload = JSONObject().put("type", "voices").put("voices", arr).toString()
            web.post { web.evaluateJavascript("window.airagTts && window.airagTts($payload)", null) }
        }
    }

    @JavascriptInterface
    fun ttsSpeak(key: String, text: String, voice: String, lang: String, rate: Float, id: String) {
        if (!NativeKey.ok(key)) return
        withTts {
            val t = tts ?: return@withTts
            val chosen = t.voices?.firstOrNull { it.name == voice }
            if (chosen != null) t.voice = chosen
            else if (lang.isNotBlank()) t.language = Locale.forLanguageTag(lang)
            t.setSpeechRate(rate.coerceIn(0.5f, 2.0f))
            val params = Bundle().apply { putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, id) }
            t.speak(text.take(TextToSpeech.getMaxSpeechInputLength() - 1), TextToSpeech.QUEUE_FLUSH, params, id)
        }
    }

    @JavascriptInterface
    fun ttsStop() { activity.runOnUiThread { tts?.stop() } }

    private fun send(type: String, id: String, error: String = "") {
        val payload = JSONObject().put("type", type).put("id", id).put("error", error).put("detail", error).toString()
        web.post { web.evaluateJavascript("window.airagTts && window.airagTts($payload)", null) }
    }

    fun destroy() { tts?.shutdown(); tts = null; ready = false }
}
