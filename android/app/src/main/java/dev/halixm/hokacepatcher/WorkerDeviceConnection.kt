package dev.halixm.hokacepatcher

import android.content.ComponentName
import android.content.Context
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import java.lang.reflect.InvocationTargetException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import java.util.UUID
import rikka.shizuku.Shizuku
import rikka.shizuku.ShizukuRemoteProcess

/**
 * The foreground worker owns its binding independently of activity recreation.
 *
 * It asks Shizuku for a user service first. Some ROMs crash inside Shizuku's starter before the service
 * class loads (see [ShellServiceStarter]), and nothing reports that back: the binder simply never comes.
 * After [SHIZUKU_SECONDS] the connection also starts the worker itself through Shizuku's shell-process
 * API, takes whichever binder arrives first, and remembers per phone and Shizuku build that the second
 * path was the one that worked, so later runs start there.
 */
class WorkerDeviceConnection(context: Context, private val lost: () -> Unit) : AutoCloseable {
    private companion object {
        // A cold app_process start of this APK on a slow phone; a delivered binder returns at once.
        const val CONNECT_SECONDS = 45L
        const val SHIZUKU_SECONDS = 10L
        const val SHIZUKU_APP = "moe.shizuku.privileged.api"
        const val PREFERENCES = "worker-starter"
        const val OUTPUT_LINES = 200
    }
    private val appContext = context.applicationContext
    private val packages = appContext.packageManager
    private val bindStarted = android.os.SystemClock.elapsedRealtime()
    private val service = AtomicReference<IPrivilegedDeviceService?>(null)
    private val connected = CountDownLatch(1)
    private val guard = Any()
    private var closed = false
    private var failure: String? = null
    private var binder: IBinder? = null
    private var recipient: IBinder.DeathRecipient? = null
    private var via: String? = null
    private var bound = false
    private var process: ShizukuRemoteProcess? = null
    // Held for the connection's lifetime: the shell starter exits when this binder dies.
    private val client = Binder()
    private val tag = "hokace-worker-${UUID.randomUUID()}"
    private val token = UUID.randomUUID().toString()
    private val args = Shizuku.UserServiceArgs(ComponentName(context, PrivilegedDeviceService::class.java))
        .daemon(false).processNameSuffix("worker").tag(tag)
        .version(PrivilegedDeviceService.PROTOCOL_VERSION)
    private val death = Shizuku.OnBinderDeadListener { disconnected("Shizuku server disconnected") }

    private fun elapsed() = android.os.SystemClock.elapsedRealtime() - bindStarted

    private fun disconnected(message: String, expected: IBinder? = null) {
        DiagnosticTrace.event("shizuku", "$message after ${elapsed()} ms ($tag)")
        val notify = synchronized(guard) {
            if (closed || failure != null || (expected != null && binder !== expected)) false
            else {
                failure = message
                service.set(null)
                connected.countDown()
                true
            }
        }
        if (notify) runCatching { lost() }.onFailure {
            DiagnosticTrace.error("shizuku", "Could not persist service-loss recovery state", it)
        }
    }

    /** Accept the first worker binder from either path; a later one is refused. */
    private fun attach(connectedBinder: IBinder, path: String): Boolean {
        DiagnosticTrace.event("shizuku", "Worker binder from $path after ${elapsed()} ms, " +
            "binder alive ${connectedBinder.isBinderAlive}")
        var failed = false
        synchronized(guard) {
            if (closed || failure != null || binder != null) {
                DiagnosticTrace.event("shizuku", "Ignoring worker binder from $path; connection already settled by $via")
                return false
            }
            binder = connectedBinder
            via = path
            val deathRecipient = IBinder.DeathRecipient {
                disconnected("Shizuku worker disconnected ($path)", connectedBinder)
            }
            recipient = deathRecipient
            try {
                connectedBinder.linkToDeath(deathRecipient, 0)
                service.set(IPrivilegedDeviceService.Stub.asInterface(connectedBinder))
                connected.countDown()
            } catch (error: android.os.RemoteException) {
                DiagnosticTrace.error("shizuku", "Cannot watch the worker binder", error)
                failed = true
            }
        }
        if (failed) disconnected("Shizuku worker disconnected ($path)", connectedBinder)
        return !failed
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, connectedBinder: IBinder) {
            attach(connectedBinder, "Shizuku user service")
        }
        override fun onServiceDisconnected(name: ComponentName) { disconnected("Shizuku worker disconnected") }
    }

    init {
        DiagnosticTrace.event("shizuku", "Connecting worker $tag: ${environment()}")
        check(Shizuku.pingBinder()) { "Start Shizuku before starting a patch or recovery" }
        check(Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
            "Authorize HOK ACE in Shizuku before starting"
        }
        Shizuku.addBinderDeadListener(death)
        try {
            if (preferences().getBoolean(phoneKey(), false)) {
                DiagnosticTrace.event("shizuku", "This phone needed the app's own starter before; starting it directly")
                startOwn()
            } else {
                Shizuku.bindUserService(args, connection)
                synchronized(guard) { bound = true }
            }
        } catch (error: Throwable) {
            DiagnosticTrace.error("shizuku", "Worker start refused", error)
            Shizuku.removeBinderDeadListener(death)
            WorkerBinderProvider.forget(token)
            throw error
        }
    }

    fun await(): IPrivilegedDeviceService {
        val first = synchronized(guard) { bound && process == null }
        if (first && !connected.await(SHIZUKU_SECONDS, TimeUnit.SECONDS)) {
            DiagnosticTrace.event("shizuku", "No binder from Shizuku's user-service starter after ${elapsed()} ms; " +
                "starting the worker with the app's own starter")
            runCatching { startOwn() }.onFailure {
                DiagnosticTrace.error("shizuku", "The app's own starter could not be launched", it)
            }
        }
        val remaining = CONNECT_SECONDS * 1000 - elapsed()
        if (!connected.await(maxOf(remaining, 0), TimeUnit.MILLISECONDS)) {
            val detail = environment()
            DiagnosticTrace.event("shizuku", "No worker binder after ${elapsed()} ms from either starter; Shizuku server " +
                "ping ${runCatching { Shizuku.pingBinder() }.getOrDefault(false)}")
            error("Shizuku worker connection timed out ($detail)")
        }
        return synchronized(guard) {
            check(!closed) { "Shizuku worker connection closed" }
            check(failure == null) { failure!! }
            checkNotNull(service.get()).also { check(it.asBinder().isBinderAlive) { "Shizuku worker disconnected" } }
        }.also { remember() }
    }

    /** Launch [ShellServiceStarter] as shell through Shizuku, with this APK as its class path. */
    private fun startOwn() {
        synchronized(guard) { if (closed || process != null) return }
        WorkerBinderProvider.expect(token) { delivered -> if (attach(delivered, "app's own starter")) client else null }
        val apk = appContext.applicationInfo.sourceDir
        val command = arrayOf("/system/bin/sh", "-c",
            "CLASSPATH=\"\$1\" exec /system/bin/app_process /system/bin --nice-name=\"\$2\" " +
                "${ShellServiceStarter::class.java.name} \"\$3\" \"\$4\" 2>&1",
            "hokace-worker", apk, "${appContext.packageName}:worker", token, WorkerBinderProvider.authority(appContext))
        val started = try {
            Shizuku::class.java.getDeclaredMethod("newProcess", Array<String>::class.java, Array<String>::class.java,
                String::class.java).apply { isAccessible = true }.invoke(null, command, null, null) as ShizukuRemoteProcess
        } catch (error: InvocationTargetException) {
            WorkerBinderProvider.forget(token)
            throw error.targetException
        }
        val keep = synchronized(guard) { if (closed) false else { process = started; true } }
        if (!keep) { runCatching { started.destroy() }; return }
        DiagnosticTrace.event("shizuku", "Started the app's own worker starter after ${elapsed()} ms")
        Thread({ watch(started) }, "hokace-worker-starter").apply { isDaemon = true }.start()
    }

    /** Trace the starter's output; if it exits before handing over a binder, fail now instead of timing out. */
    private fun watch(started: ShizukuRemoteProcess) {
        runCatching {
            started.inputStream.bufferedReader().useLines { lines ->
                lines.take(OUTPUT_LINES).forEach { DiagnosticTrace.event("starter", it) }
            }
        }
        val code = runCatching { started.waitFor() }.getOrNull()
        DiagnosticTrace.event("starter", "Own worker starter exited with code $code after ${elapsed()} ms")
        val pending = synchronized(guard) { binder == null && !closed }
        if (pending) disconnected("The app's own worker starter exited with code $code before connecting")
    }

    private fun preferences() = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** A new ROM build or Shizuku release gets Shizuku's own starter tried again. */
    private fun phoneKey(): String {
        val app = runCatching { packages.getPackageInfo(SHIZUKU_APP, 0).longVersionCode }.getOrDefault(-1L)
        return "own:${Build.FINGERPRINT}:${runCatching { Shizuku.getVersion() }.getOrDefault(-1)}:$app"
    }

    private fun remember() {
        val own = synchronized(guard) { via == "app's own starter" }
        runCatching { preferences().edit().clear().putBoolean(phoneKey(), own).apply() }
    }

    private fun environment(): String {
        val server = runCatching { "Shizuku ${Shizuku.getVersion()} uid ${Shizuku.getUid()}" }.getOrElse { "Shizuku unknown" }
        val app = runCatching { "app ${packages.getPackageInfo(SHIZUKU_APP, 0).versionName}" }.getOrElse { "app missing" }
        return "$server $app, ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} API ${Build.VERSION.SDK_INT}, ${CONNECT_SECONDS}s"
    }

    override fun close() {
        val (unbind, started) = synchronized(guard) {
            if (closed) return
            closed = true
            DiagnosticTrace.event("shizuku", "Closing worker $tag via $via after ${elapsed()} ms")
            binder?.let { target -> recipient?.let { runCatching { target.unlinkToDeath(it, 0) } } }
            binder = null
            recipient = null
            service.set(null)
            connected.countDown()
            bound to process
        }
        WorkerBinderProvider.forget(token)
        Shizuku.removeBinderDeadListener(death)
        if (unbind) runCatching { Shizuku.unbindUserService(args, connection, true) }
        started?.let { runCatching { it.destroy() } }
    }
}
