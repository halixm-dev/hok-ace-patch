package dev.halixm.hokacepatcher

import android.content.Context
import android.os.Binder
import android.os.IBinder
import java.io.InputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import java.util.UUID

/**
 * The foreground worker owns its binding independently of activity recreation.
 *
 * A [WorkerStarter], one per [ShellProvider], starts the worker; this connection takes the first binder
 * it delivers, watches it for death, and reports a loss once through <lost>. Any starter that can run
 * one shell command can use [WorkerLink.ownCommand], which starts [ShellServiceStarter] with this APK as
 * its class path and a one-time token for [WorkerBinderProvider].
 */
class WorkerDeviceConnection(context: Context, private val starter: WorkerStarter,
                             private val lost: () -> Unit) : AutoCloseable, WorkerLink {
    companion object {
        // A cold app_process start of this APK on a slow phone; a delivered binder returns at once.
        const val CONNECT_SECONDS = 45L
        private const val OUTPUT_LINES = 200

        /** The connection for <provider>; a provider this build cannot start is refused here. */
        fun open(context: Context, provider: ShellProvider, lost: () -> Unit): WorkerDeviceConnection {
            DiagnosticTrace.event("connection", "Shell provider ${provider.key}")
            check(provider.available) { "${provider.label} is not available in this build" }
            val starter = when (provider) {
                ShellProvider.SHIZUKU -> ShizukuWorkerStarter(context)
                ShellProvider.WIRELESS -> WirelessWorkerStarter(context)
                ShellProvider.ROOT -> RootWorkerStarter()
            }
            return WorkerDeviceConnection(context, starter, lost)
        }
    }
    private val appContext = context.applicationContext
    private val bindStarted = android.os.SystemClock.elapsedRealtime()
    private val service = AtomicReference<IPrivilegedDeviceService?>(null)
    private val connected = CountDownLatch(1)
    private val guard = Any()
    private var closed = false
    private var failure: String? = null
    private var binder: IBinder? = null
    private var recipient: IBinder.DeathRecipient? = null
    private var via: String? = null
    // Held for the connection's lifetime: the shell starter exits when this binder dies.
    private val client = Binder()
    override val tag = "hokace-worker-${UUID.randomUUID()}"
    private val token = UUID.randomUUID().toString()

    override fun elapsed() = android.os.SystemClock.elapsedRealtime() - bindStarted

    override fun disconnected(message: String, expected: IBinder?) {
        DiagnosticTrace.event("connection", "$message after ${elapsed()} ms ($tag)")
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
            DiagnosticTrace.error("connection", "Could not persist service-loss recovery state", it)
        }
    }

    /** Accept the first worker binder from any path; a later one is refused. */
    override fun attach(connectedBinder: IBinder, path: String): Boolean {
        DiagnosticTrace.event("connection", "Worker binder from $path after ${elapsed()} ms, " +
            "binder alive ${connectedBinder.isBinderAlive}")
        var failed = false
        synchronized(guard) {
            if (closed || failure != null || binder != null) {
                DiagnosticTrace.event("connection", "Ignoring worker binder from $path; connection already settled by $via")
                return false
            }
            binder = connectedBinder
            via = path
            val deathRecipient = IBinder.DeathRecipient {
                disconnected("Worker disconnected ($path)", connectedBinder)
            }
            recipient = deathRecipient
            try {
                connectedBinder.linkToDeath(deathRecipient, 0)
                service.set(IPrivilegedDeviceService.Stub.asInterface(connectedBinder))
                connected.countDown()
            } catch (error: android.os.RemoteException) {
                DiagnosticTrace.error("connection", "Cannot watch the worker binder", error)
                failed = true
            }
        }
        if (failed) disconnected("Worker disconnected ($path)", connectedBinder)
        return !failed
    }

    init {
        DiagnosticTrace.event("connection", "Connecting worker $tag: ${environment()}")
        try { starter.start(this) } catch (error: Throwable) {
            DiagnosticTrace.error("connection", "Worker start refused", error)
            WorkerBinderProvider.forget(token)
            runCatching { starter.close() }
            throw error
        }
    }

    fun await(): IPrivilegedDeviceService {
        val patience = starter.patienceSeconds
        if (patience > 0 && !connected.await(patience, TimeUnit.SECONDS)) {
            DiagnosticTrace.event("connection", "No binder after ${elapsed()} ms; telling the starter")
            runCatching { starter.stalled(this) }.onFailure {
                DiagnosticTrace.error("connection", "The starter's second attempt could not be launched", it)
            }
        }
        val remaining = CONNECT_SECONDS * 1000 - elapsed()
        if (!connected.await(maxOf(remaining, 0), TimeUnit.MILLISECONDS)) {
            DiagnosticTrace.event("connection", "No worker binder after ${elapsed()} ms")
            error("Worker connection timed out (${environment()})")
        }
        return synchronized(guard) {
            check(!closed) { "Worker connection closed" }
            check(failure == null) { failure!! }
            checkNotNull(service.get()).also { check(it.asBinder().isBinderAlive) { "Worker disconnected" } }
        }.also { starter.connected(checkNotNull(synchronized(guard) { via })) }
    }

    /** `sh -c` starting [ShellServiceStarter] under app_process, with this APK as its class path. */
    override fun ownCommand(): Array<String> {
        WorkerBinderProvider.expect(token) { delivered -> if (attach(delivered, OWN_STARTER)) client else null }
        val apk = appContext.applicationInfo.sourceDir
        return arrayOf("/system/bin/sh", "-c",
            "CLASSPATH=\"\$1\" exec /system/bin/app_process /system/bin --nice-name=\"\$2\" " +
                "${ShellServiceStarter::class.java.name} \"\$3\" \"\$4\" 2>&1",
            "hokace-worker", apk, "${appContext.packageName}:worker", token, WorkerBinderProvider.authority(appContext))
    }

    override fun forgetOwnCommand() = WorkerBinderProvider.forget(token)

    /** Trace the starter's output; if it exits before handing over a binder, fail now instead of timing out. */
    override fun watch(output: InputStream, exit: () -> Int?) {
        Thread({
            runCatching {
                output.bufferedReader().useLines { lines ->
                    lines.take(OUTPUT_LINES).forEach { DiagnosticTrace.event("starter", it) }
                }
            }
            val code = runCatching { exit() }.getOrNull()
            DiagnosticTrace.event("starter", "Own worker starter exited with code $code after ${elapsed()} ms")
            val pending = synchronized(guard) { binder == null && !closed }
            if (pending) disconnected("The app's own worker starter exited with code $code before connecting")
        }, "hokace-worker-starter").apply { isDaemon = true }.start()
    }

    override val isClosed: Boolean get() = synchronized(guard) { closed }

    private fun environment() = runCatching { starter.environment() }.getOrElse { "environment unknown (${it.message})" } +
        ", ${CONNECT_SECONDS}s"

    override fun close() {
        synchronized(guard) {
            if (closed) return
            closed = true
            DiagnosticTrace.event("connection", "Closing worker $tag via $via after ${elapsed()} ms")
            binder?.let { target -> recipient?.let { runCatching { target.unlinkToDeath(it, 0) } } }
            binder = null
            recipient = null
            service.set(null)
            connected.countDown()
        }
        WorkerBinderProvider.forget(token)
        runCatching { starter.close() }
    }
}

/** The path name [WorkerLink.ownCommand]'s binder arrives under. */
const val OWN_STARTER = "app's own starter"

/** What a [WorkerStarter] may ask of its connection. */
interface WorkerLink {
    /** Unique per connection; a starter may name its own processes or services after it. */
    val tag: String
    val isClosed: Boolean
    fun elapsed(): Long
    /** Offer a worker binder that arrived through <path>; false when the connection refused it. */
    fun attach(connectedBinder: IBinder, path: String): Boolean
    /** The worker or its starter is gone; <expected> limits the loss to that one binder. */
    fun disconnected(message: String, expected: IBinder? = null)
    /** The command that starts [ShellServiceStarter] as whoever runs it, armed for one binder. */
    fun ownCommand(): Array<String>
    /** Disarm [ownCommand] when it could not be launched. */
    fun forgetOwnCommand()
    /** Trace a launched [ownCommand]'s <output>; <exit> waits for its exit code. */
    fun watch(output: InputStream, exit: () -> Int?)
}

/** Starts the worker for one [WorkerDeviceConnection]; one implementation per [ShellProvider]. */
interface WorkerStarter {
    /** Begin starting the worker, or throw why it cannot; binders arrive through <link>. */
    fun start(link: WorkerLink)
    /** Seconds [WorkerDeviceConnection.await] waits before calling [stalled]; 0 never calls it. */
    val patienceSeconds: Long get() = 0
    /** No binder arrived within [patienceSeconds]: a second way to start, if the starter has one. */
    fun stalled(link: WorkerLink) {}
    /** The worker's binder arrived through <path>. */
    fun connected(path: String) {}
    /** One line for traces and the timeout message: provider, versions, phone. */
    fun environment(): String
    /** Release whatever [start] took; called once, after a refusal too. */
    fun close()
}
