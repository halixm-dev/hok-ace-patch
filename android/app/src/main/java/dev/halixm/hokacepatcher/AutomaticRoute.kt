package dev.halixm.hokacepatcher

import org.json.JSONObject

/** Deterministic recovery-first routing; ambiguous or damaged state never guesses a target. */
object AutomaticRoute {
    enum class Step { VERIFY, RECOVER_PATCH, RECOVER_SETUP, WAIT_FOR_DOWNLOADS, PREPARE, MANUAL }
    data class Setup(val id: String, val waitingForDownloads: Boolean)
    data class Decision(val step: Step, val id: String? = null)

    fun choose(emergency: String?, patches: List<String>, setups: List<Setup>): Decision = when {
        emergency != null -> Decision(Step.VERIFY, emergency)
        patches.size > 1 -> Decision(Step.MANUAL)
        patches.size == 1 -> Decision(Step.RECOVER_PATCH, patches.single())
        setups.size > 1 -> Decision(Step.MANUAL)
        setups.size == 1 -> Decision(if (setups.single().waitingForDownloads) Step.WAIT_FOR_DOWNLOADS
            else Step.RECOVER_SETUP, setups.single().id)
        else -> Decision(Step.PREPARE)
    }

    /** A previous result, or a still-live service, cannot trigger the next automatic operation. */
    fun finished(value: JSONObject?, token: String?, workerAlive: Boolean): Boolean =
        token != null && value != null && !workerAlive && value.optString("flow") == token &&
            value.optString("status") in setOf("prepared", "verified", "recovered", "setup_ready",
                "setup_waiting", "setup_cancelled", "complete", "cancelled", "error", "recovery_required")
}
