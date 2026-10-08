package dev.halixm.hokacepatcher

import android.content.Context
import android.os.Process
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Timestamped app-private trace for the diagnostic export: what the screen showed, what the worker did,
 * how the Shizuku connection went and every stack trace. It is evidence only; nothing reads it back to
 * decide recovery, and a failed write never fails the operation it describes.
 */
object DiagnosticTrace {
    const val FILE = "trace.log"
    const val PREVIOUS = "trace.log.1"
    private const val MAX_BYTES = 1024L * 1024
    private val lock = Any()
    @Volatile private var root: File? = null
    @Volatile private var handlerInstalled = false

    /** Remember the app-private directory and record crashes; safe to call from every entry point. */
    fun init(context: Context) {
        root = context.applicationContext.filesDir
        synchronized(lock) {
            if (handlerInstalled) return
            handlerInstalled = true
            val previous = Thread.getDefaultUncaughtExceptionHandler()
            Thread.setDefaultUncaughtExceptionHandler { thread, failure ->
                error("crash", "Uncaught exception on thread ${thread.name}", failure)
                previous?.uncaughtException(thread, failure)
            }
        }
    }

    fun event(tag: String, message: String) = write(tag, message, null)

    fun error(tag: String, message: String, error: Throwable) = write(tag, message, error)

    /** Run [block], tracing its duration and any failure before rethrowing it unchanged. */
    fun <T> timed(tag: String, name: String, block: () -> T): T {
        val started = android.os.SystemClock.elapsedRealtime()
        event(tag, "$name started")
        try {
            return block().also { event(tag, "$name finished in ${android.os.SystemClock.elapsedRealtime() - started} ms") }
        } catch (failure: Throwable) {
            error(tag, "$name failed after ${android.os.SystemClock.elapsedRealtime() - started} ms", failure)
            throw failure
        }
    }

    private fun write(tag: String, message: String, failure: Throwable?) {
        if (failure == null) Log.i("HokAce/$tag", message) else Log.e("HokAce/$tag", message, failure)
        val directory = root ?: return
        val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS Z", Locale.US).format(Date())
        val line = buildString {
            append(time).append(" p").append(Process.myPid()).append(" t").append(Process.myTid())
                .append(' ').append(tag).append(": ").append(message).append('\n')
            if (failure != null) append(Log.getStackTraceString(failure)).append('\n')
        }
        runCatching {
            synchronized(lock) {
                val file = File(directory, FILE)
                if (file.length() > MAX_BYTES) file.renameTo(File(directory, PREVIOUS))
                FileOutputStream(file, true).use { it.write(line.toByteArray(Charsets.UTF_8)) }
            }
        }
    }
}
