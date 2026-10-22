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

    fun describe(value: JSONObject): String = when (value.optString("status")) {
        "running" -> "Last saved progress: ${value.optString("progress", "Starting") }"
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
            if (value.optBoolean("data_loss_may_have_happened")) " Local data may need downloading again." else ""
        "complete" -> if (value.has("redownloaded")) {
            "Damaged files deleted. Normal game app verified.\n" +
                "Package files deleted: ${value.getInt("redownloaded")}\n" +
                "Open the game, let it finish the update to the login screen, close it, then tap Start to patch again."
        } else if (value.has("removed")) {
            "Translation removed. Normal game app verified.\n" +
                "Original game files restored: ${value.getInt("removed")}\n" +
                "Keep using Scan to login. For the official app, reinstall the game from the store."
        } else value.optJSONObject("counts")?.let { counts ->
            "Patch complete. Normal game app verified.\n" +
                "Text tables applied: ${counts.getInt("text_tables")}\n" +
                "Images applied: ${counts.getInt("applied_textures")}\n" +
                "Text tables skipped: ${counts.getInt("skipped_tables")}\n" +
                "Images skipped: ${counts.getInt("skipped_textures")}"
        } ?: "Patch complete. Normal game app verified; counts unavailable."
        "recovery_required" -> "Recovery required. Keep the game closed.\n" +
            InstallerFailure.explain(value.optString("error"), value.optString("action"), true)
        "cancelled" -> "Preparation cancelled. No game files changed."
        "error" -> "Stopped: " + InstallerFailure.explain(value.optString("error", "Unknown error"),
            value.optString("action"), false)
        else -> "No saved worker result."
    }
}
