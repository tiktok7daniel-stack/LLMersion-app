package app.lumenread

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.Bundle
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * Optional: the conversation tutor and writing feedback need a large language model,
 * which runs in the LumenRead server on the learner's computer. This screen shows that
 * server's interface when one is configured in Settings. Everything else in the app
 * works without it.
 */
class TutorActivity : BaseActivity() {
    private var pending: PermissionRequest? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = Prefs.serverUrl.trim().trimEnd('/')
        if (url.isEmpty()) { toast(getString(R.string.tutor_needs_server)); finish(); return }
        val web = WebView(this)
        setContentView(web)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.mediaPlaybackRequiresUserGesture = false
        web.webViewClient = object : WebViewClient() {
            override fun onReceivedError(v: WebView, r: WebResourceRequest, e: WebResourceError) {
                if (r.isForMainFrame) { toast(getString(R.string.tutor_unreachable)); finish() }
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(request.resources)
                } else {
                    pending = request
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 7)
                }
            }
        }
        web.loadUrl(if (url.startsWith("http")) url else "http://$url")
    }

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        pending?.let {
            if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED) it.grant(it.resources) else it.deny()
        }
        pending = null
    }
}
