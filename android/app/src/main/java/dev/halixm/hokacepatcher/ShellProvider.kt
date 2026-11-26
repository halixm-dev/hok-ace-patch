package dev.halixm.hokacepatcher

import android.content.Context
import android.os.Build

/**
 * What starts the patcher's worker with the privileges to reach the game's files (GLOSSARY: shell provider).
 * The user picks one on the home screen from the providers supported by their Android version.
 */
enum class ShellProvider(val key: String, val label: String) {
    WIRELESS("wireless", "Wireless debugging"),
    SHIZUKU("shizuku", "Shizuku"),
    ROOT("root", "Root");

    val available: Boolean get() = availableOn(Build.VERSION.SDK_INT)

    fun availableOn(sdk: Int): Boolean = this != WIRELESS || sdk >= Build.VERSION_CODES.R

    companion object {
        private const val PREFERENCES = "shell-provider"
        private const val KEY = "provider"
        /** Worker connections refuse a Shizuku server running as root; the UI matches on it. */
        const val SHIZUKU_AS_ROOT = "Shizuku is running with root. Choose the Root provider instead."

        /** Resolve the preference for this OS. Saved runs keep the exact provider recorded in RunStore. */
        fun of(saved: String?, sdk: Int): ShellProvider =
            entries.firstOrNull { it.key == saved && it.availableOn(sdk) }
                ?: if (WIRELESS.availableOn(sdk)) WIRELESS else SHIZUKU

        fun current(context: Context): ShellProvider = of(
            context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getString(KEY, null),
            Build.VERSION.SDK_INT)

        fun set(context: Context, provider: ShellProvider) {
            // commit, not apply: a run started right after choosing must read the new value.
            check(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit().putString(KEY, provider.key).commit()) {
                "Cannot save the shell provider choice"
            }
        }
    }
}

/**
 * What the worker does at the uid it was started as: 2000 is shell, which reaches the game through the
 * access APK and `run-as`; 0 is root, which writes the game's files itself (ADR 0007). Anything else is refused.
 */
enum class WorkerAccess {
    SHELL, ROOT;

    companion object {
        const val SHELL_UID = 2000
        const val ROOT_UID = 0

        fun of(uid: Int): WorkerAccess = when (uid) {
            SHELL_UID -> SHELL
            ROOT_UID -> ROOT
            else -> error("The worker runs as uid $uid; only shell (2000) and root (0) are supported")
        }

        /** The running worker's own access, as its uid reports it. */
        fun of(device: IPrivilegedDeviceService): WorkerAccess =
            of(org.json.JSONObject(device.diagnostics()).getInt("uid"))

    }
}
