package app.lumenread

import android.app.Application
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader

class LumenApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Prefs.init(this)
        Db.init(this)
        PDFBoxResourceLoader.init(applicationContext)
        Prefs.applyNightMode()
    }
}
