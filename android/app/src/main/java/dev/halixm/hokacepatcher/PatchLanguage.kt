package dev.halixm.hokacepatcher

import android.content.Context

/** The translation a patch installs. Codes match `tools/languages.py`; the engine refuses any other. */
object PatchLanguage {
    const val DEFAULT = "en"
    /** Code to the name shown on the picker, in display order. */
    val choices = linkedMapOf("en" to "English", "id" to "Bahasa Indonesia")
    private const val PREFERENCES = "patch-language"
    private const val KEY = "language"

    fun current(context: Context): String {
        val saved = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getString(KEY, DEFAULT)
        return if (saved in choices) saved!! else DEFAULT
    }

    fun set(context: Context, code: String) {
        require(code in choices) { "Unknown language $code" }
        // commit, not apply: a patch started right after choosing must read the new value.
        check(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit().putString(KEY, code).commit()) {
            "Cannot save the language choice"
        }
    }

    fun name(code: String): String = choices[code] ?: choices.getValue(DEFAULT)
}
