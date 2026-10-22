package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File
import org.json.JSONObject

/**
 * Where the Android patcher keeps its pristine delta. The delta is made and applied by the engine
 * (`tools/pristine_delta.py` through `android_bridge`); this side only names the files and reports.
 */
object PristineDelta {
    /** In a session: the build input's rebuilt pristine files, deleted once the build is done. */
    const val BUILD_COPY = "pristine"
    /** In a session: the delta of the install it stages, promoted once that install is complete. */
    const val SESSION_DELTA = "pristine-delta.bin"

    fun directory(context: Context) = File(context.filesDir, "pristine")

    /** Whether a translated phone can be repatched without clearing the game's data. */
    fun held(context: Context) = File(directory(context), "delta.bin").isFile

    /** Log lines for `build_snapshot`'s `pristine` report. */
    fun describe(pristine: JSONObject): List<String> {
        if (pristine.optString("mode") == "removed") {
            return listOfNotNull("Restoring ${pristine.optInt("rebuilt")} original game files", assetsRestored(pristine))
        }
        if (pristine.optString("mode") != "rebuilt") {
            val stale = pristine.optInt("stale")
            return listOf(if (stale > 0) {
                "The kept pristine delta no longer matches $stale file(s); built from the game files as they are"
            } else "No pristine delta for this phone: built from the game files as they are")
        }
        val lines = mutableListOf("Rebuilt ${pristine.optInt("rebuilt")} files from the pristine delta")
        val replaced = pristine.optJSONArray("replaced")
        if (replaced != null && replaced.length() > 0) {
            lines += "${replaced.length()} file(s) the game update replaced hold none of this patcher's translation; built from them as the update left them"
        }
        val restored = pristine.optJSONArray("restored")
        if (restored != null && restored.length() > 0) {
            lines += "${restored.length()} file(s) this build leaves untranslated go back to their original bytes"
        }
        assetsRestored(pristine)?.let { lines += it }
        return lines
    }

    /** The packages asset restore (ADR 0008) wrote original bytes back into, or null when none. */
    private fun assetsRestored(pristine: JSONObject): String? {
        val packages = pristine.optJSONArray("assets_restored") ?: return null
        if (packages.length() == 0) return null
        val names = (0 until packages.length()).joinToString(", ") { packages.getString(it) }
        return "Wrote the original bytes back into package $names, which a game update kept partly translated"
    }
}
