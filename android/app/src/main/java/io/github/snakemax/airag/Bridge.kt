package io.github.snakemax.airag

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.core.content.FileProvider
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

    /** Hands a downloaded update to Android's package installer. */
    @JvmStatic
    fun installApk(path: String) {
        val a = activity() ?: return
        a.runOnUiThread {
            if (!a.packageManager.canRequestPackageInstalls()) {
                a.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + a.packageName)))
                return@runOnUiThread
            }
            val intent = Intent(Intent.ACTION_VIEW)
                .setDataAndType(uriFor(a, File(path)), "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            a.startActivity(intent)
        }
    }
}
