package app.lumenread

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.appbar.MaterialToolbar

/** Applies the black theme when chosen, and gives every screen a toolbar with a back arrow
 *  (the arrow is mirrored automatically in Arabic). */
open class BaseActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        if (Prefs.theme == "black") setTheme(R.style.Theme_LumenRead_Black)
        super.onCreate(savedInstanceState)
    }

    protected fun toolbar(title: CharSequence?, back: Boolean = true): MaterialToolbar {
        val tb = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(tb)
        supportActionBar?.title = title
        if (back) {
            supportActionBar?.setDisplayHomeAsUpEnabled(true)
            tb.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }
        }
        return tb
    }

    protected fun toast(msg: CharSequence) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
