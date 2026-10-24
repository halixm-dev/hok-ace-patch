package dev.halixm.hokacepatcher

import android.content.Context

/**
 * What starts the patcher's worker with the privileges to reach the game's files (GLOSSARY: shell provider).
 * The user picks one on the home screen; the app never picks one by detection. [available] is false for a
 * provider this build cannot start yet: its guide says so and Start refuses it.
 */
enum class ShellProvider(val key: String, val label: String, val beta: Boolean, val available: Boolean) {
    SHIZUKU("shizuku", "Shizuku", false, true),
    WIRELESS("wireless", "Wireless debugging", true, true),
    ROOT("root", "Root", true, false);

    companion object {
        /** Shizuku stays the default, so a phone patched before the picker existed keeps the provider that patched it. */
        val DEFAULT = SHIZUKU
        private const val PREFERENCES = "shell-provider"
        private const val KEY = "provider"
        /** Worker connections refuse a Shizuku server running as root; the UI matches on it. */
        const val SHIZUKU_AS_ROOT = "Shizuku is running with root. Choose the Root provider instead."

        /** The provider <saved> names; nothing saved, or a key this build does not know, is [DEFAULT]. */
        fun of(saved: String?): ShellProvider = entries.firstOrNull { it.key == saved } ?: DEFAULT

        fun current(context: Context): ShellProvider = of(
            context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getString(KEY, null))

        fun set(context: Context, provider: ShellProvider) {
            // commit, not apply: a run started right after choosing must read the new value.
            check(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit().putString(KEY, provider.key).commit()) {
                "Cannot save the shell provider choice"
            }
        }
    }
}

/** What the worker does at the uid it was started as: 2000 is shell, 0 is root, anything else is refused. */
enum class WorkerAccess {
    SHELL;

    companion object {
        const val SHELL_UID = 2000
        const val ROOT_UID = 0

        fun of(uid: Int): WorkerAccess = when (uid) {
            SHELL_UID -> SHELL
            ROOT_UID -> error("The worker runs as root, which this build does not support yet")
            else -> error("The worker runs as uid $uid; only shell (2000) is supported")
        }
    }
}
