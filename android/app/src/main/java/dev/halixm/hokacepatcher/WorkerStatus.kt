package dev.halixm.hokacepatcher

import org.json.JSONObject

/** Describe durable worker results without treating an old running record as a live process. */
object WorkerStatus {
    const val UNCONFIRMED = "Recovery finished. Normal game app verified. The translation was written and checked, " +
        "but the game changed its files afterwards, so they were not checked again. If some text is Chinese, tap Start to patch again."

    /** Exact sentences, so [UiText] can translate them; the GB figures follow on their own lines. */
    fun freed(bytes: Long, free: Long, removedApks: Boolean = false) = (if (removedApks)
        "Space freed. The record for switching languages was kept. The saved game apps were removed; the next patch prepares them again."
        else "Space freed. The record for switching languages and the saved game app were kept.") +
        "\nFreed: ${StorageBudget.freeSpaceLabel(bytes)}\nFree now: ${StorageBudget.freeSpaceLabel(free)}"

    /**
     * <result>, a resolved session's terminal result, as the player should read it given the session record <journal>.
     * A Stop that took effect only after the payload was verified and the pristine delta finalized left the action
     * done on the game, so it reports that outcome and its counts (or, with the layer unconfirmed, that state), never
     * a plain stop. The run itself stays resolved as stopped. Any other result is returned unchanged.
     */
    fun afterStop(result: JSONObject, journal: JSONObject): JSONObject {
        if (result.optString("status") != "stopped_consistent" || !journal.optBoolean("patch_payload_verified") ||
            !journal.optBoolean("finalized")) return result
        if (journal.optString("layer_unconfirmed").isNotEmpty()) return result.put("status", "recovered_unconfirmed")
        result.put("status", "complete").put("stopped_after_finish", true).put("counts", journal.opt("counts") ?: JSONObject.NULL)
        if (journal.has("removed_count")) result.put("removed", journal.getInt("removed_count"))
        return result
    }

    fun describe(value: JSONObject): String = when (value.optString("status")) {
        "running" -> (if (value.optBoolean("stopping")) "Stopping safely. The current step finishes or is restored first.\n" else "") +
            "Last saved progress: ${value.optString("progress", "Starting") }"
        "prepared" -> "Game files prepared. Translation has not started." +
            if (value.optBoolean("requires_signature_conversion"))
                "\nFirst setup needs separate consent to delete local game data and use Scan to login."
            else ""
        "verified" -> "Normal game app verified. Unfinished game-data changes still require recovery."
        "recovered" -> "Original game files and normal game app restored."
        "recovered_unconfirmed" -> UNCONFIRMED
        "space_freed" -> freed(value.optLong("freed_bytes"), value.optLong("free_bytes"), value.optBoolean("removed_saved_apks"))
        "setup_waiting" -> "Game app installed. Translation has not started. Open the game, finish every download, then close it." +
            if (value.optBoolean("automatic_recovery")) "\nThe normal app was restored after a setup error." else ""
        "setup_ready" -> "Game setup finished. Translation has not started. Prepare game files again, then confirm the update checkpoint to patch."
        "setup_cancelled" -> "Setup stopped. The original game app was verified. Translation has not started." +
            (if (value.optBoolean("data_loss_may_have_happened")) " Local data may need downloading again." else "") +
            // The uninstall is never repeated automatically; a new attempt needs its own data-loss approval.
            (if (value.optBoolean("fresh_consent_required")) "\nSetting up again needs your approval to delete local game data." else "")
        // The saved action waits for the user (ticket 12): the game files and app are consistent meanwhile.
        "waiting" -> if (value.optString("reason") == "storage")
            StorageBudget.explainFailure(value.optString("error")) ?: value.optString("error")
            else if (value.optString("reason") == PatchCoordinator.REDOWNLOAD_DOWNLOAD)
            "Damaged files deleted. The translation waits until the game downloads them again."
            // The game changed its files mid-run: nothing is damaged, the action waits for its downloads (③'s own card).
            else if (value.optString("reason") == PatchCoordinator.SOURCE_DOWNLOADS) UiText.english("setup_update")
            // Only the loop guard's fallback waits here: Re-download is otherwise approved automatically (2026-11-13).
            else "Damaged game files need your review before they are deleted again. Nothing was deleted."
        "stopped_consistent" -> "Stopped safely. The game files and app are consistent. Start when you want to patch again."
        "complete" -> completed(value)
        "recovery_required" -> "Recovery required. Keep the game closed.\n" +
            InstallerFailure.explain(value.optString("error"), value.optString("action"), true)
        "cancelled" -> "Preparation cancelled. No game files changed."
        "error" -> "Stopped: " + InstallerFailure.explain(value.optString("error", "Unknown error"),
            value.optString("action"), false)
        else -> "No saved worker result."
    }

    /** A root run never replaced the game app, so it does not name the normal app (ADR 0007). */
    private fun completed(value: JSONObject): String {
        val app = if (value.optBoolean("root")) "The game app was not replaced" else "Normal game app verified"
        return if (value.has("redownloaded")) {
            "Damaged files deleted. $app.\n" +
                "Package files deleted: ${value.getInt("redownloaded")}\n" +
                "Open the game, let it finish the update to the login screen, close it, then tap Start to patch again."
        } else if (value.has("removed")) {
            "Translation removed. $app.\n" +
                "Original game files restored: ${value.getInt("removed")}\n" +
                "Keep using Scan to login. For the official app, reinstall the game from the store."
        } else value.optJSONObject("counts")?.let { counts ->
            "Patch complete. $app.\n" +
                "Text tables applied: ${counts.getInt("text_tables")}\n" +
                "Images applied: ${counts.getInt("applied_textures")}\n" +
                "Text tables skipped: ${counts.getInt("skipped_tables")}\n" +
                "Images skipped: ${counts.getInt("skipped_textures")}"
        } ?: "Patch complete. $app; counts unavailable."
    }
}
