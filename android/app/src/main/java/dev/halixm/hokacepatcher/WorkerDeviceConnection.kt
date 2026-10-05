package dev.halixm.hokacepatcher

import android.content.ComponentName
import android.content.Context
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import java.util.UUID
import rikka.shizuku.Shizuku

/** The foreground worker owns its binding independently of activity recreation. */
class WorkerDeviceConnection(context: Context, private val lost: () -> Unit) : AutoCloseable {
    private val service = AtomicReference<IPrivilegedDeviceService?>(null)
    private val connected = CountDownLatch(1)
    private val guard = Any()
    private var closed = false
    private var failure: String? = null
    private var binder: IBinder? = null
    private var recipient: IBinder.DeathRecipient? = null
    private val args = Shizuku.UserServiceArgs(ComponentName(context, PrivilegedDeviceService::class.java))
        .daemon(false).processNameSuffix("worker").tag("hokace-worker-${UUID.randomUUID()}")
        .version(PrivilegedDeviceService.PROTOCOL_VERSION)
    private val death = Shizuku.OnBinderDeadListener { disconnected("Shizuku server disconnected") }

    private fun disconnected(message: String, expected: IBinder? = null) {
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
            android.util.Log.e("HokAceWorker", "Could not persist service-loss recovery state", it)
        }
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, connectedBinder: IBinder) {
            var failed = false
            synchronized(guard) {
                if (closed || failure != null || binder != null) return
                binder = connectedBinder
                val deathRecipient = IBinder.DeathRecipient {
                    disconnected("Shizuku worker disconnected", connectedBinder)
                }
                recipient = deathRecipient
                try {
                    connectedBinder.linkToDeath(deathRecipient, 0)
                    service.set(IPrivilegedDeviceService.Stub.asInterface(connectedBinder))
                    connected.countDown()
                } catch (_: android.os.RemoteException) {
                    failed = true
                }
            }
            if (failed) disconnected("Shizuku worker disconnected", connectedBinder)
        }
        override fun onServiceDisconnected(name: ComponentName) { disconnected("Shizuku worker disconnected") }
    }

    init {
        check(Shizuku.pingBinder()) { "Start Shizuku before starting a patch or recovery" }
        check(Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
            "Authorize HOK ACE in Shizuku before starting"
        }
        Shizuku.addBinderDeadListener(death)
        try { Shizuku.bindUserService(args, connection) } catch (error: Throwable) {
            Shizuku.removeBinderDeadListener(death)
            throw error
        }
    }

    fun await(): IPrivilegedDeviceService {
        check(connected.await(20, TimeUnit.SECONDS)) { "Shizuku worker connection timed out" }
        return synchronized(guard) {
            check(!closed) { "Shizuku worker connection closed" }
            check(failure == null) { failure!! }
            checkNotNull(service.get()).also { check(it.asBinder().isBinderAlive) { "Shizuku worker disconnected" } }
        }
    }

    override fun close() {
        synchronized(guard) {
            if (closed) return
            closed = true
            binder?.let { target -> recipient?.let { runCatching { target.unlinkToDeath(it, 0) } } }
            binder = null
            recipient = null
            service.set(null)
            connected.countDown()
        }
        Shizuku.removeBinderDeadListener(death)
        runCatching { Shizuku.unbindUserService(args, connection, true) }
    }
}
