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

    fun freed(context: Context, state: JSONObject): String =
        string(context, if (state.optBoolean("removed_saved_apks")) "freed_removed_apks" else "freed_kept") + "\n" +
            string(context, "freed_amounts", "freed" to StorageBudget.freeSpaceLabel(state.optLong("freed_bytes")),
                "free" to StorageBudget.freeSpaceLabel(state.optLong("free_bytes")))

    /** Free up space's opt-in: <saved> is what it frees, <prepare> what the next preparation needs free. */
    fun removeSavedApks(context: Context, saved: Long, prepare: Long): String = string(context, "remove_saved_apks",
        "saved" to StorageBudget.freeSpaceLabel(saved), "prepare" to StorageBudget.freeSpaceLabel(prepare))

    fun removeConfirmation(context: Context): String = string(context, "remove_confirmation")

    fun completed(context: Context, state: JSONObject): String {
        if (state.has("removed")) return string(context, "removal_verified") + "\n" +
            string(context, "original_files_restored", "count" to state.getInt("removed")) + "\n" +
            string(context, "removed_login_note")
        val counts = state.optJSONObject("counts") ?: return string(context, "completed_no_counts")
        return string(context, "completed_counts", "text_tables" to counts.getInt("text_tables"),
            "applied_textures" to counts.getInt("applied_textures"), "skipped_tables" to counts.getInt("skipped_tables"),
            "skipped_textures" to counts.getInt("skipped_textures"))
    }

    fun firstSetup(context: Context): String = string(context, "first_setup_consent")

    fun setupUpdate(context: Context): String = string(context, "setup_update")

    fun patchConfirmation(context: Context): String =
        string(context, "patch_confirmation", "language" to PatchLanguage.name(PatchLanguage.current(context)))

    fun restore(context: Context, version: String): String = string(context, "restore_apk_only", "version" to version)
}
