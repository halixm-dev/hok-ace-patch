package dev.halixm.hokacepatcher

/** Turn preserved installer codes into next steps; retain the original error in journals/logs. */
object InstallerFailure {
    fun explain(error: String, action: String, recoveryRequired: Boolean): String {
        StorageBudget.explainFailure(error)?.let { return it }
        val recoveryAction = if (action in setOf("first_setup", "setup_recover", "setup_update"))
            "Recover or finish game setup" else "Recover interrupted patch"
        val retry = if (!recoveryRequired) "Retry the action after fixing it." else "Then choose $recoveryAction."
        val code = Regex("INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+").findAll(error).lastOrNull()?.value
        return when (code) {
            "INSTALL_FAILED_USER_RESTRICTED" ->
                "The phone blocked installation. Unlock it and accept the install prompt. " +
                    "If available, enable Install via USB. On MIUI, also check USB debugging (Security settings). $retry"
            "INSTALL_FAILED_INSUFFICIENT_STORAGE" ->
                "The phone needs more free storage. Keep the patcher's recovery files; free space elsewhere. $retry"
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE" ->
                "The installed app has a different signing identity. Keep the recovery files and export diagnostic logs. " +
                    "Do not uninstall the game to retry this action."
            "INSTALL_FAILED_ALREADY_EXISTS" ->
                "An app is already installed where first setup expected it to be absent. " +
                    "Use $recoveryAction to check it; do not repeat removal."
            else -> error
        }
    }
}
