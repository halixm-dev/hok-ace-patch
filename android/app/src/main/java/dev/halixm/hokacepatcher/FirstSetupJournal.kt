package dev.halixm.hokacepatcher

import android.content.Context
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.util.UUID

enum class FirstSetupPhase { PREPARED, UNINSTALL_INTENT, INSTALL_INTENT, WAITING_FOR_GAME_UPDATE, READY, CANCELLED }

/** First-install data loss is irreversible; retain its own intent and update-wait state. */
class FirstSetupJournal private constructor(val directory: File, private val value: JSONObject) {
    private val storage = AtomicFile(File(directory, "journal.json"))
    val id: String get() = value.getString("id")
    @get:Synchronized val phase: FirstSetupPhase get() = FirstSetupPhase.valueOf(value.getString("phase"))
    val normal: ApkIdentity get() = ApkIdentity.fromJson(value.getJSONObject("normal"))
    val source: ApkIdentity get() = ApkIdentity.fromJson(value.getJSONObject("source"))
    val preparation: String get() = value.getString("preparation")
    @get:Synchronized val normalVerified: Boolean get() = value.getBoolean("normal_verified")

    @Synchronized fun snapshot(): JSONObject = JSONObject(value.toString())
    private fun persist() {
        DurableFiles.createDirectories(directory)
        value.put("updated_ms", System.currentTimeMillis())
        val bytes = value.toString().toByteArray(Charsets.UTF_8)
        val stream = storage.startWrite()
        try {
            stream.write(bytes); stream.fd.sync(); storage.finishWrite(stream)
            DurableFiles.syncDirectory(directory)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
        check(DurableFiles.readCommitted(storage.baseFile).contentEquals(bytes)) { "First setup journal read-back differs" }
    }
    @Synchronized fun beforeUninstall() {
        check(phase == FirstSetupPhase.PREPARED)
        check(value.getBoolean("data_loss_confirmed"))
        value.put("phase", FirstSetupPhase.UNINSTALL_INTENT.name).put("normal_verified", false)
        persist()
    }
    @Synchronized fun beforeInstall() {
        check(phase in setOf(FirstSetupPhase.UNINSTALL_INTENT, FirstSetupPhase.INSTALL_INTENT))
        value.put("phase", FirstSetupPhase.INSTALL_INTENT.name).put("normal_verified", false)
        persist()
    }
    @Synchronized fun normalInstalled(verified: ApkIdentity) {
        check(phase in setOf(FirstSetupPhase.UNINSTALL_INTENT, FirstSetupPhase.INSTALL_INTENT,
            FirstSetupPhase.WAITING_FOR_GAME_UPDATE))
        verified.requireRecovery(); check(verified == normal) { "First setup installed identity differs" }
        value.put("phase", FirstSetupPhase.WAITING_FOR_GAME_UPDATE.name).put("normal_verified", true)
        persist()
    }
    @Synchronized fun updateFinished(confirmed: Boolean, verified: ApkIdentity) {
        check(confirmed) { "Finish every in-game update and close the game first" }
        check(phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE && normalVerified)
        verified.requireRecovery(); check(verified == normal) { "Game app changed during the update" }
        value.put("phase", FirstSetupPhase.READY.name).put("update_finished_and_game_closed", true)
        persist()
    }
    @Synchronized fun interrupted(message: String) {
        if (phase in setOf(FirstSetupPhase.READY, FirstSetupPhase.CANCELLED)) return
        value.put("last_error", message.take(4096)); persist() // Keep uninstall/install intent intact.
    }
    @Synchronized fun cancelWithOriginal(verified: ApkIdentity) {
        check(phase in setOf(FirstSetupPhase.PREPARED, FirstSetupPhase.UNINSTALL_INTENT))
        check(verified == source)
        value.put("data_loss_may_have_happened", phase == FirstSetupPhase.UNINSTALL_INTENT)
            .put("phase", FirstSetupPhase.CANCELLED.name).put("original_verified", true)
        persist()
    }
    @Synchronized fun result(): JSONObject {
        if (phase == FirstSetupPhase.CANCELLED) return JSONObject().put("status", "setup_cancelled")
            .put("action", "first_setup").put("setup", id).put("translation_started", false)
            .put("original_verified", value.getBoolean("original_verified"))
            .put("data_loss_may_have_happened", value.getBoolean("data_loss_may_have_happened"))
        check(normalVerified && phase in setOf(FirstSetupPhase.WAITING_FOR_GAME_UPDATE, FirstSetupPhase.READY)) {
            "First setup requires independently verified normal installation"
        }
        return JSONObject().put("status", if (phase == FirstSetupPhase.READY) "setup_ready" else "setup_waiting")
            .put("action", "first_setup").put("setup", id).put("normal", normal.sha256)
            .put("data_loss_confirmed", true).put("translation_started", false)
    }

    companion object {
        private const val INITIALIZING = ".creating-"
        @JvmOverloads fun create(parent: File, prepared: ApkPreparation.Prepared, engineId: String, dataLossConfirmed: Boolean,
                                consentRequest: String? = null): FirstSetupJournal {
            check(dataLossConfirmed) { "First setup requires explicit data-loss consent" }
            check(prepared.requiresSignatureConversion && !prepared.source.debuggable) { "Converted or debug games cannot enter first setup" }
            prepared.normal.requireRecovery()
            check(listOf(prepared.source, prepared.normal, prepared.access).all {
                it.bytes in 1..(3L * 1024 * 1024 * 1024) && it.sha256.matches(Regex("[0-9a-f]{64}")) &&
                    it.certificateSha256.matches(Regex("[0-9a-f]{64}"))
            }) { "First setup identities are invalid" }
            check(prepared.source.packageName == prepared.normal.packageName &&
                prepared.source.versionCode == prepared.normal.versionCode && prepared.source.versionName == prepared.normal.versionName)
            check(prepared.access.debuggable && prepared.access.packageName == prepared.normal.packageName &&
                prepared.access.certificateSha256 == prepared.normal.certificateSha256 &&
                prepared.access.versionCode == prepared.normal.versionCode && prepared.access.versionName == prepared.normal.versionName)
            GameFilePolicy.session(prepared.directory.name)
            require(engineId.matches(Regex("[0-9a-f]{64}")))
            val id = UUID.randomUUID().toString()
            if (consentRequest != null) GameFilePolicy.session(consentRequest)
            val target = File(parent, id)
            val staging = File(parent, "$INITIALIZING$id")
            check(!target.exists() && !staging.exists()) { "First setup journal already exists" }
            val staged = FirstSetupJournal(staging, JSONObject().put("schema", 1).put("id", id)
                .put("preparation", prepared.directory.name).put("engine_id", engineId)
                .put("source", prepared.source.json()).put("normal", prepared.normal.json()).put("consent_request", consentRequest)
                .put("data_loss_confirmed", true).put("normal_verified", false)
                .put("phase", FirstSetupPhase.PREPARED.name))
            // Nothing can mutate the game until the initialized directory is published and synced.
            staged.persist()
            check(staging.renameTo(target)) { "Cannot publish first setup journal" }
            DurableFiles.syncDirectory(parent)
            return load(target)
        }
        fun load(directory: File): FirstSetupJournal {
            GameFilePolicy.session(directory.name)
            val path = File(directory, "journal.json")
            check(path.length() in 1..16384) { "First setup journal is missing or oversized" }
            val value = JSONObject(String(DurableFiles.readCommitted(path), Charsets.UTF_8))
            check(value.getInt("schema") == 1 && value.getString("id") == directory.name && value.getBoolean("data_loss_confirmed"))
            GameFilePolicy.session(value.getString("preparation"))
            if (value.has("consent_request")) GameFilePolicy.session(value.getString("consent_request"))
            val result = FirstSetupJournal(directory, value)
            result.normal.requireRecovery()
            check(value.getString("engine_id").matches(Regex("[0-9a-f]{64}")))
            check(listOf(result.source, result.normal).all {
                it.bytes in 1..(3L * 1024 * 1024 * 1024) && it.sha256.matches(Regex("[0-9a-f]{64}")) &&
                    it.certificateSha256.matches(Regex("[0-9a-f]{64}"))
            }) { "First setup stored identities are invalid" }
            check(!result.source.debuggable && result.source.certificateSha256 != GameSigner.CERTIFICATE_SHA256)
            check(result.source.packageName == result.normal.packageName && result.source.versionCode == result.normal.versionCode &&
                result.source.versionName == result.normal.versionName)
            if (result.phase == FirstSetupPhase.READY) check(result.normalVerified && value.getBoolean("update_finished_and_game_closed"))
            if (result.phase == FirstSetupPhase.CANCELLED) check(!result.normalVerified && value.getBoolean("original_verified") &&
                value.has("data_loss_may_have_happened"))
            if (result.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE) check(result.normalVerified)
            if (result.phase in setOf(FirstSetupPhase.PREPARED, FirstSetupPhase.UNINSTALL_INTENT,
                FirstSetupPhase.INSTALL_INTENT)) check(!result.normalVerified)
            result.phase
            return result
        }
        fun history(context: Context): List<FirstSetupJournal> = File(context.filesDir, "first-setups").listFiles()
            .orEmpty().filter { it.isDirectory }.filter {
                if (it.name.startsWith(INITIALIZING)) {
                    GameFilePolicy.session(it.name.removePrefix(INITIALIZING))
                    false // Reserved unpublished directories cannot be loaded or used for mutation.
                } else { GameFilePolicy.session(it.name); true }
            }.map { load(it) }

        fun pending(context: Context): List<FirstSetupJournal> = history(context)
            .filter { it.phase !in setOf(FirstSetupPhase.READY, FirstSetupPhase.CANCELLED) }
    }
}
