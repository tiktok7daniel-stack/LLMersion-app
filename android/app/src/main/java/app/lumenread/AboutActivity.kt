package app.lumenread

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat

/** Version, privacy, upstream attribution and licences — in the interface language. */
class AboutActivity : BaseActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scroll)
        toolbar(getString(R.string.about))
        val box = findViewById<LinearLayout>(R.id.content)
        val dp = resources.displayMetrics.density
        val version = runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull() ?: ""

        box.addView(ImageView(this).apply {
            setImageResource(R.drawable.logo)
            layoutParams = LinearLayout.LayoutParams((88 * dp).toInt(), (88 * dp).toInt()).apply {
                gravity = Gravity.CENTER_HORIZONTAL; topMargin = (24 * dp).toInt()
            }
        })
        fun text(s: CharSequence, size: Float, color: Int, top: Int = 0, center: Boolean = false) =
            box.addView(TextView(this).apply {
                text = s; textSize = size; setTextColor(ContextCompat.getColor(context, color))
                setPadding(0, (top * dp).toInt(), 0, 0)
                if (center) gravity = Gravity.CENTER_HORIZONTAL
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        text(getString(R.string.app_name), 26f, R.color.text, 12, true)
        text(getString(R.string.tagline), 15f, R.color.text2, 2, true)
        text(getString(R.string.version_n, version), 13f, R.color.text3, 4, true)
        text(getString(R.string.subtitle), 15f, R.color.text2, 20)
        text(getString(R.string.about_privacy_title), 17f, R.color.text, 24)
        text(getString(R.string.privacy), 15f, R.color.text2, 6)
        text(getString(R.string.about_upstream_title), 17f, R.color.text, 24)
        text(getString(R.string.about_upstream), 15f, R.color.text2, 6)
        box.getChildAt(box.childCount - 1).setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/QM378/LLMersion")))
        }
        text(getString(R.string.about_license_title), 17f, R.color.text, 24)
        text(getString(R.string.about_license), 14f, R.color.text2, 6)
    }
}
