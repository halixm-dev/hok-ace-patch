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
        if (pristine.optString("mode") != "rebuilt") {
            val stale = pristine.optInt("stale")
            return listOf(if (stale > 0) {
                "The kept pristine delta no longer matches $stale file(s); built from the game files as they are"
            } else "No pristine delta for this phone: built from the game files as they are")
        }
        val lines = mutableListOf("Rebuilt ${pristine.optInt("rebuilt")} files from the pristine delta")
        val restored = pristine.optJSONArray("restored")
        if (restored != null && restored.length() > 0) {
            lines += "${restored.length()} file(s) this build leaves untranslated go back to their original bytes"
        }
        return lines
    }
}
