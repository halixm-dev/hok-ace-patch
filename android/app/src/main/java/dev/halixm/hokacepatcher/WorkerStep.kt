package dev.halixm.hokacepatcher

import org.json.JSONObject

/**
 * The six steps a patch or a removal reports, as stable keys the worker record carries beside its free-text
 * line. `prepare` runs steps 1 and 2 before the confirmation; `patch` and `remove` run 3 to 6 after it.
 * Recovery, first setup and Free up space report no step.
 */
object WorkerStep {
    val KEYS = listOf("check_game", "prepare_files", "unlock_access", "build", "write", "restore_game_app")

    /** The progress line that starts each step, by prefix; any other line keeps the current step. */
    private val STARTS = listOf(
        "Checking other Android profiles for the game" to "check_game",
        "Checking saved normal and access APKs" to "check_game",
        "Copying and verifying the installed source APK" to "prepare_files",
        "Preparing normal and access APKs" to "prepare_files",
        "Reusing verified saved APKs" to "prepare_files",
        "Opening game data access" to "unlock_access",
        "Measuring downloaded game data" to "unlock_access",
        "Saving complete game data" to "unlock_access",
        "Building text and graphics" to "build",
        "Rebuilding the original game files" to "build",
        "Applying package file" to "write",
        "Restoring normal game APK" to "restore_game_app",
    )

    /** The first and last step of <action>, or null for an action that reports none. */
    private fun range(action: String): IntRange? = when (action) {
        "prepare" -> 0..1
        "patch", "remove" -> 2..5
        else -> null
    }

    /**
     * The step after <action> reports <message> at <current>, or null for an action without steps. A step
     * never goes back and never skips one: a run that fails at step 3 restores the game app while recovering,
     * which is not step 6.
     */
    fun next(action: String, current: String?, message: String): String? {
        val range = range(action) ?: return null
        val at = KEYS.indexOf(current).takeIf { it in range } ?: range.first
        val started = KEYS.indexOf(STARTS.firstOrNull { message.startsWith(it.first) }?.second)
        return KEYS[if (started == at + 1 && started in range) started else at]
    }

    /** The 1-based step a running <state> reports, or null when it carries none for its action. */
    fun number(state: JSONObject): Int? {
        val range = range(state.optString("action")) ?: return null
        val index = KEYS.indexOf(state.optString("step"))
        return if (state.optString("status") == "running" && index in range) index + 1 else null
    }
}
