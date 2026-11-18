package io.github.snakemax.airag

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import android.util.Base64
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

/**
 * "Share to AIRAG" for pictures and screenshots: the shared image is shrunk, turned into a data URL and
 * handed to the web UI (window.AIRAGShare.take()), which opens "Analyze image".
 */
class ShareBridge(private val activity: MainActivity, private val web: WebView) {
    @Volatile private var pending: String? = null
    @Volatile private var pendingFile: String? = null

    /** The web UI asks for the shared picture once it has loaded (or when told one arrived). */
    @JavascriptInterface
    fun take(key: String): String {
        if (!NativeKey.ok(key)) return ""
        val p = pending ?: ""
        pending = null
        return p
    }

    /** A file opened with (or shared to) AIRAG: {"name": ..., "data": base64} as JSON. */
    @JavascriptInterface
    fun takeFile(key: String): String {
        if (!NativeKey.ok(key)) return ""
        val p = pendingFile ?: ""
        pendingFile = null
        return p
    }

    fun handle(intent: Intent?) {
        if (intent == null) return
        if (intent.action == Intent.ACTION_VIEW && intent.data != null) return openDocument(intent.data!!)
        if (intent.action != Intent.ACTION_SEND) return
        if (intent.type?.startsWith("image/") != true) {
            streamOf(intent)?.let { openDocument(it) }
            return
        }
        val uri: Uri = streamOf(intent) ?: return
        thread(name = "airag-share") {
            val data = try { encode(uri) } catch (e: Throwable) { null } ?: return@thread
            pending = data
            activity.runOnUiThread { web.evaluateJavascript("window.dispatchEvent(new Event('airag-share'))", null) }
        }
    }

    /** Reads a file (up to 20 MB) and hands it to the page, which opens it without the AI. */
    private fun openDocument(uri: Uri) {
        thread(name = "airag-open") {
            val json = try {
                var name = "file.md"
                activity.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                    if (c.moveToFirst()) {
                        c.getString(0)?.let { name = it }
                        if (!c.isNull(1) && c.getLong(1) > MAX_FILE) throw IllegalArgumentException("too big")
                    }
                }
                val bytes = activity.contentResolver.openInputStream(uri)?.use { input ->
                    val out = ByteArrayOutputStream()
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        if (out.size() > MAX_FILE) throw IllegalArgumentException("too big")
                    }
                    out.toByteArray()
                } ?: return@thread
                // raw bytes as base64: AIRAG reads Word, Excel, CSV, SQLite... as well as text
                JSONObject().put("name", name).put("data", Base64.encodeToString(bytes, Base64.NO_WRAP)).toString()
            } catch (e: Throwable) {
                JSONObject().put("name", "").put("error", if (e.message == "too big") "big" else "read").toString()
            }
            pendingFile = json
            activity.runOnUiThread { web.evaluateJavascript("window.dispatchEvent(new Event('airag-share'))", null) }
        }
    }

    private companion object { const val MAX_FILE = 20L * 1024 * 1024 }

    @Suppress("DEPRECATION")
    private fun streamOf(intent: Intent): Uri? =
        if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)

    /** Reads the picture, scales it to at most 1600 px on the long side and returns a JPEG data URL. */
    private fun encode(uri: Uri): String? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        activity.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 1600) sample *= 2
        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        var bmp = activity.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) } ?: return null
        val long = maxOf(bmp.width, bmp.height)
        if (long > 1600) {
            val f = 1600f / long
            bmp = Bitmap.createScaledBitmap(bmp, (bmp.width * f).toInt(), (bmp.height * f).toInt(), true)
        }
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 88, out)
        return "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }
}
