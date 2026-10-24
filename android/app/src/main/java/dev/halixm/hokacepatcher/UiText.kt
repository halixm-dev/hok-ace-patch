package dev.halixm.hokacepatcher

import android.content.Context
import org.json.JSONObject

/**
 * Presentation-only text, read from the shared strings file (`resources/ui/strings.json`) that both
 * patchers use. Action keys, engine messages and diagnostic exports stay stable and untranslated.
 */
object UiText {
    /** Key -> language code -> text, for this patcher's keys. A class resource, so JVM unit tests read the same file. */
    private val strings: Map<String, Map<String, String>> by lazy {
        val stream = UiText::class.java.classLoader!!.getResourceAsStream("ui/strings.json")
            ?: error("ui/strings.json is missing from the build")
        val table = JSONObject(stream.use { String(it.readBytes(), Charsets.UTF_8) }).getJSONObject("strings")
        table.keys().asSequence().filter { key ->
            val platforms = table.getJSONObject(key).getJSONArray("platforms")
            (0 until platforms.length()).any { platforms.getString(it) == "android" }
        }.associateWith { key ->
            val entry = table.getJSONObject(key)
            listOf("en", "id").associateWith { entry.getString(it) }
        }
    }

    /** English text -> key, so code can keep showing the English it always showed. */
    private val keys: Map<String, String> by lazy { strings.entries.associate { (key, entry) -> entry.getValue("en") to key } }

    fun text(context: Context, source: String): String = translate(PatchLanguage.current(context), source)

    /** Exact matches only: never alter paths, hashes, action keys or raw diagnostic messages. */
    fun translate(code: String, source: String): String = keys[source]?.let { strings.getValue(it)[code] } ?: source

    /** The string <key> in the current language, with each `{name}` placeholder filled. */
    fun string(context: Context, key: String, vararg values: Pair<String, Any>): String =
        template(PatchLanguage.current(context), key, *values)

    private fun template(code: String, key: String, vararg values: Pair<String, Any>): String {
        val entry = strings[key] ?: error("No shared string $key")
        return values.fold(entry[code] ?: entry.getValue("en")) { text, (name, value) -> text.replace("{$name}", value.toString()) }
    }

    fun progress(context: Context, source: String): String {
        val code = PatchLanguage.current(context)
        if (code == "en") return source
        return keys[source]?.let { strings.getValue(it)[code] } ?: template(code, "progress_fallback")
    }

    /** A running step of ③ Start: its 1-based number, the total, and "Step N of M · <step>". */
    data class Step(val number: Int, val total: Int, val line: String)

    /** The step <state> reports in language <code>, or null for a record without one; removal and re-download name their own steps 4 and 5. */
    fun step(code: String, state: JSONObject): Step? {
        val number = WorkerStep.number(state) ?: return null
        val total = state.optInt("steps").takeIf { it >= number } ?: return null
        val action = state.optString("action")
        val name = when (number) {
            1 -> template(code, "android_step_check_game")
            2 -> template(code, "android_step_prepare_files")
            3 -> template(code, "android_step_unlock_access")
            4 -> when (action) {
                "remove" -> template(code, "android_step_build_original")
                "redownload" -> template(code, "android_step_find_damaged")
                else -> template(code, "step_translate")
            }
            5 -> when (action) {
                "remove" -> template(code, "android_step_write_original")
                "redownload" -> template(code, "android_step_delete_damaged")
                else -> template(code, "android_step_write")
            }
            else -> template(code, "android_step_restore_game_app")
        }
        return Step(number, total, template(code, "progress_step", "n" to number, "total" to total, "step" to name))
    }

    /** Translate only the measured storage summary, preserving its conservative GB numbers. */
    fun storage(context: Context, source: String): String {
        val shortage = Regex("Need ([0-9.]+) GB free for this step.\\nFree now: ([0-9.]+) GB.\\nClear at least ([0-9.]+) GB more, then try again.\\nKeep saved recovery files.").matchEntire(source)
        if (shortage != null) {
            val (need, free, more) = shortage.destructured
            return string(context, "storage_shortage", "need" to need, "free" to free, "more" to more)
        }
        val enough = Regex("Enough space now for this step.\\nNeeded: ([0-9.]+) GB free \\(rounded up\\).\\nTap Try again. Keep saved recovery files.").matchEntire(source)
        if (enough != null) return string(context, "storage_enough", "need" to enough.groupValues[1])
        return source
    }

    /**
     * A result state of ③ Start: its heading, one summary line, the run's own counts, then the login note; <english> names it in traces.
     * <gameReady> marks a result that leaves the game ready to play, so ③ leads with Open game.
     */
    data class Result(val english: String, val heading: String, val summary: String, val items: List<String>, val note: String = "",
                      val gameReady: Boolean = false)

    /** The result <state> reports in language <code>, or null when the worker record is not a result. Takes a code, not a Context, so JVM tests reach it. */
    fun result(code: String, state: JSONObject): Result? = when (state.optString("status")) {
        // ③ leads with Open game: the game's own update is the next step, and the note says what follows it.
        "complete" -> if (state.has("redownloaded")) Result("Damaged files deleted", translate(code, "Damaged files deleted"),
            template(code, "redownload_verified"), listOf(template(code, "redownload_files_deleted", "count" to state.getInt("redownloaded"))),
            template(code, "redownload_next_step"), gameReady = true)
        else if (state.has("removed")) Result("Translation removed", translate(code, "Translation removed"), template(code, "removal_verified"),
            listOf(template(code, "original_files_restored", "count" to state.getInt("removed"))), template(code, "removed_login_note"), gameReady = true)
        else {
            val counts = state.optJSONObject("counts")
            // The template's first line is the summary; each further line is one count.
            val lines = if (counts == null) listOf(template(code, "completed_no_counts")) else template(code, "completed_counts",
                "text_tables" to counts.getInt("text_tables"), "applied_textures" to counts.getInt("applied_textures"),
                "skipped_tables" to counts.getInt("skipped_tables"), "skipped_textures" to counts.getInt("skipped_textures")).lines()
            Result("Translation added", translate(code, "Translation added"), lines.first(), lines.drop(1), template(code, "added_login_note"), gameReady = true)
        }
        "recovered_unconfirmed" -> Result("Translation written", translate(code, "Translation written"), translate(code, WorkerStatus.UNCONFIRMED), emptyList(), gameReady = true)
        "space_freed" -> Result("Space freed", translate(code, "Space freed"),
            template(code, if (state.optBoolean("removed_saved_apks")) "freed_removed_apks" else "freed_kept"),
            template(code, "freed_amounts", "freed" to StorageBudget.freeSpaceLabel(state.optLong("freed_bytes")),
                "free" to StorageBudget.freeSpaceLabel(state.optLong("free_bytes"))).lines())
        else -> null
    }

    /** Free up space's opt-in: <saved> is what it frees, <prepare> what the next preparation needs free. */
    fun removeSavedApks(context: Context, saved: Long, prepare: Long): String = string(context, "remove_saved_apks",
        "saved" to size(saved), "prepare" to size(prepare))

    /** A size that never wraps between its number and its unit. */
    private fun size(bytes: Long): String = StorageBudget.freeSpaceLabel(bytes).replace(' ', ' ')

    /** <root>: a root run writes the files back and never touches the game app (ADR 0007). */
    fun removeConfirmation(context: Context, root: Boolean = false): String =
        string(context, if (root) "remove_confirmation_root" else "remove_confirmation")

    fun redownloadConfirmation(context: Context): String = string(context, "redownload_confirmation")

    fun firstSetup(context: Context): String = string(context, "first_setup_consent")

    fun setupUpdate(context: Context): String = string(context, "setup_update")

    fun patchConfirmation(context: Context, root: Boolean = false): String =
        string(context, if (root) "patch_confirmation_root" else "patch_confirmation",
            "language" to PatchLanguage.name(PatchLanguage.current(context)))


    fun restore(context: Context, version: String): String = string(context, "restore_apk_only", "version" to version)
}
