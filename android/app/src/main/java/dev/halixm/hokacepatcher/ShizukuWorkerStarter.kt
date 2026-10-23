package dev.halixm.hokacepatcher

import android.content.ComponentName
import android.content.Context
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.IBinder
import java.lang.reflect.InvocationTargetException
import rikka.shizuku.Shizuku
import rikka.shizuku.ShizukuRemoteProcess

/**
 * The Shizuku provider's [WorkerStarter]. It asks Shizuku for a user service first. Some ROMs crash inside
 * Shizuku's starter before the service class loads (see [ShellServiceStarter]), and nothing reports that
 * back: the binder simply never comes. After [SHIZUKU_SECONDS] it also starts the worker itself through
 * Shizuku's shell-process API, the connection takes whichever binder arrives first, and the starter
 * remembers per phone and Shizuku build that the second path was the one that worked, so later runs start
 * there. A Shizuku server running as root is refused: its worker would run as uid 0, which is the Root
 * provider's write path.
 */
class ShizukuWorkerStarter(context: Context) : WorkerStarter {
    private companion object {
        const val SHIZUKU_SECONDS = 10L
        const val SHIZUKU_APP = "moe.shizuku.privileged.api"
        const val PREFERENCES = "worker-starter"
        const val USER_SERVICE = "Shizuku user service"
    }
    private val appContext = context.applicationContext
    private val packages = appContext.packageManager
    private val guard = Any()
    private var link: WorkerLink? = null
    private var args: Shizuku.UserServiceArgs? = null
    private var bound = false
    private var process: ShizukuRemoteProcess? = null
    private var listening = false
    private val death = Shizuku.OnBinderDeadListener { link?.disconnected("Shizuku server disconnected") }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, connectedBinder: IBinder) {
            link?.attach(connectedBinder, USER_SERVICE)
        }
        override fun onServiceDisconnected(name: ComponentName) { link?.disconnected("Shizuku worker disconnected") }
    }

    override val patienceSeconds: Long get() = synchronized(guard) { if (bound && process == null) SHIZUKU_SECONDS else 0 }

    override fun start(link: WorkerLink) {
        this.link = link
        check(Shizuku.pingBinder()) { "Start Shizuku before starting a patch or recovery" }
        check(Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
            "Authorize HOK ACE in Shizuku before starting"
        }
        check(Shizuku.getUid() != WorkerAccess.ROOT_UID) { ShellProvider.SHIZUKU_AS_ROOT }
        Shizuku.addBinderDeadListener(death)
        synchronized(guard) { listening = true }
        if (preferences().getBoolean(phoneKey(), false)) {
            DiagnosticTrace.event("shizuku", "This phone needed the app's own starter before; starting it directly")
            startOwn(link)
        } else {
            val serviceArgs = Shizuku.UserServiceArgs(ComponentName(appContext, PrivilegedDeviceService::class.java))
                .daemon(false).processNameSuffix("worker").tag(link.tag)
                .version(PrivilegedDeviceService.PROTOCOL_VERSION)
            Shizuku.bindUserService(serviceArgs, connection)
            synchronized(guard) { args = serviceArgs; bound = true }
        }
    }

    override fun stalled(link: WorkerLink) {
        DiagnosticTrace.event("shizuku", "No binder from Shizuku's user-service starter after ${link.elapsed()} ms; " +
            "starting the worker with the app's own starter")
        startOwn(link)
    }

    /** Launch [WorkerLink.ownCommand] as shell through Shizuku. */
    private fun startOwn(link: WorkerLink) {
        synchronized(guard) { if (link.isClosed || process != null) return }
        val command = link.ownCommand()
        val started = try {
            Shizuku::class.java.getDeclaredMethod("newProcess", Array<String>::class.java, Array<String>::class.java,
                String::class.java).apply { isAccessible = true }.invoke(null, command, null, null) as ShizukuRemoteProcess
        } catch (error: InvocationTargetException) {
            link.forgetOwnCommand()
            throw error.targetException
        }
        val keep = synchronized(guard) { if (link.isClosed) false else { process = started; true } }
        if (!keep) { runCatching { started.destroy() }; return }
        DiagnosticTrace.event("shizuku", "Started the app's own worker starter after ${link.elapsed()} ms")
        link.watch(started.inputStream) { started.waitFor() }
    }

    private fun preferences() = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** A new ROM build or Shizuku release gets Shizuku's own starter tried again. */
    private fun phoneKey(): String {
        val app = runCatching { packages.getPackageInfo(SHIZUKU_APP, 0).longVersionCode }.getOrDefault(-1L)
        return "own:${Build.FINGERPRINT}:${runCatching { Shizuku.getVersion() }.getOrDefault(-1)}:$app"
    }

    override fun connected(path: String) {
        runCatching { preferences().edit().clear().putBoolean(phoneKey(), path == OWN_STARTER).apply() }
    }

    override fun environment(): String {
        val server = runCatching { "Shizuku ${Shizuku.getVersion()} uid ${Shizuku.getUid()}" }.getOrElse { "Shizuku unknown" }
        val app = runCatching { "app ${packages.getPackageInfo(SHIZUKU_APP, 0).versionName}" }.getOrElse { "app missing" }
        val ping = runCatching { Shizuku.pingBinder() }.getOrDefault(false)
        return "$server $app ping $ping, ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} API ${Build.VERSION.SDK_INT}"
    }

    override fun close() {
        val (unbind, started, listened) = synchronized(guard) {
            Triple(args.takeIf { bound }, process, listening).also { bound = false; process = null; listening = false }
        }
        if (listened) Shizuku.removeBinderDeadListener(death)
        if (unbind != null) runCatching { Shizuku.unbindUserService(unbind, connection, true) }
        started?.let { runCatching { it.destroy() } }
    }
}
