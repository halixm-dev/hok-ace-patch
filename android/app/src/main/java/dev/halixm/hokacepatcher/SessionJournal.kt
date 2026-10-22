package dev.halixm.hokacepatcher

import android.util.AtomicFile
import java.io.File
import java.nio.file.Files
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

enum class PatchPhase {
    PREPARED, WAITING_FOR_GAME_UPDATE, SNAPSHOT_ACCESS_INSTALLED, SNAPSHOT_READY,
    NORMAL_RESTORED_FOR_BUILD, BUILDING, STAGED, APPLY_ACCESS_INSTALLED, APPLYING,
    RESTORING, COMPLETE, RECOVERY_REQUIRED, CANCELLED,
}

/** Intent is durably committed before each mutation; incomplete work can never report completion. */
class SessionJournal private constructor(val directory: File, private val value: JSONObject) {
    private val storage = AtomicFile(File(directory, "journal.json"))
    val id: String get() = value.getString("id")
    val phase: PatchPhase get() = PatchPhase.valueOf(value.getString("phase"))
    val hasMutationIntent: Boolean get() = !value.isNull("mutation_intent")
    val hasRecoveryNormalIntent: Boolean get() = !value.isNull("recovery_normal_intent")
    val dirtyPackages: Boolean get() = value.optBoolean("packages_dirty", false)
    val recoveryId: String get() = value.getString("recovery_id")
    /** The run wrote and verified its whole payload, so its pristine delta describes what it overwrote. */
    val payloadVerified: Boolean get() = value.optBoolean("patch_payload_verified", false)
    /** Closed with its payload written but the game files not checked again; see [closeUnconfirmed]. */
    val layerUnconfirmed: Boolean get() = phase == PatchPhase.CANCELLED && value.optString("layer_unconfirmed").isNotEmpty()
    val recoveryCompletionPhase: PatchPhase get() =
        if (!dirtyPackages && payloadVerified) PatchPhase.COMPLETE
        else PatchPhase.CANCELLED

    @Synchronized fun snapshot(): JSONObject = JSONObject(value.toString())

    /** Recovery results use retained counters; loading a new Python engine is unnecessary. */
    @Synchronized fun terminalResult(): JSONObject {
        check(phase in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED) &&
            value.optBoolean("normal_verified", false) && !dirtyPackages && !hasMutationIntent && !hasRecoveryNormalIntent) {
            "Recovery result requires a resolved session and verified normal APK"
        }
        val status = when {
            phase == PatchPhase.COMPLETE -> "complete"
            layerUnconfirmed -> "recovered_unconfirmed"
            else -> "recovered"
        }
        val result = JSONObject().put("status", status)
            .put("action", "recover").put("session", id).put("phase", phase.name)
        if (phase == PatchPhase.COMPLETE) result.put("counts", value.opt("counts") ?: JSONObject.NULL)
        return result
    }

    /** Preserve the unresolved package intent while separately journaling emergency APK restoration. */
    @Synchronized fun beginRecoveryNormal(identity: ApkIdentity) {
        check(phase == PatchPhase.RECOVERY_REQUIRED)
        identity.requireRecovery()
        check(identity.sha256 == recoveryId)
        value.put("recovery_normal_intent", identity.json()).put("normal_verified", false)
        persist()
    }

    @Synchronized fun recoveryNormalVerified() {
        check(phase == PatchPhase.RECOVERY_REQUIRED)
        value.put("recovery_normal_intent", JSONObject.NULL).put("normal_verified", true)
        persist()
    }

    private fun persist() {
        DurableFiles.createDirectories(directory)
        value.put("updated_ms", System.currentTimeMillis())
        val bytes = value.toString().toByteArray(Charsets.UTF_8)
        val stream = storage.startWrite()
        try {
            stream.write(bytes)
            stream.fd.sync()
            storage.finishWrite(stream)
            DurableFiles.syncDirectory(directory)
        } catch (error: Throwable) {
            storage.failWrite(stream)
            throw error
        }
        check(DurableFiles.readCommitted(storage.baseFile).contentEquals(bytes)) { "Session journal read-back differs" }
    }

    @Synchronized fun intent(operation: String, detail: JSONObject = JSONObject()) {
        check(!hasMutationIntent) { "An earlier mutation is unresolved" }
        check(operation in setOf("install_access", "install_normal", "first_uninstall",
            "first_install", "write_file", "delete_file", "clear_watchdog", "rollback_file", "restore_watchdog")) {
            "Unknown journal operation"
        }
        value.put("mutation_intent", JSONObject().put("operation", operation).put("detail", detail))
        if (operation in setOf("install_access", "install_normal", "first_uninstall", "first_install"))
            value.put("normal_verified", false)
        if (operation in setOf("write_file", "delete_file", "clear_watchdog")) {
            value.put("packages_dirty", true).put("patch_payload_verified", false)
        }
        persist()
    }

    @Synchronized fun outcome(next: PatchPhase, updates: JSONObject = JSONObject()) {
        val allowed = when (phase) {
            PatchPhase.PREPARED -> setOf(PatchPhase.WAITING_FOR_GAME_UPDATE, PatchPhase.SNAPSHOT_ACCESS_INSTALLED,
                PatchPhase.RESTORING, PatchPhase.CANCELLED)
            PatchPhase.WAITING_FOR_GAME_UPDATE -> setOf(PatchPhase.SNAPSHOT_ACCESS_INSTALLED,
                PatchPhase.RESTORING, PatchPhase.CANCELLED)
            PatchPhase.SNAPSHOT_ACCESS_INSTALLED -> setOf(PatchPhase.SNAPSHOT_READY, PatchPhase.RESTORING)
            // The access APK stays installed through the build (as on Windows); older journals went
            // through NORMAL_RESTORED_FOR_BUILD and APPLY_ACCESS_INSTALLED, which still recover.
            PatchPhase.SNAPSHOT_READY -> setOf(PatchPhase.BUILDING, PatchPhase.NORMAL_RESTORED_FOR_BUILD,
                PatchPhase.RESTORING)
            PatchPhase.NORMAL_RESTORED_FOR_BUILD -> setOf(PatchPhase.BUILDING, PatchPhase.RESTORING, PatchPhase.CANCELLED)
            PatchPhase.BUILDING -> setOf(PatchPhase.STAGED, PatchPhase.RESTORING, PatchPhase.CANCELLED)
            PatchPhase.STAGED -> setOf(PatchPhase.APPLYING, PatchPhase.APPLY_ACCESS_INSTALLED, PatchPhase.RESTORING,
                PatchPhase.CANCELLED)
            PatchPhase.APPLY_ACCESS_INSTALLED -> setOf(PatchPhase.APPLYING, PatchPhase.RESTORING)
            PatchPhase.APPLYING -> setOf(PatchPhase.APPLYING, PatchPhase.RESTORING)
            PatchPhase.RESTORING -> setOf(PatchPhase.RESTORING, PatchPhase.NORMAL_RESTORED_FOR_BUILD, PatchPhase.COMPLETE,
                PatchPhase.CANCELLED, PatchPhase.WAITING_FOR_GAME_UPDATE)
            PatchPhase.RECOVERY_REQUIRED -> setOf(PatchPhase.RESTORING)
            PatchPhase.COMPLETE, PatchPhase.CANCELLED -> emptySet()
        }
        check(next in allowed || next == PatchPhase.RECOVERY_REQUIRED) { "Invalid patch state transition" }
        if (next == PatchPhase.COMPLETE || next == PatchPhase.CANCELLED) {
            check(updates.optBoolean("normal_verified", false)) {
                "The normal game APK has not been verified"
            }
            check(!hasMutationIntent ||
                value.getJSONObject("mutation_intent").getString("operation") == "install_normal") {
                "A mutation outcome is unresolved"
            }
            check(!updates.optBoolean("packages_dirty", value.optBoolean("packages_dirty", false))) {
                "Package consistency is unresolved"
            }
        }
        for (name in updates.keys()) {
            check(name !in setOf("schema", "id", "recovery_id", "engine_id", "mutation_intent", "phase")) {
                "Cannot replace a journal identity field"
            }
            value.put(name, updates.get(name))
        }
        // A newly verified installed APK resolves an earlier interrupted emergency APK intent.
        if (updates.has("normal_verified")) value.put("recovery_normal_intent", JSONObject.NULL)
        value.put("phase", next.name).put("mutation_intent", JSONObject.NULL)
        persist()
    }

    /**
     * Close a run that left no game file mid-change, once the caller has verified the normal APK is
     * installed. Nothing is rolled back: a clean run has nothing to roll back. A run whose payload was
     * verified is marked `layer_unconfirmed` (<reason>), so its pristine delta is still kept.
     */
    @Synchronized fun closeUnconfirmed(reason: String) {
        check(phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED) && !dirtyPackages) {
            "Only an unfinished run with no game file mid-change can close without recovery"
        }
        outcome(PatchPhase.RESTORING)
        val updates = JSONObject().put("normal_verified", true)
        if (payloadVerified) updates.put("layer_unconfirmed", reason.take(4096))
        outcome(PatchPhase.CANCELLED, updates)
    }

    @Synchronized fun recoveryRequired(message: String) {
        value.put("phase", PatchPhase.RECOVERY_REQUIRED.name).put("last_error", message.take(4096))
        persist() // Preserve pending intent and the dirty flag for rollback.
    }

    @Synchronized fun fileCommitted(relative: String) {
        check(hasMutationIntent) { "File commit has no durable intent" }
        val files = value.getJSONArray("committed_files")
        files.put(relative)
        value.put("mutation_intent", JSONObject.NULL).put("phase", PatchPhase.APPLYING.name)
        persist()
    }

    companion object {
        private const val INITIALIZING = ".creating-"
        private const val MAX_BYTES = 1024 * 1024
        fun create(parent: File, recoveryId: String, engineId: String): SessionJournal {
            require(recoveryId.matches(Regex("[0-9a-f]{64}"))) { "Invalid recovery identity" }
            require(engineId.matches(Regex("[0-9a-f]{64}"))) { "Invalid engine identity" }
            val id = UUID.randomUUID().toString()
            val directory = File(parent, id)
            val staging = File(parent, "$INITIALIZING$id")
            check(!directory.exists() && !staging.exists()) { "Session already exists" }
            val value = JSONObject().put("schema", 1).put("id", id).put("recovery_id", recoveryId)
                .put("engine_id", engineId).put("phase", PatchPhase.PREPARED.name)
                .put("created_ms", System.currentTimeMillis()).put("normal_verified", false)
                .put("packages_dirty", false).put("mutation_intent", JSONObject.NULL)
                .put("committed_files", JSONArray())
            // A discoverable session must already have its complete, durable initial journal.
            SessionJournal(staging, value).persist()
            check(staging.renameTo(directory)) { "Cannot publish patch journal" }
            DurableFiles.syncDirectory(parent)
            return load(directory)
        }

        fun load(directory: File): SessionJournal {
            GameFilePolicy.session(directory.name)
            check(directory.isDirectory && !Files.isSymbolicLink(directory.toPath())) { "Invalid session directory" }
            val path = File(directory, "journal.json")
            val candidates = listOf(path, File(path.path + ".bak")).filter { it.exists() }
            check(candidates.isNotEmpty() && candidates.all {
                it.isFile && !Files.isSymbolicLink(it.toPath()) && it.length() in 1..MAX_BYTES
            }) { "Session journal is missing, linked or oversized" }
            val bytes = DurableFiles.readCommitted(path)
            check(bytes.size in 1..MAX_BYTES) { "Session journal is missing or oversized" }
            val value = JSONObject(String(bytes, Charsets.UTF_8))
            check(value.getInt("schema") == 1 && value.getString("id") == directory.name) { "Unsupported session journal" }
            check(value.getString("recovery_id").matches(Regex("[0-9a-f]{64}"))) { "Invalid recovery identity" }
            check(value.getString("engine_id").matches(Regex("[0-9a-f]{64}"))) { "Invalid engine identity" }
            check(value.getLong("created_ms") > 0 && value.getLong("updated_ms") > 0) { "Invalid session timestamp" }
            check(value.has("mutation_intent")) { "Session mutation state is missing" }
            value.getBoolean("normal_verified")
            value.getBoolean("packages_dirty")
            val committed = value.getJSONArray("committed_files")
            check(committed.length() <= 8192) { "Too many committed files" }
            for (index in 0 until committed.length()) GameFilePolicy.validate(committed.getString(index), writable = true)
            val result = SessionJournal(directory, value)
            if (result.hasMutationIntent) {
                val intent = value.getJSONObject("mutation_intent")
                check(intent.getString("operation") in setOf("install_access", "install_normal", "first_uninstall",
                    "first_install", "write_file", "delete_file", "clear_watchdog", "rollback_file", "restore_watchdog")) { "Unknown stored mutation" }
                intent.getJSONObject("detail")
            }
            if (result.phase in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) {
                check(value.getBoolean("normal_verified") && !result.dirtyPackages &&
                    !result.hasMutationIntent && !result.hasRecoveryNormalIntent) { "Terminal session recovery is unresolved" }
            }
            return result
        }

        fun history(parent: File): List<SessionJournal> = parent.listFiles().orEmpty()
            .filter { it.isDirectory || Files.isSymbolicLink(it.toPath()) }.filter {
                if (it.name.startsWith(INITIALIZING)) {
                    GameFilePolicy.session(it.name.removePrefix(INITIALIZING))
                    false // An unpublished draft cannot have authorized a device mutation.
                } else { GameFilePolicy.session(it.name); true }
            }.map { load(it) }

        fun pending(parent: File): List<SessionJournal> = history(parent)
            .filter { it.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED) }
    }
}
