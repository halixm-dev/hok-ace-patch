package dev.halixm.hokacepatcher

/**
 * What ③ offers after a run stopped, from the worker's saved status and error alone.
 *
 * The retained normal APK makes [RecoveryMaterial.any] true for good, so recovery material alone must never
 * take Start away: a refusal before the worker started, or a stop the worker recovered from itself, offers a
 * retry, with the recovery options still below (lab notebook, 2026-10-29).
 */
object StopCard {
    /**
     * The engine's refusals that open Re-download and the update wait, and the start of its clear-data advice.
     * Each is the start of the same constant in `android_bridge.py`; `tools/research/check_ui_strings.py`
     * checks they match.
     */
    const val UPDATE_STUCK = "The game's update stopped on translated files"
    const val UPDATE_MIXED = "A game update kept part of this patcher's translation"
    const val UPDATE_WAITING = "The game has not downloaded the re-downloaded files yet"
    const val DOWNLOAD_UNFINISHED = "The game was still downloading game files"
    const val CLEAR_DATA = "Clear the game's data (Android Settings"

    enum class Exit {
        /** An update stuck on translated files. */
        REDOWNLOAD_STUCK,
        /** Packages an update rewrote around the translation. */
        REDOWNLOAD_MIXED,
        /** After Re-download, or a package the game was still downloading. */
        WAIT_FOR_GAME,
        /** A shell provider's refusal, before the worker started: the refusal's own line says tap Start. */
        START,
        /** A stop that left nothing unfinished. */
        TRY_AGAIN,
        /** Unfinished work, or records that could not be read. */
        RECOVERY,
    }

    /**
     * ③'s way out for <status> and <error>, or null when the status is no stop. <pending> is whether a patch
     * session, first setup or emergency restore is unfinished (null: unreadable); <recoverable> whether
     * recovery material exists.
     */
    fun decide(status: String?, error: String, pending: Boolean?, recoverable: Boolean): Exit? {
        if (status !in setOf("error", "recovery_required")) return null
        if (status == "error") when {
            error.contains(UPDATE_STUCK) -> return Exit.REDOWNLOAD_STUCK
            error.contains(UPDATE_MIXED) -> return Exit.REDOWNLOAD_MIXED
            error.contains(UPDATE_WAITING) || error.contains(DOWNLOAD_UNFINISHED) -> return Exit.WAIT_FOR_GAME
            providerRefusal(error) -> return Exit.START
            pending == false -> return Exit.TRY_AGAIN
        }
        return if (recoverable) Exit.RECOVERY else Exit.TRY_AGAIN
    }

    /** Whether the stop's own line points at the recovery options rather than at a retry. */
    fun pointsAtRecovery(exit: Exit, recoverable: Boolean) = recoverable && exit != Exit.TRY_AGAIN

    /** Whether ③'s line stands in for the stop's own explanation, so the result message stays empty. */
    fun ownCard(exit: Exit) = exit in setOf(Exit.REDOWNLOAD_STUCK, Exit.REDOWNLOAD_MIXED, Exit.WAIT_FOR_GAME)

    /** True when <message> is a shell provider's refusal to start the worker, which comes before any game file is touched. */
    fun providerRefusal(message: String) =
        (WirelessDebugging.REFUSALS + RootWorkerStarter.REFUSALS).any { message.contains(it) }
}
