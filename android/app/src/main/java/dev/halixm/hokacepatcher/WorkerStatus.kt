package dev.halixm.hokacepatcher

import org.json.JSONObject

/** Describe durable worker results without treating an old running record as a live process. */
object WorkerStatus {
    fun describe(value: JSONObject): String = when (value.optString("status")) {
        "running" -> "Last saved progress: ${value.optString("progress", "Starting") }"
        "prepared" -> "Game files prepared. Translation has not started." +
            if (value.optBoolean("requires_signature_conversion"))
                "\nFirst setup needs separate consent to delete local game data and use Scan to login."
            else ""
        "verified" -> "Normal game app verified. Unfinished game-data changes still require recovery."
        "recovered" -> "Original game files and normal game app restored."
        "setup_waiting" -> "Game app installed. Translation has not started. Open the game, finish every download, then close it." +
            if (value.optBoolean("automatic_recovery")) "\nThe normal app was restored after a setup error." else ""
        "setup_ready" -> "Game setup finished. Translation has not started. Prepare game files again, then confirm the update checkpoint to patch."
        "setup_cancelled" -> "Setup stopped. The original game app was verified. Translation has not started." +
            if (value.optBoolean("data_loss_may_have_happened")) " Local data may need downloading again." else ""
        "complete" -> if (value.has("removed")) {
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
