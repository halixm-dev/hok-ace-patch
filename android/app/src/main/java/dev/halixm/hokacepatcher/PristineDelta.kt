package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/**
 * Where the Android patcher keeps its pristine delta. The delta is made and applied by the engine
 * (`tools/pristine_delta.py` through `android_bridge`); this side only names the files and reports.
 */
object PristineDelta {
    /** In a session: the build input's rebuilt pristine files, deleted once the build is done. */
    const val BUILD_COPY = "pristine"
    /** In a session: the delta of the install it stages, promoted once that install is complete. */
    const val SESSION_DELTA = "pristine-delta.bin"

    fun directory(context: Context) = File(RunStore.privateRoot(context), "pristine")

    /** Whether a translated phone can be repatched without clearing the game's data. */
    fun held(context: Context) = File(directory(context), "delta.bin").isFile

    /** Beside a schema-2 build attempt, outside its immutable receipt-hashed result. */
    const val FINALIZATION_PLAN = "finalization-plan.json"

    /**
     * Seal what finalizing [journal]'s current build will do, from <plan> (`finalization_plan`, decided by
     * the engine while it is available at STAGED). Called before any game file is written.
     */
    fun seal(context: Context, journal: SessionJournal, plan: JSONObject) {
        val root = journal.resultRoot
        val attempt = checkNotNull(root.parentFile)
        check(root != journal.directory) { "Only an owned build attempt can be sealed" }
        val remove = journal.snapshot().optBoolean("remove", false)
        check(plan.getInt("schema") == 1 && plan.getBoolean("remove") == remove) { "Finalization plan differs from the run" }
        check(plan.getString("delta_sha256") == ApkIdentity.digest(File(root, SESSION_DELTA))) { "Finalization plan delta differs" }
        val hashes = plan.getJSONArray("staged_hashes")
        check(hashes.length() <= 65536 && (0 until hashes.length()).all { HASH.matches(hashes.getString(it)) })
        check(!remove || hashes.length() == 0) { "Remove records no translated bytes" }
        check(plan.isNull("redownload_done") || plan.get("redownload_done") is JSONObject) { "Invalid Re-download claim" }
        val bytes = ArtifactReceipts.canonical(plan).toByteArray(Charsets.UTF_8)
        atomic(File(attempt, FINALIZATION_PLAN), bytes)
        val old = activeIdentity(context)
        journal.snapshot().optJSONObject("build_identity")?.getJSONObject("delta")?.getJSONObject("files")?.let { inputs ->
            for ((file, field) in listOf("delta.bin" to "delta", "staged-hashes.json" to "record",
                    "restore-refused.json" to "restore_refused", "redownload.json" to "redownload"))
                check(same(inputs.get(file), old.get(field))) { "Finalization input changed after build: $file" }
        }
        val all = sortedSetOf<String>()
        val keptRecord = File(directory(context), "staged-hashes.json")
        if (present(keptRecord)) {
            val prior = ArtifactReceipts.parse(DurableFiles.readCommitted(keptRecord))
            check(prior.getInt("schema") == 1)
            val entries = prior.getJSONArray("sha256"); check(entries.length() <= 65536)
            for (i in 0 until entries.length()) all += entries.getString(i)
        }
        for (i in 0 until hashes.length()) all += hashes.getString(i)
        check(all.size <= 65536 && all.all { HASH.matches(it) })
        val finalRecord = ArtifactReceipts.canonical(JSONObject().put("schema", 1).put("sha256", JSONArray(all.toList())))
            .toByteArray(Charsets.UTF_8)
        check(same(old, activeIdentity(context))) { "Active pristine knowledge changed while sealing" }
        atomic(File(attempt, "sealed-final-record.json"), finalRecord)
        journal.record(JSONObject().put("sealed_delta", ApkIdentity.digest(File(root, SESSION_DELTA)))
            .put("sealed_hashes", ApkIdentity.digest(File(root, "staged-hashes.json")))
            .put("sealed_active", old).put("sealed_record", ArtifactReceipts.digest(finalRecord))
            .put("finalization_plan", ArtifactReceipts.digest(bytes)))
    }

    /**
     * Byte-only idempotent finalization: no Python, codec or newer engine after payload verification, so a
     * kill after normal restoration finishes here without a rebuild. Exactly `keep_delta`'s effect: the
     * plan's translated hashes join the kept record, then the session delta becomes the kept delta (Remove
     * deletes it). The prior kept files are copied beside the attempt before either changes. An unconfirmed
     * closure also finalizes: its delta still names the pristine bytes it overwrote, and each entry applies
     * only to a file still at its staged hash. That is pristine knowledge, never a success receipt.
     * Last, a kept Re-download record the build read with every package back (the plan's
     * `redownload_done`) is dropped, only while it holds exactly the sealed bytes; the build never drops it.
     */
    fun finalize(context: Context, journal: SessionJournal) {
        val saved = journal.snapshot()
        check(journal.runId != null && journal.payloadVerified && !journal.dirtyPackages && !journal.hasMutationIntent &&
            saved.optBoolean("normal_verified", false)) { "Finalization needs a verified payload and normal APK" }
        val root = journal.resultRoot
        check(root != journal.directory) { "Finalization needs an owned build attempt" }
        val attempt = checkNotNull(root.parentFile)
        val delta = File(root, SESSION_DELTA)
        val hashes = File(root, "staged-hashes.json")
        val planFile = File(attempt, FINALIZATION_PLAN)
        RunStore.safe(context.filesDir.canonicalFile, planFile)
        val planBytes = DurableFiles.readCommitted(planFile)
        check(ArtifactReceipts.digest(planBytes) == saved.getString("finalization_plan") &&
            ApkIdentity.digest(delta) == saved.getString("sealed_delta") &&
            ApkIdentity.digest(hashes) == saved.getString("sealed_hashes")) { "Finalization material changed" }
        val plan = ArtifactReceipts.parse(planBytes)
        val remove = saved.optBoolean("remove", false)
        check(plan.getBoolean("remove") == remove && plan.getString("delta_sha256") == saved.getString("sealed_delta"))
        val keep = directory(context)
        DurableFiles.createDirectories(keep)
        RunStore.safe(context.filesDir.canonicalFile, keep, true)
        val record = File(keep, "staged-hashes.json")
        val active = File(keep, "delta.bin")
        val intentFile = File(attempt, "finalization/intent.json")
        if (!saved.optBoolean("finalization_pending", false) && !saved.optBoolean("finalized", false)) {
            check(same(activeIdentity(context), saved.getJSONObject("sealed_active"))) {
                "Active pristine knowledge changed after staging"
            }
            // Keep both prior records pinned beside this attempt before changing either active file.
            val previous = File(attempt, "finalization")
            DurableFiles.createDirectories(previous)
            for (old in listOf(active, record)) {
                val backup = File(previous, "previous-${old.name}")
                if (present(old)) {
                    ArtifactReceipts.safe(File(old.path + ".bak").takeIf { it.exists() } ?: old)
                    if (backup.exists()) check(same(identity(backup), identity(old))) { "Previous finalization backup differs" }
                    else atomic(backup, DurableFiles.readCommitted(old))
                } else check(!backup.exists()) { "Unexpected previous finalization backup" }
            }
            val all = sortedSetOf<String>()
            if (present(record)) {
                val prior = ArtifactReceipts.parse(DurableFiles.readCommitted(record))
                check(prior.getInt("schema") == 1)
                val entries = prior.getJSONArray("sha256"); check(entries.length() <= 65536)
                for (i in 0 until entries.length()) all += entries.getString(i)
            }
            val added = plan.getJSONArray("staged_hashes")
            for (i in 0 until added.length()) all += added.getString(i)
            check(all.size <= 65536 && all.all { HASH.matches(it) })
            val finalRecord = ArtifactReceipts.canonical(JSONObject().put("schema", 1).put("sha256", JSONArray(all.toList())))
                .toByteArray(Charsets.UTF_8)
            check(ArtifactReceipts.digest(finalRecord) == saved.getString("sealed_record") &&
                ArtifactReceipts.digest(DurableFiles.readCommitted(File(attempt, "sealed-final-record.json"))) == saved.getString("sealed_record"))
            val intent = JSONObject().put("schema", 1).put("plan", saved.getString("finalization_plan"))
                .put("old_delta", identity(active)).put("old_record", identity(record))
                .put("final_delta", if (remove || plan.getInt("files") == 0) JSONObject.NULL else identity(delta))
                .put("final_record", JSONObject().put("size", finalRecord.size).put("sha256", ArtifactReceipts.digest(finalRecord)))
            if (intentFile.exists()) check(ArtifactReceipts.canonical(ArtifactReceipts.parse(DurableFiles.readCommitted(intentFile))) ==
                ArtifactReceipts.canonical(intent)) { "Uncommitted finalization intent differs" }
            else atomic(intentFile, ArtifactReceipts.canonical(intent).toByteArray(Charsets.UTF_8))
            atomic(File(previous, "final-staged-hashes.json"), finalRecord)
            journal.record(JSONObject().put("finalization_pending", true).put("finalized", false)
                .put("finalization_intent", ApkIdentity.digest(intentFile)))
        }
        // Never merge the active record on restart: only the sealed old -> record -> delta order is justified.
        check(ApkIdentity.digest(intentFile) == journal.snapshot().getString("finalization_intent")) { "Finalization intent changed" }
        val intent = ArtifactReceipts.parse(DurableFiles.readCommitted(intentFile))
        check(intent.getInt("schema") == 1 && intent.getString("plan") == saved.getString("finalization_plan"))
        val sealed = saved.getJSONObject("sealed_active")
        check(same(intent.get("old_delta"), sealed.get("delta")) && same(intent.get("old_record"), sealed.get("record")))
        val classification = activeIdentity(context)
        // The build read the sealed Re-download record with every package back (`redownload_done`); this
        // finalization drops exactly those bytes, so after a cut it may already be gone.
        val dropsRedownload = !plan.isNull("redownload_done") && !sealed.isNull("redownload") &&
            same(plan.get("redownload_done"), sealed.get("redownload"))
        check(same(classification.get("redownload"), sealed.get("redownload")) ||
            (dropsRedownload && classification.isNull("redownload"))) { "Re-download knowledge changed" }
        check(same(classification.get("restore_refused"), sealed.get("restore_refused")) ||
            classification.isNull("restore_refused")) { "Restore refusal knowledge changed" }
        for ((name, key) in listOf("delta.bin" to "old_delta", "staged-hashes.json" to "old_record")) {
            check(same(identity(File(attempt, "finalization/previous-$name")), intent.get(key))) { "Finalization backup changed" }
        }
        val finalRecord = File(attempt, "finalization/final-staged-hashes.json")
        check(same(identity(finalRecord), intent.get("final_record"))) { "Final staged-hash record changed" }
        val oldPair = same(identity(active), intent.get("old_delta")) && same(identity(record), intent.get("old_record"))
        val intermediate = same(identity(active), intent.get("old_delta")) && same(identity(record), intent.get("final_record"))
        val finalPair = same(identity(active), intent.get("final_delta")) && same(identity(record), intent.get("final_record"))
        check(!classification.isNull("restore_refused") || sealed.isNull("restore_refused") || finalPair) {
            "Refusal deletion precedes required metadata promotion"
        }
        check(if (saved.optBoolean("finalized", false)) finalPair else oldPair || intermediate || finalPair) {
            "Active pristine knowledge differs from the sealed finalization states"
        }
        if (saved.optBoolean("finalized", false) && !saved.optBoolean("finalization_pending", false)) {
            check(classification.isNull("restore_refused")) { "New refusal record after finalization" }
            return
        }
        atomic(record, DurableFiles.readCommitted(finalRecord))
        if (remove || plan.getInt("files") == 0) {
            for (file in listOf(active, File(active.path + ".bak"))) if (file.exists()) {
                RunStore.safe(keep, file); check(file.delete()); DurableFiles.syncDirectory(keep)
            }
        } else atomic(active, delta.readBytes())
        check(same(identity(active), intent.get("final_delta")) && same(identity(record), intent.get("final_record"))) {
            "Kept pristine delta read-back differs"
        }
        val refused = File(keep, "restore-refused.json")
        check(same(identity(refused), sealed.get("restore_refused")) || identity(refused) == JSONObject.NULL)
        for (file in listOf(refused, File(refused.path + ".bak"))) if (file.exists()) {
            RunStore.safe(keep, file); check(file.delete()); DurableFiles.syncDirectory(keep)
        }
        check(activeIdentity(context).isNull("restore_refused"))
        if (dropsRedownload) {
            val marker = File(keep, "redownload.json")
            check(same(identity(marker), sealed.get("redownload")) || identity(marker) == JSONObject.NULL) {
                "Re-download knowledge changed"
            }
            for (file in listOf(marker, File(marker.path + ".bak"))) if (file.exists()) {
                RunStore.safe(keep, file); check(file.delete()); DurableFiles.syncDirectory(keep)
            }
            check(activeIdentity(context).isNull("redownload"))
        }
        journal.record(JSONObject().put("finalized", true).put("finalization_pending", false))
    }

    private val HASH = Regex("[0-9a-f]{64}")
    private fun present(file: File) = file.exists() || File(file.path + ".bak").exists()

    private fun identity(file: File): Any {
        var path: java.nio.file.Path? = file.toPath().toAbsolutePath().normalize()
        while (path != null) { check(!java.nio.file.Files.isSymbolicLink(path)); path = path.parent }
        val committed = File(file.path + ".bak").takeIf { it.exists() } ?: file
        return if (committed.exists()) ArtifactReceipts.fileIdentity(committed) else JSONObject.NULL
    }

    private fun same(left: Any, right: Any) = ArtifactReceipts.canonical(left) == ArtifactReceipts.canonical(right)

    /** Fresh hashes (and explicit absence), also usable without loading the translation engine. */
    fun activeIdentity(context: Context): JSONObject = JSONObject().put("delta", identity(File(directory(context), "delta.bin")))
        .put("record", identity(File(directory(context), "staged-hashes.json")))
        .put("restore_refused", identity(File(directory(context), "restore-refused.json")))
        .put("redownload", identity(File(directory(context), "redownload.json")))

    private fun atomic(file: File, bytes: ByteArray) {
        check(checkNotNull(file.parentFile).isDirectory && !java.nio.file.Files.isSymbolicLink(file.parentFile!!.toPath()))
        for (name in listOf(file.name, file.name + ".bak", file.name + ".new")) {
            val candidate = File(file.parentFile, name)
            check(!java.nio.file.Files.isSymbolicLink(candidate.toPath()))
        }
        val storage = android.util.AtomicFile(file)
        val stream = storage.startWrite()
        try { stream.write(bytes); stream.fd.sync(); storage.finishWrite(stream); DurableFiles.syncDirectory(checkNotNull(file.parentFile)) }
        catch (error: Throwable) { storage.failWrite(stream); throw error }
        check(DurableFiles.readCommitted(file).contentEquals(bytes))
    }

    /** Log lines for `build_snapshot`'s `pristine` report. */
    fun describe(pristine: JSONObject): List<String> {
        if (pristine.optString("mode") == "removed") {
            return listOfNotNull("Restoring ${pristine.optInt("rebuilt")} original game files", assetsRestored(pristine))
        }
        if (pristine.optString("mode") != "rebuilt") {
            val stale = pristine.optInt("stale")
            return listOf(if (stale > 0) {
                "The kept pristine delta no longer matches $stale file(s); built from the game files as they are"
            } else "No pristine delta for this phone: built from the game files as they are")
        }
        val lines = mutableListOf("Rebuilt ${pristine.optInt("rebuilt")} files from the pristine delta")
        val replaced = pristine.optJSONArray("replaced")
        if (replaced != null && replaced.length() > 0) {
            lines += "${replaced.length()} file(s) the game update replaced hold none of this patcher's translation; built from them as the update left them"
        }
        val restored = pristine.optJSONArray("restored")
        if (restored != null && restored.length() > 0) {
            lines += "${restored.length()} file(s) this build leaves untranslated go back to their original bytes"
        }
        assetsRestored(pristine)?.let { lines += it }
        return lines
    }

    /** The packages asset restore (ADR 0008) wrote original bytes back into, or null when none. */
    private fun assetsRestored(pristine: JSONObject): String? {
        val packages = pristine.optJSONArray("assets_restored") ?: return null
        if (packages.length() == 0) return null
        val names = (0 until packages.length()).joinToString(", ") { packages.getString(it) }
        return "Wrote the original bytes back into package $names, which a game update kept partly translated"
    }
}
