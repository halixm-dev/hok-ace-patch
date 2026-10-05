package dev.halixm.hokacepatcher

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** Separate irreversible signature conversion from translation and its file rollback. */
class FirstSetupCoordinator @JvmOverloads constructor(
    private val context: Context,
    private val transport: Transport,
    private val report: (String) -> Unit,
    private val recoveryMaterial: RecoveryMaterial? = null,
) {
    private val cancelled = AtomicBoolean(false)
    private val active = AtomicReference<FirstSetupJournal?>(null)
    fun cancel() { cancelled.set(true) }
    fun interrupted(message: String) {
        cancelled.set(true)
        active.get()?.let { journal -> if (journal.phase !in setOf(FirstSetupPhase.READY, FirstSetupPhase.CANCELLED)) journal.interrupted(message) }
    }
    fun pendingRecoveryResult(): JSONObject? = active.get()?.let { journal ->
        if (journal.phase in setOf(FirstSetupPhase.READY, FirstSetupPhase.CANCELLED)) null else JSONObject().put("status", "recovery_required")
            .put("action", "first_setup").put("setup", journal.id).put("translation_started", false)
            .put("error", journal.snapshot().optString("last_error", "Recover or finish game setup"))
    }
    /** Implementations must use fixed game targets and independently inspect installed bytes/identity. */
    interface Transport {
        fun verifyInstalled(expected: ApkIdentity)
        fun gameAbsent(): Boolean
        fun forceStop()
        fun uninstallVerified(expectedSource: ApkIdentity)
        fun installNormal(file: File, expected: ApkIdentity)
    }
    /** In-process fixture seam; the application uses RecoveryStore's full content verification. */
    fun interface RecoveryMaterial { fun verify(expected: ApkIdentity): File }

    private fun recovery(expected: ApkIdentity): File {
        expected.requireRecovery()
        recoveryMaterial?.let { return it.verify(expected) }
        val store = RecoveryStore(context)
        check(store.verify(expected.sha256) == expected) { "First setup recovery identity changed" }
        return store.normal(expected.sha256)
    }

    private fun progress(message: String) {
        try { report(message) }
        catch (error: Throwable) { android.util.Log.w("HokAceSetup", "Progress display unavailable", error) }
    }

    private fun <T> exclusive(action: () -> T): T {
        val sessions = File(context.filesDir, "sessions")
        DurableFiles.createDirectories(sessions)
        RandomAccessFile(File(sessions, "coordinator.lock"), "rw").use { file ->
            file.channel.use { channel ->
                checkNotNull(channel.tryLock()) { "Another patch or recovery is running" }.use {
                    check(SessionJournal.pending(sessions).isEmpty()) { "Recover the interrupted translation before first setup" }
                    return action()
                }
            }
        }
    }

    @JvmOverloads fun run(prepared: ApkPreparation.Prepared, engineId: String, dataLossConfirmed: Boolean,
                         consentRequest: String? = null): JSONObject = exclusive {
        check(dataLossConfirmed) { "First setup requires explicit data-loss consent" }
        EmergencyRestoreStore(context).requireResolved()
        check(consentRequest != null || recoveryMaterial != null) { "First setup requires a verified one-use consent request" }
        check(!cancelled.get()) { "Setup cancelled before removal" }
        check(FirstSetupJournal.pending(context).isEmpty()) { "Recover the unfinished first setup" }
        val normalFile = recovery(prepared.normal)
        StorageBudget.requireAvailable(context.filesDir, "First setup installer", prepared.normal.bytes)
        transport.verifyInstalled(prepared.source)
        check(!cancelled.get()) { "Setup cancelled before removal" }
        if (consentRequest != null) FirstSetupRequestStore(context).begin(consentRequest, prepared)
        val journal = FirstSetupJournal.create(File(context.filesDir, "first-setups"), prepared, engineId, true, consentRequest)
        active.set(journal)
        try {
            transport.forceStop()
            check(!cancelled.get()) { "Setup cancelled before removal" }
            journal.beforeUninstall()
            progress("Removing the old game app and its local data")
            transport.uninstallVerified(prepared.source)
            check(transport.gameAbsent()) { "Old game app remains installed; normal install refused" }
            install(journal, normalFile)
        } catch (error: Throwable) {
            val message = error.message ?: "First setup interrupted"
            runCatching { journal.interrupted(message) }.exceptionOrNull()?.let { error.addSuppressed(it) }
            try {
                // Reload durable intent; a failed journal write must not authorize a new mutation.
                val retained = FirstSetupJournal.load(journal.directory)
                active.set(retained)
                progress("Checking and restoring the game app after a setup error")
                return@exclusive recoverJournal(retained).put("automatic_recovery", true).put("warning", message.take(4096))
            } catch (recoveryError: Throwable) {
                error.addSuppressed(recoveryError)
                runCatching { active.get()?.interrupted("$message; recovery stopped: ${recoveryError.message}".take(4096)) }
                throw error
            }
        }
    }

    private fun install(journal: FirstSetupJournal, normalFile: File): JSONObject {
        journal.beforeInstall()
        progress("Installing the verified normal game app")
        transport.installNormal(normalFile, journal.normal)
        transport.verifyInstalled(journal.normal)
        journal.normalInstalled(journal.normal)
        progress("Open the game, finish its downloads, then close it before translation")
        return journal.result()
    }

    /** Recover installation only. Never repeat an uninstall or claim deleted user data was restored. */
    fun recover(id: String): JSONObject = exclusive {
        GameFilePolicy.session(id)
        val journal = FirstSetupJournal.load(File(context.filesDir, "first-setups/$id"))
        active.set(journal)
        check(journal.phase !in setOf(FirstSetupPhase.READY, FirstSetupPhase.CANCELLED)) { "First setup is already finished" }
        try {
            recoverJournal(journal)
        } catch (error: Throwable) {
            runCatching { journal.interrupted(error.message ?: "First setup recovery interrupted") }
                .exceptionOrNull()?.let { error.addSuppressed(it) }
            throw error
        }
    }

    private fun recoverJournal(journal: FirstSetupJournal): JSONObject {
        val normalFile = recovery(journal.normal)
        if (!transport.gameAbsent()) {
            // An ambiguous reply may mean normal installation already landed.
            // A different installed app is never deleted during recovery.
            if (journal.phase in setOf(FirstSetupPhase.PREPARED, FirstSetupPhase.UNINSTALL_INTENT)) {
                val originalPresent = runCatching { transport.verifyInstalled(journal.source) }.isSuccess
                if (originalPresent) {
                    journal.cancelWithOriginal(journal.source)
                    return journal.result()
                }
            }
            transport.verifyInstalled(journal.normal)
            check(journal.phase != FirstSetupPhase.PREPARED) { "First setup has no uninstall intent" }
            journal.normalInstalled(journal.normal)
            return journal.result()
        }
        check(journal.phase in setOf(FirstSetupPhase.UNINSTALL_INTENT, FirstSetupPhase.INSTALL_INTENT)) {
            "Missing game app has no matching first setup install intent"
        }
        StorageBudget.requireAvailable(context.filesDir, "First setup recovery installer", journal.normal.bytes)
        return install(journal, normalFile)
    }

    fun finishUpdate(id: String, confirmed: Boolean): JSONObject = exclusive {
        check(confirmed) { "Finish every in-game update and close the game first" }
        check(!cancelled.get()) { "Setup confirmation cancelled" }
        GameFilePolicy.session(id)
        val journal = FirstSetupJournal.load(File(context.filesDir, "first-setups/$id"))
        active.set(journal)
        check(journal.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE)
        recovery(journal.normal)
        transport.verifyInstalled(journal.normal)
        check(!cancelled.get()) { "Setup confirmation cancelled" }
        transport.forceStop()
        journal.updateFinished(true, journal.normal)
        journal.result()
    }
}
