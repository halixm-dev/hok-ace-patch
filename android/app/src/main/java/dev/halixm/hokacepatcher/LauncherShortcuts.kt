package dev.halixm.hokacepatcher

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ShortcutInfo
import android.content.pm.ShortcutManager
import android.graphics.drawable.Icon

/**
 * The launcher icon's long-press shortcuts: Start patch, Save log for help and Check for updates.
 *
 * Each one taps the same home-screen action a player would, with the same checks. They open the
 * non-exported `ShortcutEntry` alias, which the launcher starts on this app's behalf, so no other app
 * can start a patch through them. They are published from the activity, in the patcher's own
 * language, and follow it when the language changes.
 */
object LauncherShortcuts {
    /** The home-screen action key, also the shortcut's id, with the label it shows. */
    private val SHORTCUTS = listOf(
        "start" to "Start patch",
        "export" to "Save log for help",
        "check_update" to "Check for updates",
    )
    private const val ALIAS = "dev.halixm.hokacepatcher.ShortcutEntry"
    private const val EXTRA = "home-action"

    /** Publish the shortcuts in the current language; a launcher that refuses them never fails the app. */
    fun publish(context: Context) {
        runCatching {
            val icon = Icon.createWithResource(context, R.mipmap.ic_launcher)
            context.getSystemService(ShortcutManager::class.java).dynamicShortcuts = SHORTCUTS.map { (key, label) ->
                val text = UiText.text(context, label)
                ShortcutInfo.Builder(context, key).setShortLabel(text).setLongLabel(text).setIcon(icon)
                    .setIntent(Intent(Intent.ACTION_VIEW).setComponent(ComponentName(context.packageName, ALIAS))
                        .putExtra(EXTRA, key))
                    .build()
            }
        }.onFailure { DiagnosticTrace.event("ui", "Launcher shortcuts not published: ${it.message}") }
    }

    /**
     * The home-screen action <intent> asks for, only when it came through the shortcut alias. Reopening
     * the app from Recents hands the same intent back; that is opening the app, so it asks for nothing.
     */
    fun action(intent: Intent?): String? = intent
        ?.takeIf { it.component?.className == ALIAS && it.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY == 0 }
        ?.getStringExtra(EXTRA)?.takeIf { key -> SHORTCUTS.any { it.first == key } }
}
