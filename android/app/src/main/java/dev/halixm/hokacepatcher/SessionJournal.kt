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
    /** Schema 1 is safety-only history; only schema 2 carries linked ordinary Start authority. */
    val runId: String? get() = if (value.getInt("schema") == 2) value.getString("run_id") else null
    val authorizationKey: String? get() = if (value.getInt("schema") == 2) value.getString("authorization_key") else null
    val phase: PatchPhase get() = PatchPhase.valueOf(value.getString("phase"))
    val hasMutationIntent: Boolean get() = !value.isNull("mutation_intent")
    val hasRecoveryNormalIntent: Boolean get() = !value.isNull("recovery_normal_intent")
    val dirtyPackages: Boolean get() = value.optBoolean("packages_dirty", false)
    val recoveryId: String get() = value.getString("recovery_id")
    /**
     * Under root (ADR 0007): the installed game app the run leaves in place, whose sha256 is [recoveryId].
     * Null on the shell path, whose [recoveryId] is the saved normal APK.
     */
    val rootInstalled: ApkIdentity? get() = value.optJSONObject("root_installed")?.let { ApkIdentity.fromJson(it) }
    val root: Boolean get() = value.has("root_installed")
    /** The run wrote and verified its whole payload, so its pristine delta describes what it overwrote. */
    val payloadVerified: Boolean get() = value.optBoolean("patch_payload_verified", false)
    /** Closed with its payload written but the game files not checked again; see [closeUnconfirmed]. */
    val layerUnconfirmed: Boolean get() = phase == PatchPhase.CANCELLED && value.optString("layer_unconfirmed").isNotEmpty()
    val recoveryCompletionPhase: PatchPhase get() =
        if (!dirtyPackages && payloadVerified) PatchPhase.COMPLETE
        else PatchPhase.CANCELLED

    @Synchronized fun snapshot(): JSONObject = JSONObject(value.toString())

    /**
     * Attempt paths are derived from a validated UUID, never accepted from bridge JSON. With no build attempt
     * pinned, an approved Re-download's plan folder (`redownload_plan`) holds the staged list its deletions and
     * their rollback read.
     */
    val resultRoot: File get() = snapshot().optString("build_attempt").takeIf { it.isNotEmpty() }?.let {
        GameFilePolicy.session(it)
        File(directory, "build-attempts/$it/result").also { result ->
            RunStore.safe(directory, result, true)
        }
    } ?: redownloadPlanRoot ?: directory

    /** The pinned Re-download plan's folder, or null. */
    val redownloadPlanRoot: File? get() = snapshot().optString("redownload_plan").takeIf { it.isNotEmpty() }?.let {
        GameFilePolicy.session(it)
        File(directory, "redownload-plans/$it").also { plan -> RunStore.safe(directory, plan, true) }
    }

    /** Persist non-mutation checkpoint ownership before transport, rename or finalization. */
    @Synchronized fun record(updates: JSONObject) {
        check(runId != null) { "Legacy journals carry no continuation checkpoints" }
        check(updates.keys().asSequence().all { it in RECORD_KEYS }) { "Unknown checkpoint record" }
        for (key in updates.keys()) value.put(key, updates.get(key))
        persist()
    }

    /** Why this run waits for the user rather than continuing automatically, or null. */
    val waitingReason: String? get() = value.optString("waiting_reason").takeIf { it.isNotEmpty() && it != "null" }

    /**
     * Re-enter only a clean, correlated continuation; this never creates authorization. A closed
     * `recovered_unconfirmed` payload stays in history and never becomes this run's success: the new
     * attempt must write and verify a fresh payload, and finalize it again.
     */
    @Synchronized fun resumeConsistent() {
        check(runId != null && !dirtyPackages && !hasMutationIntent && !hasRecoveryNormalIntent) {
            "Only a consistent linked run can continue"
        }
        check(phase in setOf(PatchPhase.PREPARED, PatchPhase.SNAPSHOT_ACCESS_INSTALLED, PatchPhase.SNAPSHOT_READY,
                PatchPhase.BUILDING, PatchPhase.STAGED, PatchPhase.APPLYING, PatchPhase.CANCELLED, PatchPhase.RESTORING,
                PatchPhase.RECOVERY_REQUIRED)) {
            "Continuation needs a consistent run"
        }
        check(!value.optBoolean("finalization_pending", false)) { "Finish pristine delta finalization first" }
        check(!value.optBoolean("stopped", false)) { "A stopped run never continues" }
        check(!payloadVerified || layerUnconfirmed) { "A verified payload finishes forward, not again" }
        if (layerUnconfirmed) {
            val history = value.optJSONArray("unconfirmed_history") ?: JSONArray()
            check(history.length() < 64) { "Too many unconfirmed results" }
            history.put(JSONObject().put("reason", value.getString("layer_unconfirmed"))
                .put("build_attempt", value.opt("build_attempt") ?: JSONObject.NULL))
            value.put("unconfirmed_history", history).remove("layer_unconfirmed")
        }
        value.put("attempted_files", JSONArray()).put("committed_files", JSONArray()).put("watchdog_touched", false)
        value.put("patch_payload_verified", false).put("finalized", false).put("final_normal_verified", false)
            .put("continuations", value.optInt("continuations", 0) + 1)
        value.put("phase", PatchPhase.PREPARED.name)
        persist()
    }

    /**
     * Resolve an install intent whose reply was lost, from the installed identity the caller audited
     * (<installedSha256>, or null when it matches neither APK). The intent never proves either outcome.
     */
    @Synchronized fun reconcileInstall(installedSha256: String?) {
        check(hasMutationIntent && !dirtyPackages)
        val intent = value.getJSONObject("mutation_intent")
        check(intent.getString("operation") in setOf("install_access", "install_normal")) { "Not an install intent" }
        val expected = intent.getJSONObject("detail").optString("sha256")
        value.put("install_audit", JSONObject().put("operation", intent.getString("operation"))
            .put("expected", expected).put("installed", installedSha256 ?: JSONObject.NULL))
            .put("mutation_intent", JSONObject.NULL)
        if (intent.getString("operation") == "install_normal") value.put("normal_verified", installedSha256 == expected)
        persist()
    }

    /** Recovery results use retained counters; loading a new Python engine is unnecessary. */
    @Synchronized fun terminalResult(): JSONObject {
        check(phase in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED) &&
            value.optBoolean("normal_verified", false) && !dirtyPackages && !hasMutationIntent && !hasRecoveryNormalIntent) {
            "Recovery result requires a resolved session and verified normal APK"
        }
        val status = when {
            phase == PatchPhase.COMPLETE -> "complete"
            value.optBoolean("stopped", false) -> "stopped_consistent"
            layerUnconfirmed -> "recovered_unconfirmed"
            else -> "recovered"
        }
        val result = JSONObject().put("status", status)
            .put("action", "recover").put("session", id).put("phase", phase.name)
        if (phase == PatchPhase.COMPLETE) {
            result.put("counts", value.opt("counts") ?: JSONObject.NULL)
            if (value.has("removed_count")) result.put("removed", value.getInt("removed_count"))
        }
        if (root) result.put("root", true)
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
        check(!Files.isSymbolicLink(directory.toPath()) && !Files.isSymbolicLink(checkNotNull(directory.parentFile).toPath())) { "Linked journal root" }
        for (name in listOf("journal.json", "journal.json.bak", "journal.json.new"))
            check(!Files.isSymbolicLink(File(directory, name).toPath())) { "Linked journal file" }
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
        if (operation in setOf("write_file", "delete_file", "rollback_file")) {
            val path = detail.getString("path"); GameFilePolicy.validate(path, writable = true)
            val attempted = value.optJSONArray("attempted_files") ?: JSONArray()
            if ((0 until attempted.length()).none { attempted.getString(it) == path }) {
                check(attempted.length() < 8192); attempted.put(path)
            }
            value.put("attempted_files", attempted)
        }
        if (operation in setOf("clear_watchdog", "restore_watchdog")) value.put("watchdog_touched", true)
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
            // A build refused over damaged files stays BUILDING as the same run plans their deletion.
            PatchPhase.BUILDING -> setOf(PatchPhase.BUILDING, PatchPhase.STAGED, PatchPhase.RESTORING, PatchPhase.CANCELLED)
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
        if (next == PatchPhase.COMPLETE && runId != null && payloadVerified) {
            check(value.optBoolean("finalized", false)) { "Pristine delta finalization is incomplete" }
        }
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
            check(name !in setOf("schema", "id", "recovery_id", "engine_id", "root_installed", "mutation_intent", "phase", "run_id", "authorization_key")) {
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
        check(!value.optBoolean("finalization_pending", false) &&
            !(runId != null && payloadVerified && !value.optBoolean("finalized", false))) {
            "Required pristine knowledge finalization remains unresolved"
        }
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
        /** Checkpoint fields [record] may change; identity, mutation and phase fields never pass here. */
        private val RECORD_KEYS = setOf("snapshot_attempt", "snapshot_rename", "snapshot_ready",
            "build_attempt", "build_identity", "sealed_delta", "sealed_hashes", "finalization_plan", "finalized",
            "finalization_pending", "finalization_intent", "sealed_active", "sealed_record", "waiting_reason", "counts", "remove", "removed_count", "retired_snapshots", RetiredSnapshots.RELEASED,
            "inputs_invalidated", "stopped", "build_storage_estimate", "build_storage_check", "storage_wait", "language",
            "redownload_plan", "redownload_plan_sha256", "redownloaded", "redownload_kept", "recovery_original_hash_passes", "completion_reuse")
        private const val INITIALIZING = ".creating-"
        private const val MAX_BYTES = 1024 * 1024
        /** <rootInstalled> marks a root run ([rootInstalled]); its sha256 must be <recoveryId>. */
        @JvmOverloads fun create(parent: File, recoveryId: String, engineId: String, rootInstalled: ApkIdentity? = null,
                                        runId: String? = null, authorizationKey: String? = null): SessionJournal {
            require(recoveryId.matches(Regex("[0-9a-f]{64}"))) { "Invalid recovery identity" }
            require(rootInstalled == null || rootInstalled.sha256 == recoveryId) { "Invalid root identity" }
            require(engineId.matches(Regex("[0-9a-f]{64}"))) { "Invalid engine identity" }
            check((runId == null) == (authorizationKey == null))
            runId?.let { GameFilePolicy.session(it) }
            authorizationKey?.let { check(it.matches(Regex("[0-9a-f]{64}"))) }
            val id = runId ?: UUID.randomUUID().toString()
            val directory = File(parent, id)
            val staging = File(parent, "$INITIALIZING$id")
            check(!directory.exists() && !Files.isSymbolicLink(directory.toPath())) { "Session already exists" }
            if (staging.exists() || Files.isSymbolicLink(staging.toPath())) {
                check(runId != null && !Files.isSymbolicLink(staging.toPath())) { "Unowned session draft" }
                // No device call is permitted until the final directory is published. Only the
                // owning stable UUID may restart this incomplete initial journal, including a cut
                // before startWrite/finishWrite. Foreign payloads or links force attention.
                check(staging.listFiles().orEmpty().all { it.name in setOf("journal.json", "journal.json.bak", "journal.json.new") &&
                    it.isFile && !Files.isSymbolicLink(it.toPath()) && it.length() <= MAX_BYTES })
                DurableFiles.deleteTree(staging)
            }
            val value = JSONObject().put("schema", if (runId == null) 1 else 2).put("id", id).put("recovery_id", recoveryId)
                .put("engine_id", engineId).put("phase", PatchPhase.PREPARED.name)
                .put("created_ms", System.currentTimeMillis()).put("normal_verified", false)
                .put("packages_dirty", false).put("mutation_intent", JSONObject.NULL)
                .put("committed_files", JSONArray())
            rootInstalled?.let { value.put("root_installed", it.json()) }
            runId?.let { value.put("run_id", it).put("authorization_key", authorizationKey) }
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
            val value = ArtifactReceipts.parse(bytes)
            check(value.opt("schema") in setOf(1L, 2L, 1, 2) && value.getString("id") == directory.name) { "Unsupported session journal" }
            if (value.getInt("schema") == 2) {
                check(value.get("run_id") is String && value.get("authorization_key") is String)
                check(value.get("normal_verified") is Boolean && value.get("packages_dirty") is Boolean)
                for (key in listOf("created_ms", "updated_ms")) check(value.get(key) is Int || value.get(key) is Long)
                check(value.getString("run_id") == directory.name)
                check(value.getString("authorization_key").matches(Regex("[0-9a-f]{64}")))
            } else check(!value.has("run_id") && !value.has("authorization_key")) { "Legacy journal cannot carry authorization" }
            check(value.getString("recovery_id").matches(Regex("[0-9a-f]{64}"))) { "Invalid recovery identity" }
            check(value.getString("engine_id").matches(Regex("[0-9a-f]{64}"))) { "Invalid engine identity" }
            check(value.getLong("created_ms") > 0 && value.getLong("updated_ms") > 0) { "Invalid session timestamp" }
            check(value.has("mutation_intent")) { "Session mutation state is missing" }
            value.getBoolean("normal_verified")
            value.getBoolean("packages_dirty")
            value.optJSONObject("root_installed")?.let {
                check(ApkIdentity.fromJson(it).sha256 == value.getString("recovery_id")) { "Invalid root identity" }
            }

            val committed = value.getJSONArray("committed_files")
            check(committed.length() <= 8192) { "Too many committed files" }
            for (index in 0 until committed.length()) GameFilePolicy.validate(committed.getString(index), writable = true)
            value.optJSONArray("attempted_files")?.let { attempted ->
                check(attempted.length() <= 8192)
                for (index in 0 until attempted.length()) {
                    check(attempted.get(index) is String)
                    GameFilePolicy.validate(attempted.getString(index), writable = true)
                }
            }
            if (value.has("attempted_files")) check(value.get("attempted_files") is JSONArray)
            if (value.has("watchdog_touched")) check(value.get("watchdog_touched") is Boolean)
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
