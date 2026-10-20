package dev.halixm.hokacepatcher

import android.Manifest
import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject

/**
 * The notification a finished run posts, and the one-time ask for the permission it needs.
 *
 * Android 13+ shows an app's notifications only once the player allows them. The patcher asks once,
 * when its first run is under way (Shizuku access is settled by then, so the two dialogs never stack),
 * and the run goes on whatever the answer. A result that leaves the game ready offers Open game; a
 * failure says Work stopped and opens the patcher. Nothing is posted while the patcher is on screen.
 */
data class RunNotification(val title: String, val text: String, val openGame: Boolean) {
    companion object {
        private const val CHANNEL = "result"
        private const val ID = 1403
        private const val PREFERENCES = "notifications"
        private const val ASKED = "permission_asked"
        const val REQUEST = 1403
        const val GAME = "com.tencent.tmgp.osgame"

        /** What the finished <state> posts in language <code>, or null for a step, a stop the player asked for, or Space freed. */
        fun of(code: String, state: JSONObject): RunNotification? {
            UiText.result(code, state)?.let { return if (it.gameReady) RunNotification(it.heading, it.summary, true) else null }
            return if (state.optString("status") in setOf("error", "recovery_required")) RunNotification(
                UiText.translate(code, "Work stopped"), UiText.translate(code, "Tap to see what happened and what to do next."), false)
            else null
        }

        /** Post the notification for finished <state>; a refused or absent permission only means nothing shows. */
        fun post(context: Context, state: JSONObject, patcherShown: Boolean) {
            if (patcherShown) return
            val note = of(PatchLanguage.current(context), state) ?: return
            runCatching {
                val manager = context.getSystemService(NotificationManager::class.java)
                manager.createNotificationChannel(NotificationChannel(CHANNEL, UiText.text(context, "Patch results"),
                    NotificationManager.IMPORTANCE_DEFAULT))
                val patcher = PendingIntent.getActivity(context, 3, Intent(context, MainActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                val builder = Notification.Builder(context, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download_done)
                    .setContentTitle(note.title).setContentText(note.text).setStyle(Notification.BigTextStyle().bigText(note.text))
                    .setContentIntent(patcher).setAutoCancel(true)
                val game = context.packageManager.getLaunchIntentForPackage(GAME)
                if (note.openGame && game != null) builder.addAction(Notification.Action.Builder(null, UiText.text(context, "Open game"),
                    PendingIntent.getActivity(context, 4, game, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)).build())
                manager.notify(ID, builder.build())
            }.onFailure { DiagnosticTrace.event("worker", "Result notification not posted: ${it.message}") }
        }

        /** Ask once, on Android 13+, while a run is under way; true when the ask was made now. */
        fun askOnce(activity: Activity): Boolean {
            if (Build.VERSION.SDK_INT < 33) return false
            if (activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return false
            val preferences = activity.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            if (preferences.getBoolean(ASKED, false)) return false
            preferences.edit().putBoolean(ASKED, true).apply()
            activity.requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST)
            return true
        }
    }
}
