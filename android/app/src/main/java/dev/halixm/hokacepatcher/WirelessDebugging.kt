package dev.halixm.hokacepatcher

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.RemoteInput
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.provider.Settings
import java.io.File
import java.io.IOException
import java.net.ConnectException

/**
 * The wireless debugging provider: pairing once through a notification, and the per-phone state it leaves.
 *
 * The player opens *Wireless debugging → Pair device with pairing code*; the patcher's notification takes
 * the six-digit code as an inline reply, and [PairingReceiver] pairs [AdbKey] with `adbd`. The key stays in
 * no-backup storage; the paired flag only says pairing once succeeded, and a refused connection clears it.
 * Android enables wireless debugging only on Wi-Fi, and the patcher offers no way around that.
 */
object WirelessDebugging {
    const val NO_WIFI = "Wireless debugging needs Wi-Fi. Connect this phone to a Wi-Fi network, then tap Start again."
    const val NOT_PAIRED = "Pair the patcher with wireless debugging first. Tap Pair, then follow the steps above."
    const val SWITCHED_OFF = "Wireless debugging is off. Turn it on in Developer options, then tap Start again."
    const val REFUSED = "Wireless debugging no longer trusts the patcher. Tap Pair to pair it again."
    const val LOST = "Wireless debugging disconnected"
    /** The starter's refusals, each already the line the player reads. */
    val REFUSALS = listOf(NO_WIFI, NOT_PAIRED, SWITCHED_OFF, REFUSED)

    private const val PREFERENCES = "wireless-debugging"
    private const val PAIRED = "paired"
    private const val CHANNEL = "pairing"
    private const val NOTIFICATION = 1404
    private const val REPLY = 1404
    private const val CODE = "code"
    private const val LOCALHOST = "127.0.0.1"
    private const val PAIRING_SEARCH_MS = 8000L

    fun keyDirectory(context: Context) = File(context.noBackupFilesDir, "adb")

    fun paired(context: Context) = preferences(context).getBoolean(PAIRED, false) && AdbKey.exists(keyDirectory(context))

    /** `adbd` refused the key: the player removed the pairing or reset developer options. */
    fun forget(context: Context) { preferences(context).edit().putBoolean(PAIRED, false).commit() }

    fun onWifi(context: Context): Boolean = runCatching {
        val connectivity = context.getSystemService(ConnectivityManager::class.java)
        @Suppress("DEPRECATION")
        connectivity.allNetworks.any { connectivity.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true }
    }.getOrDefault(false)

    /** False only when Settings says wireless debugging is off; unreadable counts as on. */
    fun switchedOn(context: Context): Boolean =
        runCatching { Settings.Global.getInt(context.contentResolver, "adb_wifi_enabled") != 0 }.getOrDefault(true)

    /** <command> as one `sh -c` line for ADB's shell service, each argument single-quoted. */
    fun shellLine(command: Array<String>) = command.joinToString(" ") { "'" + it.replace("'", "'\\''") + "'" }

    /** Open Developer options at the Wireless debugging row. */
    fun openSettings(activity: Activity): Boolean {
        val developer = Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        // Settings' highlight of the Wireless debugging row, which Shizuku uses too; not every ROM honours it.
        val wireless = Intent(developer).putExtra(":settings:fragment_args_key", "toggle_adb_wireless")
        return runCatching { activity.startActivity(wireless) }.isSuccess || runCatching { activity.startActivity(developer) }.isSuccess
    }

    /** Post the notification that takes the pairing code; false when notifications are off. */
    fun askForCode(context: Context, text: String = UiText.text(context,
        "In Wireless debugging, tap Pair device with pairing code. Then type the six-digit code here.")): Boolean {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (!manager.areNotificationsEnabled()) return false
        manager.createNotificationChannel(NotificationChannel(CHANNEL, UiText.text(context, "Wireless debugging pairing"),
            NotificationManager.IMPORTANCE_HIGH).apply { setSound(null, null); setShowBadge(false) })
        val reply = PendingIntent.getBroadcast(context, REPLY,
            Intent(context, PairingReceiver::class.java).setComponent(ComponentName(context, PairingReceiver::class.java)),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
        val input = RemoteInput.Builder(CODE).setLabel(UiText.text(context, "Pairing code")).build()
        val action = Notification.Action.Builder(null, UiText.text(context, "Enter pairing code"), reply)
            .addRemoteInput(input).build()
        manager.notify(NOTIFICATION, Notification.Builder(context, CHANNEL).setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle(UiText.text(context, "Pair HOK ACE with wireless debugging")).setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text)).addAction(action).setOngoing(true).build())
        return true
    }

    private fun result(context: Context, title: String, text: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val patcher = PendingIntent.getActivity(context, NOTIFICATION, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        manager.notify(NOTIFICATION, Notification.Builder(context, CHANNEL).setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle(UiText.text(context, title)).setContentText(UiText.text(context, text))
            .setStyle(Notification.BigTextStyle().bigText(UiText.text(context, text)))
            .setContentIntent(patcher).setAutoCancel(true).build())
    }

    /** Find the pairing port and pair; the notification says how it went. */
    fun pair(context: Context, code: String) {
        DiagnosticTrace.init(context)
        val trimmed = code.filter { it.isDigit() }
        if (trimmed.length != 6) {
            askForCode(context, UiText.text(context, "That was not a six-digit code. Type the code Wireless debugging shows."))
            return
        }
        val failure = try {
            val port = AdbMdns.find(context, AdbMdns.PAIRING, PAIRING_SEARCH_MS)
                ?: throw IOException("No pairing service")
            DiagnosticTrace.event("adb", "Pairing with wireless debugging on port $port")
            AdbPairingClient(LOCALHOST, port, trimmed, AdbKey.load(keyDirectory(context))).pair()
            preferences(context).edit().putBoolean(PAIRED, true).commit()
            DiagnosticTrace.event("adb", "Paired with wireless debugging")
            null
        } catch (error: Exception) {
            DiagnosticTrace.error("adb", "Pairing failed", error)
            when {
                error is AdbWrongPairingCode -> "The code did not match. Check the code Wireless debugging shows, and type it again."
                error is ConnectException || error.message == "No pairing service" ->
                    "The pairing screen was not found. Keep Pair device with pairing code open, then type the code again."
                else -> "Pairing did not finish. Keep Pair device with pairing code open, then type the code again."
            }
        }
        if (failure == null) result(context, "Paired with wireless debugging", "Return to the patcher and tap Start.")
        else askForCode(context, UiText.text(context, failure))
    }

    private fun preferences(context: Context) = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** Takes the code from the notification's inline reply; pairing runs off the main thread. */
    class PairingReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val code = RemoteInput.getResultsFromIntent(intent)?.getCharSequence(CODE)?.toString() ?: return
            val pending = goAsync()
            val appContext = context.applicationContext
            Thread({
                try {
                    result(appContext, "Pairing…", "Checking the code with wireless debugging.")
                    pair(appContext, code)
                } catch (error: Throwable) {
                    DiagnosticTrace.error("adb", "Pairing receiver failed", error)
                } finally { pending.finish() }
            }, "hokace-pairing").start()
        }
    }
}

/**
 * The wireless debugging provider's [WorkerStarter]: one ADB connection to this phone's `adbd`, kept open
 * for the whole run, whose shell stream runs [WorkerLink.ownCommand] as uid 2000. The worker's process is
 * the shell command's, so losing the connection (wireless debugging switched off, Wi-Fi gone) ends it;
 * the stream's end is reported to the link at once, as a worker loss. Nothing is detached with `setsid`.
 */
class WirelessWorkerStarter(context: Context) : WorkerStarter {
    private companion object {
        const val CONNECT_SEARCH_MS = 10000L
        const val LOCALHOST = "127.0.0.1"
    }
    private val appContext = context.applicationContext
    private var client: AdbClient? = null
    private var port = -1

    override fun start(link: WorkerLink) {
        check(WirelessDebugging.onWifi(appContext)) { WirelessDebugging.NO_WIFI }
        check(WirelessDebugging.paired(appContext)) { WirelessDebugging.NOT_PAIRED }
        check(WirelessDebugging.switchedOn(appContext)) { WirelessDebugging.SWITCHED_OFF }
        // Discovery can miss this phone's own record; then the port is found by its answer.
        port = AdbMdns.find(appContext, AdbMdns.CONNECT, CONNECT_SEARCH_MS)
            ?: AdbMdns.scan()?.also { DiagnosticTrace.event("adb", "mDNS found no live port on this phone; found wireless debugging on port $it by scan") }
            ?: error(WirelessDebugging.SWITCHED_OFF)
        DiagnosticTrace.event("adb", "Connecting to wireless debugging on port $port")
        val connection = AdbClient(LOCALHOST, port, AdbKey.load(WirelessDebugging.keyDirectory(appContext)))
        client = connection
        try { connection.connect() } catch (refused: AdbNotPaired) {
            DiagnosticTrace.error("adb", "Wireless debugging refused the key", refused)
            WirelessDebugging.forget(appContext)
            error(WirelessDebugging.REFUSED)
        }
        val command = WirelessDebugging.shellLine(link.ownCommand())
        val output = try {
            connection.shell(command) { reason -> link.disconnected("${WirelessDebugging.LOST}: $reason") }
        } catch (error: Throwable) {
            link.forgetOwnCommand()
            throw error
        }
        DiagnosticTrace.event("adb", "Started the app's own worker starter over ADB after ${link.elapsed()} ms")
        link.watch(output) { null }
    }

    // Logged before start finds the port; start logs the port itself.
    override fun environment(): String =
        "Wireless debugging, ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} API ${Build.VERSION.SDK_INT}"

    override fun close() {
        client?.close()
        client = null
    }
}
