package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File

/**
 * What the saved records let recovery do: restore an interrupted patch, finish first setup, or reinstall
 * a retained normal APK. A run that stopped in its read-only checks leaves none, so it offers no recovery.
 */
data class RecoveryMaterial(val patch: Boolean, val setup: Boolean, val savedApk: Boolean) {
    val any: Boolean get() = patch || setup || savedApk

    companion object {
        /** Throws when a record cannot be read; the caller then offers every recovery action. */
        fun read(context: Context): RecoveryMaterial {
            val emergency = EmergencyRestoreStore(context).snapshot()?.optString("status") == "verification_pending"
            val retained = File(context.filesDir, "recovery").listFiles().orEmpty().any {
                it.isDirectory && it.name.matches(Regex("[0-9a-f]{64}"))
            }
            return of(SessionJournal.pending(File(context.filesDir, "sessions")).isNotEmpty(),
                FirstSetupJournal.pending(context).isNotEmpty(), emergency, retained, ShellProvider.current(context) == ShellProvider.ROOT)
        }

        /**
         * Under Root a retained normal APK is a shell run's leftover: a root run never replaces the game app, so
         * only a pending emergency restore offers the reinstall there (ADR 0007).
         */
        fun of(patch: Boolean, setup: Boolean, emergency: Boolean, retained: Boolean, root: Boolean) =
            RecoveryMaterial(patch, setup, emergency || (retained && !root))
    }
}
