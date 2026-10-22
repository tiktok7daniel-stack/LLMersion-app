package app.lumenread

import android.app.Activity
import android.content.Intent
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.ContextCompat

/** The floating glass navigation pill shared by Home, Words, Review and Settings. */
object NavBar {
    enum class Tab { HOME, WORDS, REVIEW, SETTINGS, NONE }

    fun bind(a: Activity, selected: Tab) {
        val bar = a.findViewById<View>(R.id.navbar) ?: return
        if (selected == Tab.NONE) { bar.visibility = View.GONE; return }
        val items = listOf(
            Triple(R.id.navHome, Tab.HOME, MainActivity::class.java),
            Triple(R.id.navWords, Tab.WORDS, VocabActivity::class.java),
            Triple(R.id.navReview, Tab.REVIEW, FlashcardActivity::class.java),
            Triple(R.id.navSettings, Tab.SETTINGS, SettingsActivity::class.java),
        )
        for ((id, tab, cls) in items) {
            val item = a.findViewById<ViewGroup>(id)
            val on = tab == selected
            item.background = if (on) ContextCompat.getDrawable(a, R.drawable.bg_nav_selected) else null
            val color = ContextCompat.getColor(a, if (on) R.color.text else R.color.text3)
            (item.getChildAt(0) as ImageView).setColorFilter(color)
            (item.getChildAt(1) as TextView).setTextColor(color)
            item.setOnClickListener {
                if (on) return@setOnClickListener
                a.startActivity(Intent(a, cls).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
                @Suppress("DEPRECATION")
                a.overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
            }
        }
    }
}
