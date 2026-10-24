package dev.halixm.hokacepatcher

import android.os.Build
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * The Root provider's [WorkerStarter]: `su -c` runs [WorkerLink.ownCommand], so the worker runs as uid 0 and
 * writes the game's files itself (ADR 0007). Any `su` whose `su -c id` reports uid 0 is accepted; the root
 * manager's own allow list or prompt decides, and the patcher never asks it for more.
 *
 * The app cannot signal a uid-0 process, so the worker ends when `su`'s standard input closes
 * ([ShellServiceStarter] watches it at uid 0): [close] closes it, and so does the app's death.
 */
class RootWorkerStarter : WorkerStarter {
    companion object {
        const val NO_ROOT = "Root access is not available to HOK ACE. Allow HOK ACE in your root manager, " +
            "such as KernelSU, Magisk or APatch, then tap Start again."
        const val NOT_ROOT = "Root access did not give HOK ACE root. Check HOK ACE in your root manager, then tap Start again."
        /** The starter's refusals, each already the line the player reads. */
        val REFUSALS = listOf(NO_ROOT, NOT_ROOT)
        /** A root manager may hold `su` on its own prompt this long. */
        private const val CHECK_SECONDS = 60L
        private const val SU = "su"
    }
    private var process: Process? = null
    private var version = "unknown"

    override fun start(link: WorkerLink) {
        version = check()
        val command = WirelessDebugging.shellLine(link.ownCommand())
        val started = try { ProcessBuilder(SU, "-c", command).redirectErrorStream(true).start() }
            catch (error: IOException) { link.forgetOwnCommand(); throw error }
        process = started
        DiagnosticTrace.event("root", "Started the app's own worker starter through su after ${link.elapsed()} ms")
        link.watch(started.inputStream) { started.waitFor() }
    }

    /** Refuse unless `su -c id` reports uid 0; returns the manager's own `su -v` line for the trace. */
    private fun check(): String {
        val id = try { run(SU, "-c", "id") } catch (error: IOException) {
            DiagnosticTrace.error("root", "No su for this app", error)
            error(NO_ROOT)
        }
        DiagnosticTrace.event("root", "su -c id: ${id.second.take(200)} (exit ${id.first})")
        check(id.first == 0) { NO_ROOT }
        check(Regex("""(^|\s)uid=0\(""").containsMatchIn(id.second)) { NOT_ROOT }
        return runCatching { run(SU, "-v").second.trim().take(80) }.getOrDefault("unknown")
    }

    private fun run(vararg args: String): Pair<Int, String> {
        val started = ProcessBuilder(*args).redirectErrorStream(true).start()
        try {
            started.outputStream.close()
            // Wait first: a prompting manager writes nothing until it answers. The output fits the pipe.
            check(started.waitFor(CHECK_SECONDS, TimeUnit.SECONDS)) { NO_ROOT }
            return started.exitValue() to started.inputStream.bufferedReader().readText()
        } finally { started.destroy() }
    }

    override fun environment(): String =
        "Root su $version, ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} API ${Build.VERSION.SDK_INT}"

    override fun close() {
        process?.let { runCatching { it.outputStream.close() }; runCatching { it.destroy() } }
        process = null
    }
}
