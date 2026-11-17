package io.github.snakemax.airag

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import android.webkit.MimeTypeMap
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.FileProvider
import org.json.JSONArray
import java.io.File
import java.lang.ref.WeakReference
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Things only Android can do, called from Python (airag/android_bridge.py).
 * Python calls these from worker threads, never from the UI thread.
 */
object Bridge {
    private var activityRef = WeakReference<MainActivity>(null)
    private var pickLatch: CountDownLatch? = null
    private var pickResult: String = ""

    fun attach(a: MainActivity) { activityRef = WeakReference(a) }
    fun detach(a: MainActivity) { if (activityRef.get() === a) activityRef = WeakReference(null) }
    private fun activity() = activityRef.get()

    /** Lets the user pick a folder; returns a file path, "" if cancelled, or "!permission" / "!unsupported". */
    @JvmStatic
    fun pickFolder(): String {
        val a = activity() ?: return ""
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && !Environment.isExternalStorageManager()) {
            a.runOnUiThread {
                val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + a.packageName))
                try { a.startActivity(intent) } catch (_: Exception) {
                    a.startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
                }
            }
            return "!permission"
        }
        val latch = CountDownLatch(1)
        pickLatch = latch
        pickResult = ""
        a.runOnUiThread { a.folderPicker.launch(null) }
        latch.await(10, TimeUnit.MINUTES)
        pickLatch = null
        return pickResult
    }

    fun onFolderPicked(a: MainActivity, uri: Uri?) {
        pickResult = if (uri == null) "" else treeUriToPath(uri) ?: "!unsupported"
        pickLatch?.countDown()
    }

    /** content://.../tree/primary:Documents/Vault -> /storage/emulated/0/Documents/Vault */
    private fun treeUriToPath(uri: Uri): String? {
        val id = try { DocumentsContract.getTreeDocumentId(uri) } catch (_: Exception) { return null }
        val parts = id.split(":", limit = 2)
        if (parts.size != 2) return null
        val (volume, rel) = parts
        val base = if (volume.equals("primary", ignoreCase = true))
            Environment.getExternalStorageDirectory().absolutePath
        else "/storage/$volume"
        val dir = if (rel.isEmpty()) File(base) else File(base, rel)
        return if (dir.isDirectory) dir.absolutePath else null
    }

    private fun uriFor(a: MainActivity, f: File): Uri =
        FileProvider.getUriForFile(a, a.packageName + ".files", f)

    /** Opens a file in whichever app handles its type. */
    @JvmStatic
    fun openFile(path: String) {
        val a = activity() ?: return
        val f = File(path)
        a.runOnUiThread {
            try {
                val ext = f.extension.lowercase()
                val mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "*/*"
                val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uriFor(a, f), mime)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                a.startActivity(Intent.createChooser(intent, f.name))
            } catch (e: Exception) {
                Toast.makeText(a, a.getString(R.string.no_app), Toast.LENGTH_SHORT).show()
            }
        }
    }

    /**
     * Loads a page in a hidden WebView and returns its HTML once loaded (or "" on timeout).
     * Used when a site blocks plain requests: the WebView looks like the phone's normal browser.
     * Images are not loaded, to save data and battery.
     */
    @JvmStatic
    fun renderPage(url: String, timeoutMs: Int): String {
        val a = activity() ?: return ""
        val latch = CountDownLatch(1)
        var html = ""
        var view: WebView? = null
        a.runOnUiThread {
            val w = WebView(a)
            view = w
            w.settings.javaScriptEnabled = true
            w.settings.domStorageEnabled = true
            w.settings.loadsImagesAutomatically = false
            w.settings.blockNetworkImage = true
            w.settings.mediaPlaybackRequiresUserGesture = true
            w.webViewClient = object : WebViewClient() {
                private var done = false
                override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest) = false
                override fun onPageFinished(v: WebView, u: String) {
                    if (done) return
                    // give scripts a moment to fill in the content
                    v.postDelayed({
                        if (done) return@postDelayed
                        done = true
                        v.evaluateJavascript("document.documentElement.outerHTML") { result ->
                            html = try { JSONArray("[$result]").getString(0) } catch (_: Exception) { "" }
                            latch.countDown()
                        }
                    }, 900)
                }
            }
            w.loadUrl(url)
        }
        latch.await(timeoutMs.toLong(), TimeUnit.MILLISECONDS)
        a.runOnUiThread { view?.stopLoading(); view?.destroy() }
        return html
    }

    /** An update waiting for the "install unknown apps" permission. */
    private var pendingApk: String? = null

    /**
     * Hands a downloaded update to Android's package installer. Without the "install unknown apps"
     * permission it opens that settings page instead and returns "permission"; the install then starts
     * by itself when the user comes back with the permission granted (see onResume).
     */
    @JvmStatic
    fun installApk(path: String): String {
        val a = activity() ?: return "error"
        if (!a.packageManager.canRequestPackageInstalls()) {
            pendingApk = path
            a.runOnUiThread { openInstallPermission(a) }
            return "permission"
        }
        a.runOnUiThread { launchInstaller(a, path) }
        return "ok"
    }

    private fun openInstallPermission(a: MainActivity) {
        try {
            a.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + a.packageName)))
        } catch (_: Exception) {
            a.startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
        }
    }

    private fun launchInstaller(a: MainActivity, path: String) {
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uriFor(a, File(path)), "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        a.startActivity(intent)
    }

    /** Called when AIRAG comes back to the front, e.g. from the permission settings page. */
    fun onResume(a: MainActivity) {
        val path = pendingApk ?: return
        if (!File(path).exists()) { pendingApk = null; return }
        if (a.packageManager.canRequestPackageInstalls()) {
            pendingApk = null
            launchInstaller(a, path)
        } else {
            AlertDialog.Builder(a)
                .setTitle(R.string.perm_title)
                .setMessage(R.string.perm_message)
                .setPositiveButton(R.string.perm_give) { _, _ -> openInstallPermission(a) }
                .setNegativeButton(R.string.perm_later) { _, _ -> pendingApk = null }
                .show()
        }
    }
}
