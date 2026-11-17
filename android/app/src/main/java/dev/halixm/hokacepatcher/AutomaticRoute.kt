package dev.halixm.hokacepatcher

import org.json.JSONObject

/** Deterministic recovery-first routing; ambiguous or damaged state never guesses a target. */
object AutomaticRoute {
    enum class Step { VERIFY, RECOVER_PATCH, RECOVER_SETUP, WAIT_FOR_DOWNLOADS, PREPARE, CONTINUE_RUN, RESOLVE_STOPPED, MANUAL }
    data class Setup(val id: String, val waitingForDownloads: Boolean)
    /** A non-terminal durable Start (`RunStore.pending`): its lifecycle, Stop state and linked session. */
    data class Run(val id: String, val lifecycle: String, val mayContinue: Boolean, val sessionId: String)
    data class Decision(val step: Step, val id: String? = null)

    /**
     * Safety first: emergency verification, then one unfinished patch session, then setup. A patch session
     * linked to the one pending Start that may continue goes to that Start's dispatch, which restores
     * consistency before it continues; any other session gets safety recovery only. Then the Start itself:
     * one not yet confirmed prepares (and asks again), one confirmed continues, one Stopped is resolved
     * without device work. More than one candidate never guesses.
     */
    @JvmOverloads
    fun choose(emergency: String?, patches: List<String>, setups: List<Setup>, runs: List<Run> = emptyList()): Decision {
        val single = runs.singleOrNull()
        return when {
            emergency != null -> Decision(Step.VERIFY, emergency)
            patches.size > 1 -> Decision(Step.MANUAL)
            patches.size == 1 -> if (runs.size <= 1 && single != null && single.sessionId == patches.single() &&
                single.mayContinue && single.lifecycle == "claimed") Decision(Step.CONTINUE_RUN, single.id)
                else Decision(Step.RECOVER_PATCH, patches.single())
            setups.size > 1 -> Decision(Step.MANUAL)
            setups.size == 1 -> Decision(if (setups.single().waitingForDownloads) Step.WAIT_FOR_DOWNLOADS
                else Step.RECOVER_SETUP, setups.single().id)
            runs.size > 1 -> Decision(Step.MANUAL)
            single == null -> Decision(Step.PREPARE)
            !single.mayContinue -> Decision(Step.RESOLVE_STOPPED, single.id)
            single.lifecycle == "authorized" -> Decision(Step.PREPARE, single.id)
            single.lifecycle in setOf("prepared", "claimed") -> Decision(Step.CONTINUE_RUN, single.id)
            else -> Decision(Step.MANUAL)
        }
    }

    /**
     * After Stop safely only safety work and closing the stopped record may start: verification, patch or setup
     * recovery (install only, never another uninstall) and resolving the Stop. A new preparation, the saved
     * action's continuation or the downloads question would be new work the player just declined.
     */
    fun allowedWhileStopping(step: Step): Boolean =
        step in setOf(Step.VERIFY, Step.RECOVER_PATCH, Step.RECOVER_SETUP, Step.RESOLVE_STOPPED)

    /** What a fresh launch does by itself (spec Q1: resume on reopen, never at boot). */
    enum class Launch { NONE, CONTINUE, STOP }

    /** A saved Start as a fresh launch sees it; <setupReady> is its first setup finished with the downloads answer. */
    data class Saved(val id: String, val action: String, val lifecycle: String, val mayContinue: Boolean,
                     val stopRequested: Boolean, val retryExhausted: Boolean, val setupReady: Boolean)

    /**
     * A saved Stop finishes its safety recovery and closes, and stays stopped. An approved setup with an uninstall
     * or install intent is recovered (install only). A setup waiting for downloads asks only while its Start may
     * continue. A Start that may continue resumes once confirmed (or once its setup is ready), unless its one
     * automatic retry is spent: then it waits for an explicit Retry. Ambiguity starts nothing.
     */
    fun onLaunch(run: Saved?, runs: Int, setups: List<Setup>): Launch = when {
        runs > 1 || setups.size > 1 -> Launch.NONE
        run != null && run.stopRequested && run.lifecycle !in setOf("complete", "stopped") -> Launch.STOP
        setups.size == 1 && !setups.single().waitingForDownloads -> Launch.CONTINUE
        run == null || !run.mayContinue || run.retryExhausted -> Launch.NONE
        setups.size == 1 -> Launch.CONTINUE
        run.lifecycle in setOf("prepared", "claimed") && run.action in setOf("translate", "remove") -> Launch.CONTINUE
        run.lifecycle == "authorized" && run.setupReady -> Launch.CONTINUE
        else -> Launch.NONE
    }

    /** A previous result, or a still-live service, cannot trigger the next automatic operation. */
    fun finished(value: JSONObject?, token: String?, workerAlive: Boolean): Boolean =
        token != null && value != null && !workerAlive && value.optString("flow") == token &&
            value.optString("status") in setOf("prepared", "verified", "recovered", "recovered_unconfirmed", "setup_ready",
                "setup_waiting", "setup_cancelled", "complete", "cancelled", "error", "recovery_required", "waiting",
                "stopped_consistent")
}
