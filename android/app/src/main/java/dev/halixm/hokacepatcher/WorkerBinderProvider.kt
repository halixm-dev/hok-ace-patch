package dev.halixm.hokacepatcher

import android.content.ContentProvider
import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.net.Uri
import android.os.Binder
import android.os.Bundle
import android.os.IBinder
import java.util.concurrent.ConcurrentHashMap

/**
 * Receives the worker binder from [ShellServiceStarter]. The manifest guards it with a permission only
 * the shell holds, and each call must also come from uid 2000 and present a token that a live
 * [WorkerDeviceConnection] is waiting on. A token is single use. Nothing here reads or writes data.
 */
class WorkerBinderProvider : ContentProvider() {
    companion object {
        private const val SHELL_UID = 2000
        private val pending = ConcurrentHashMap<String, (IBinder) -> IBinder?>()

        fun authority(context: Context) = "${context.packageName}.worker"

        /** [receive] returns the binder the shell process should watch, or null to refuse it. */
        fun expect(token: String, receive: (IBinder) -> IBinder?) { pending[token] = receive }

        fun forget(token: String) { pending.remove(token) }
    }

    override fun onCreate() = true

    override fun call(method: String, arg: String?, extras: Bundle?): Bundle? {
        val caller = Binder.getCallingUid()
        if (caller != SHELL_UID) throw SecurityException("Worker attach refused for uid $caller")
        require(method == ShellServiceStarter.ATTACH) { "Unsupported worker call" }
        val receive = arg?.let { pending.remove(it) } ?: throw SecurityException("Unknown or used worker token")
        val binder = requireNotNull(extras?.getBinder(ShellServiceStarter.BINDER)) { "No worker binder" }
        val client = checkNotNull(receive(binder)) { "Worker connection already finished" }
        return Bundle().apply { putBinder(ShellServiceStarter.CLIENT, client) }
    }

    override fun query(uri: Uri, projection: Array<out String>?, selection: String?,
                       selectionArgs: Array<out String>?, sortOrder: String?): Cursor? = null
    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?) = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?) = 0
}
