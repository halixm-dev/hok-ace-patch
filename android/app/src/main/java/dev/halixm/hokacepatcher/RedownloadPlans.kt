package dev.halixm.hokacepatcher

import android.content.Context
import android.util.AtomicFile
import dev.halixm.hokacepatcher.PatchCoordinator.Companion.REDOWNLOAD_CONSENT
import dev.halixm.hokacepatcher.PatchCoordinator.Companion.REDOWNLOAD_CONSEQUENCES
import dev.halixm.hokacepatcher.PatchCoordinator.RunApks
import dev.halixm.hokacepatcher.PatchCoordinator.WaitingForUser
import java.io.File
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

/**
 * A Re-download plan's bookkeeping (ticket 12): measure and bind it, pin and offer it, read its approval, and
 * check that a pinned plan still holds. Moved verbatim out of [PatchCoordinator], whose stages decide when
 * each runs (`redownloadStage`, `waitingStep`, `awaitUser`); no game file changes here.
 */
internal class RedownloadPlans(
    private val context: Context,
    /** The coordinator's pristine folder (the kept delta and its records). */
    private val pristine: File,
    private val report: (String) -> Unit,
    private val engine: (String, Array<out Any>) -> String,
) {
    private companion object {
        /** `android_bridge.REDOWNLOAD_NAME` and `RESTORE_REFUSED_NAME`: the kept records a plan binds. */
        private const val REDOWNLOAD_RECORD = "redownload.json"
        private const val RESTORE_REFUSED_RECORD = "restore-refused.json"
    }

    private fun bridge(name: String, vararg arguments: Any): String = engine(name, arguments)

    /**
     * Measure the exact Re-download scope from this session's verified snapshot into a fresh plan folder and
     * bind it (ticket 12): run, session, action and target, the snapshot manifest, the kept delta and its
     * records, engine and producer, the run's APKs, every file deleted with its hash and size, the Watchdog
     * files cleared, and [REDOWNLOAD_CONSEQUENCES]. No game file changes. An approval names the plan's digest
     * ([ArtifactReceipts.identityKey] of `plan.json`). The staged list that the deletions and their rollback
     * read must be exactly the plan's files at their snapshot hashes. Returns the plan's id and content.
     */
    fun planRedownload(journal: SessionJournal, apks: RunApks, enginePath: String,
                               run: RunStore.Run, manifest: File): Pair<String, JSONObject> {
        val parent = File(journal.directory, "redownload-plans")
        DurableFiles.createDirectories(parent)
        RunStore.safe(context.filesDir.canonicalFile, parent, true)
        val id = UUID.randomUUID().toString()
        val folder = File(parent, id)
        val measured = JSONObject(bridge("redownload_plan", enginePath, journal.directory.path, pristine.path,
            folder.path))
        val plan = JSONObject().put("schema", 1).put("kind", "redownload")
            .put("run_id", run.id).put("session_id", journal.id).put("authorization_key", run.authorizationKey)
            .put("action", run.action).put("target", run.target.json().put("provider", run.provider.key))
            .put("snapshot_manifest_sha256", ApkIdentity.digest(manifest))
            .put("engine_id", File(enginePath).name).put("producer_key", producerKey())
            .put("apks", apkBinding(apks))
            .put("delta", measured.opt("delta") ?: JSONObject.NULL).put("records", measured.getJSONObject("records"))
            .put("packages", measured.getJSONObject("packages")).put("files", measured.getJSONObject("files"))
            .put("watchdog", JSONObject().put("change", "clear").put("files", measured.getJSONObject("watchdog")))
            .put("consequences", JSONArray(REDOWNLOAD_CONSEQUENCES))
        requirePlanScope(folder, plan, manifest)
        writeRecord(File(folder, "plan.json"), ArtifactReceipts.canonical(plan).toByteArray(Charsets.UTF_8))
        return id to plan
    }

    private fun producerKey(): Any =
        EngineAssets.producerIdentity(context)?.let { ArtifactReceipts.identityKey(it) } ?: JSONObject.NULL

    private fun apkBinding(apks: RunApks) = JSONObject().put("recovery_id", apks.recoveryId).put("root", apks.root)
        .put("access_sha256", apks.access?.sha256 ?: JSONObject.NULL)

    /**
     * The plan's files are exactly its staged list, at the snapshot manifest's hashes and sizes; its Watchdog
     * files are exactly the manifest's; its packages are the packages the files belong to.
     */
    private fun requirePlanScope(folder: File, plan: JSONObject, manifest: File) {
        val entries = ArtifactReceipts.parse(manifest.readBytes()).getJSONObject("files")
        val files = plan.getJSONObject("files")
        check(files.length() in 1..8192) { "Unsupported Re-download file count" }
        val stagedFile = File(folder, "staged-hashes.json")
        RunStore.safe(context.filesDir.canonicalFile, stagedFile)
        check(stagedFile.length() in 1..(1024 * 1024)) { "Invalid Re-download staged list" }
        val staged = ArtifactReceipts.parse(stagedFile.readBytes())
        check(staged.keys().asSequence().map { "packages/$it" }.toSet() == files.keys().asSequence().toSet()) {
            "The Re-download staged list differs from its plan"
        }
        val owners = mutableSetOf<String>()
        for (name in staged.keys()) {
            val relative = "packages/$name"
            GameFilePolicy.validate(relative, writable = true)
            val entry = files.getJSONObject(relative)
            val live = entries.getJSONObject(relative)
            check(staged.getString(name) == entry.getString("sha256") && entry.getString("sha256") == live.getString("sha256") &&
                entry.getLong("bytes") == live.getLong("bytes")) { "The Re-download plan differs from the snapshot: $name" }
            owners += name.substringBefore('/')
        }
        val packages = plan.getJSONObject("packages").keys().asSequence().toSet()
        check(packages.size in 1..1024 && packages.all { it.matches(Regex("[0-9]{1,20}")) } && packages == owners) {
            "Unsupported Re-download packages"
        }
        val watchdog = plan.getJSONObject("watchdog").getJSONObject("files")
        val expected = entries.keys().asSequence().filter { it.startsWith("Watchdog/") }.toSet()
        check(watchdog.keys().asSequence().toSet() == expected && expected.all {
            watchdog.getJSONObject(it).getString("sha256") == entries.getJSONObject(it).getString("sha256")
        }) { "The Re-download Watchdog differs from the snapshot" }
    }

    /** Atomic, fsynced, read back: a plan an approval names is never half-written. */
    private fun writeRecord(file: File, bytes: ByteArray) {
        val storage = AtomicFile(file)
        val stream = storage.startWrite()
        try {
            stream.write(bytes)
            stream.fd.sync()
            storage.finishWrite(stream)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
        DurableFiles.syncDirectory(checkNotNull(file.parentFile))
        check(DurableFiles.readCommitted(file).contentEquals(bytes)) { "Re-download plan read-back differs" }
    }

    /** The pinned plan ([SessionJournal.redownloadPlanRoot]), read back and checked against its saved digest. */
    fun savedPlan(journal: SessionJournal): Pair<String, JSONObject>? {
        val saved = journal.snapshot()
        val id = saved.optString("redownload_plan").takeIf { it.isNotEmpty() } ?: return null
        GameFilePolicy.session(id)
        val file = File(checkNotNull(journal.redownloadPlanRoot), "plan.json")
        RunStore.safe(context.filesDir.canonicalFile, file)
        val plan = ArtifactReceipts.parse(DurableFiles.readCommitted(file))
        check(ArtifactReceipts.identityKey(plan) == saved.getString("redownload_plan_sha256")) {
            "The saved Re-download plan changed"
        }
        check(plan.getString("run_id") == journal.runId && plan.getString("session_id") == journal.id &&
            plan.getString("authorization_key") == journal.authorizationKey) {
            "The Re-download plan belongs to another action"
        }
        return id to plan
    }

    /**
     * Pin <plan> in the journal first (with the consent wait when <waiting>), then offer it in the run record,
     * which approves it automatically in the same write unless the loop guard holds it back (user decision
     * 2026-11-13). The run record keeps an answer only for the same digest ([RunStore.proposeRedownload]).
     */
    fun pinRedownload(journal: SessionJournal, run: RunStore.Run, id: String, plan: JSONObject,
                              waiting: Boolean) {
        val updates = JSONObject().put("redownload_plan", id)
            .put("redownload_plan_sha256", ArtifactReceipts.identityKey(plan)).put("build_attempt", "")
        if (waiting) updates.put("waiting_reason", REDOWNLOAD_CONSENT)
        journal.record(updates)
        offerRedownload(run, id, plan)
    }

    fun offerRedownload(run: RunStore.Run, id: String, plan: JSONObject) {
        val files = plan.getJSONObject("files")
        val bytes = files.keys().asSequence().sumOf { files.getJSONObject(it).getLong("bytes") }
        val packages = plan.getJSONObject("packages").keys().asSequence().sortedBy { it.toBigInteger() }.toList()
        RunStore(context).proposeRedownload(run.id, id, ArtifactReceipts.identityKey(plan), files.length(),
            packages, bytes, automatic = true)
    }

    /** The run record's approval of exactly <plan>, or null when the loop guard left it for the user's review. */
    fun approvedPlan(run: RunStore.Run, plan: JSONObject): Redownload? =
        RunStore(context).load(run.id).redownload?.takeIf { it.approved && it.planSha256 == ArtifactReceipts.identityKey(plan) }

    /** Why the loop guard held <plan> back, reported before the action waits for the user's review. */
    fun heldBack(run: RunStore.Run, plan: JSONObject): WaitingForUser {
        val saved = RunStore(context).load(run.id)
        val again = plan.getJSONObject("packages").keys().asSequence()
            .filter { it in saved.redownloadedPackages }.sortedBy { it.toBigInteger() }.toList()
        val message = when {
            again.isNotEmpty() -> "Package ${again.joinToString(", ")} is still damaged after its Re-download in " +
                "this run; it is not deleted again without your review"
            saved.attempts.optInt(RedownloadConsent.DELETE_OPERATION, 0) >= 2 ->
                "The Re-download was interrupted twice; it is not deleted again without your review"
            else -> "The Re-download waits for your review; nothing was deleted"
        }
        report(message)
        return WaitingForUser(message)
    }

    /**
     * Whether the pinned, approved <plan> is still exactly what planning would measure now: the same run,
     * snapshot manifest (the live layer was just validated against it), engine, producer, APKs, kept delta and
     * records, and every file at its planned hash. The one change allowed is this plan's own record, after an
     * interrupted deletion of the same plan (<deleting>): `keep_redownload` wrote the record the journal saved
     * and dropped the restore-refused record; the rollback put every file back.
     */
    fun pinnedPlanHolds(journal: SessionJournal, plan: JSONObject, apks: RunApks, enginePath: String,
                                run: RunStore.Run, manifest: File, deleting: Boolean): Boolean = runCatching {
        val bound = plan.getString("action") == run.action &&
            ArtifactReceipts.canonical(plan.getJSONObject("target")) ==
                ArtifactReceipts.canonical(run.target.json().put("provider", run.provider.key)) &&
            plan.getString("snapshot_manifest_sha256") == ApkIdentity.digest(manifest) &&
            plan.getString("engine_id") == File(enginePath).name &&
            ArtifactReceipts.canonical(plan.get("producer_key")) == ArtifactReceipts.canonical(producerKey()) &&
            ArtifactReceipts.canonical(plan.getJSONObject("apks")) == ArtifactReceipts.canonical(apkBinding(apks)) &&
            ArtifactReceipts.canonical(plan.getJSONArray("consequences")) ==
                ArtifactReceipts.canonical(JSONArray(REDOWNLOAD_CONSEQUENCES))
        if (!bound) return@runCatching false
        requirePlanScope(checkNotNull(journal.redownloadPlanRoot), plan, manifest)
        val evidence = JSONObject(bridge("redownload_evidence", enginePath, pristine.path))
        if (ArtifactReceipts.canonical(evidence.opt("delta")) != ArtifactReceipts.canonical(plan.opt("delta"))) {
            return@runCatching false
        }
        val records = ArtifactReceipts.canonical(evidence.getJSONObject("records"))
        if (records == ArtifactReceipts.canonical(plan.getJSONObject("records"))) return@runCatching true
        val kept = journal.snapshot().optJSONObject("redownload_kept")
        deleting && kept != null && kept.optString("plan_sha256") == ArtifactReceipts.identityKey(plan) &&
            records == ArtifactReceipts.canonical(JSONObject().put(REDOWNLOAD_RECORD, kept.getJSONObject("record"))
                .put(RESTORE_REFUSED_RECORD, JSONObject.NULL))
    }.getOrElse { report("The saved Re-download plan no longer reads (${it.javaClass.simpleName})"); false }
}
