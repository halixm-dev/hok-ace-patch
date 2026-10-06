package dev.halixm.hokacepatcher

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri

/** Open installed Shizuku, otherwise its official Play listing, with a browser fallback. */
object ShizukuLauncher {
    const val PACKAGE = "moe.shizuku.privileged.api"
    const val STORE_URL = "https://play.google.com/store/apps/details?id=$PACKAGE"

    fun isInstalled(context: Context): Boolean = try {
        context.packageManager.getPackageInfo(PACKAGE, 0)
        true
    } catch (_: android.content.pm.PackageManager.NameNotFoundException) { false }

    fun open(context: Context): Boolean = open(
        context.packageManager.getLaunchIntentForPackage(PACKAGE)
    ) { context.startActivity(it) }

    /** Injectable launcher lets tests cover missing apps without uninstalling anything. */
    internal fun open(installed: Intent?, launch: (Intent) -> Unit): Boolean {
        val candidates = listOfNotNull(installed,
            Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$PACKAGE")).setPackage("com.android.vending"),
            Intent(Intent.ACTION_VIEW, Uri.parse(STORE_URL)))
        for (intent in candidates) {
            try { launch(intent); return true }
            catch (_: ActivityNotFoundException) { }
            catch (_: SecurityException) { }
        }
        return false
    }
}
