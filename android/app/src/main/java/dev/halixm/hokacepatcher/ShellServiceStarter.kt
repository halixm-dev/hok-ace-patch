package dev.halixm.hokacepatcher

import android.content.AttributionSource
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.os.Looper
import android.os.Process
import android.util.Log
import kotlin.system.exitProcess

/**
 * Shell-side entry point for the worker when Shizuku's own user-service starter cannot run.
 *
 * Shizuku's starter builds the target app's Application before it loads the service class. MediaTek's
 * `LoadedApk.makeApplicationInner` then calls `Application.getProcessName().equals(...)`, which is null in
 * that process, so every user service dies before any code of ours runs (measured on an Infinix X6853,
 * Android 16). [PrivilegedDeviceService] needs no Context, so this starter skips that step. The app starts
 * it through Shizuku's shell-process API with this APK as the class path, and it hands the binder to
 * [WorkerBinderProvider] with the one-time token it was given. Runs under app_process as uid 2000, or as
 * uid 0 when the Root provider starts it through `su`.
 */
object ShellServiceStarter {
    const val ATTACH = "attach"
    const val BINDER = "binder"
    const val CLIENT = "client"
    private const val SHELL = "com.android.shell"
    /** The package Android's app ops resolve uid 0 to. */
    private const val ROOT = "root"

    @JvmStatic
    fun main(args: Array<String>) {
        try {
            check(args.size == 2) { "usage: ShellServiceStarter <token> <authority>" }
            val (token, authority) = args
            @Suppress("DEPRECATION") Looper.prepareMainLooper()
            val service = PrivilegedDeviceService()
            val client = handOff(authority, token, service)
            // The app holds this binder for the connection's lifetime; its death means nobody can use us.
            client.linkToDeath({ println("app connection gone; exiting"); exitProcess(0) }, 0)
            // The app cannot signal a uid-0 process; RootWorkerStarter closes su's input instead.
            if (Process.myUid() == WorkerAccess.ROOT_UID) Thread({
                runCatching { while (System.`in`.read() >= 0) { } }
                println("su input closed; exiting"); exitProcess(0)
            }, "hokace-root-input").apply { isDaemon = true }.start()
            println("worker attached as uid ${Process.myUid()} pid ${Process.myPid()}")
            Looper.loop()
        } catch (error: Throwable) {
            println("worker starter failed: ${Log.getStackTraceString(error)}")
            exitProcess(1)
        }
    }

    private fun handOff(authority: String, token: String, service: IBinder): IBinder {
        val manager = Class.forName("android.app.ActivityManager").getMethod("getService").invoke(null)
        val api = Class.forName("android.app.IActivityManager")
        val holder = api.getMethod("getContentProviderExternal", String::class.java, Int::class.javaPrimitiveType,
            IBinder::class.java, String::class.java).invoke(manager, authority, 0, null, authority)
            ?: error("Provider $authority is not available")
        try {
            val provider = checkNotNull(holder.javaClass.getField("provider").get(holder)) { "Provider $authority has no binder" }
            val reply = call(provider, authority, token, Bundle().apply { putBinder(BINDER, service) })
            return checkNotNull(reply?.getBinder(CLIENT)) { "App did not accept the worker" }
        } finally {
            runCatching {
                api.getMethod("removeContentProviderExternalAsUser", String::class.java, IBinder::class.java,
                    Int::class.javaPrimitiveType).invoke(manager, authority, null, 0)
            }
        }
    }

    /** `IContentProvider.call` gained an AttributionSource in API 31; API 30 takes a package and feature id. */
    private fun call(provider: Any, authority: String, token: String, extras: Bundle): Bundle? {
        val methods = Class.forName("android.content.IContentProvider").methods.filter { it.name == "call" }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val method = methods.first { it.parameterTypes.size == 5 && it.parameterTypes[0] == AttributionSource::class.java }
            val source = AttributionSource.Builder(Process.myUid()).setPackageName(caller()).build()
            return method.invoke(provider, source, authority, ATTACH, token, extras) as Bundle?
        }
        val method = methods.first { it.parameterTypes.size == 6 }
        return method.invoke(provider, caller(), null, authority, ATTACH, token, extras) as Bundle?
    }

    private fun caller() = if (Process.myUid() == WorkerAccess.ROOT_UID) ROOT else SHELL
}
