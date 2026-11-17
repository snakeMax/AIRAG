package io.github.snakemax.airag

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.Python
import java.io.File
import kotlin.concurrent.thread

/**
 * Starts the Python server (the same code as the desktop app) and shows its web UI.
 * Links to other sites open in the phone's browser.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var root: FrameLayout
    private lateinit var web: WebView
    private lateinit var splash: View
    private lateinit var splashText: TextView
    private var port = 0

    val folderPicker = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        Bridge.onFolderPicked(this, uri)
    }
    val filesPicker = registerForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        Bridge.onFilesPicked(uris)
    }
    val micPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        speech?.onPermission(granted)
    }
    private var speech: Speech? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Bridge.attach(this)
        buildViews()
        clearCacheAfterUpdate()
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (::web.isInitialized && web.canGoBack()) web.goBack()
                else { isEnabled = false; onBackPressedDispatcher.onBackPressed() }
            }
        })
        startServer()
    }

    private fun color(id: Int) = ContextCompat.getColor(this, id)

    @SuppressLint("SetJavaScriptEnabled")
    private fun buildViews() {
        root = FrameLayout(this).apply { setBackgroundColor(color(R.color.bg)) }
        web = WebView(this).apply {
            setBackgroundColor(color(R.color.bg))
            visibility = View.INVISIBLE
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = true
            settings.setSupportMultipleWindows(false)
            settings.useWideViewPort = true          // honour the page's viewport tag (no zoomed-out desktop layout)
            settings.loadWithOverviewMode = false
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val url = request.url
                    if (url.host == "127.0.0.1" && url.port == port) return false
                    openExternal(url)
                    return true
                }
                override fun onPageFinished(view: WebView, url: String) {
                    view.visibility = View.VISIBLE
                    splash.visibility = View.GONE
                }
            }
            webChromeClient = WebChromeClient()
        }
        speech = Speech(this, web).also { web.addJavascriptInterface(it, "AIRAGNative") }
        val bar = ProgressBar(this).apply { isIndeterminate = true }
        splashText = TextView(this).apply {
            text = getString(R.string.starting)
            setTextColor(color(R.color.fg))
            textSize = 15f
            gravity = Gravity.CENTER
            setPadding(48, 32, 48, 0)
        }
        splash = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(bar)
            addView(splashText)
        }
        val match = ViewGroup.LayoutParams.MATCH_PARENT
        root.addView(web, FrameLayout.LayoutParams(match, match))
        root.addView(splash, FrameLayout.LayoutParams(match, match))
        setContentView(root)
        // keep the page clear of the status bar, navigation bar and keyboard
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
    }

    /** After installing a new version, drop the WebView's cached copies of the old version's pages. */
    private fun clearCacheAfterUpdate() {
        val prefs = getSharedPreferences("airag", MODE_PRIVATE)
        val stamp = packageManager.getPackageInfo(packageName, 0).lastUpdateTime.toString()  // changes with every install
        if (prefs.getString("cache_stamp", null) != stamp) {
            web.clearCache(true)
            prefs.edit().putString("cache_stamp", stamp).apply()
        }
    }

    fun clearWebCache() = runOnUiThread { web.clearCache(true) }

    private fun startServer() {
        val dataDir = File(filesDir, "airag").absolutePath
        thread(name = "airag-start") {
            try {
                val zone = java.util.TimeZone.getDefault().id
                val p = Python.getInstance().getModule("airag.android_bridge").callAttr("start", dataDir, zone).toInt()
                runOnUiThread {
                    port = p
                    web.loadUrl("http://127.0.0.1:$p/")
                }
            } catch (e: Throwable) {
                runOnUiThread { splashText.text = getString(R.string.start_failed, e.message ?: e.toString()) }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        Bridge.onResume(this)
    }

    fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (_: Exception) { }
    }

    override fun onDestroy() {
        Bridge.detach(this)
        speech?.destroy()
        if (::web.isInitialized) web.destroy()
        super.onDestroy()
    }
}
