package io.github.snakemax.airag

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.webkit.JavascriptInterface
import android.webkit.WebView
import androidx.core.content.ContextCompat
import org.json.JSONObject

/**
 * Speech-to-text for the search box, using Android's own speech recognition.
 * The page calls window.AIRAGNative.startSpeech(lang); results come back through
 * window.airagSpeech({type: "partial" | "final" | "error" | "end", text}).
 */
class Speech(private val activity: MainActivity, private val web: WebView) {
    private var recognizer: SpeechRecognizer? = null
    private var pendingLang: String? = null

    @JavascriptInterface
    fun speechAvailable(): Boolean = SpeechRecognizer.isRecognitionAvailable(activity)

    @JavascriptInterface
    fun startSpeech(key: String, lang: String) {
        if (!NativeKey.ok(key)) return
        activity.runOnUiThread {
            if (ContextCompat.checkSelfPermission(activity, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                pendingLang = lang
                activity.micPermission.launch(Manifest.permission.RECORD_AUDIO)
            } else {
                listen(lang)
            }
        }
    }

    @JavascriptInterface
    fun stopSpeech() {
        activity.runOnUiThread { recognizer?.stopListening() }
    }

    fun onPermission(granted: Boolean) {
        val lang = pendingLang ?: return
        pendingLang = null
        if (granted) listen(lang) else send("error", "permission")
    }

    private fun listen(lang: String) {
        recognizer?.destroy()
        val r = SpeechRecognizer.createSpeechRecognizer(activity)
        recognizer = r
        r.setRecognitionListener(object : RecognitionListener {
            override fun onPartialResults(b: Bundle) = send("partial", first(b))
            override fun onResults(b: Bundle) { send("final", first(b)); send("end", "") }
            override fun onError(error: Int) {
                send("error", if (error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT) "nomatch" else "error$error")
                send("end", "")
            }
            override fun onReadyForSpeech(p: Bundle?) = send("ready", "")
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(t: Int, b: Bundle?) {}
        })
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        if (lang.isNotBlank()) intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang)
        r.startListening(intent)
    }

    private fun first(b: Bundle): String =
        b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull() ?: ""

    private fun send(type: String, text: String) {
        val payload = JSONObject().put("type", type).put("text", text).toString()
        activity.runOnUiThread { web.evaluateJavascript("window.airagSpeech && window.airagSpeech($payload)", null) }
    }

    fun destroy() { recognizer?.destroy(); recognizer = null }
}
