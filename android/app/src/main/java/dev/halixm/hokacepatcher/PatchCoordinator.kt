package dev.halixm.hokacepatcher

import android.content.Context
import android.os.DeadObjectException
import android.os.ParcelFileDescriptor
import android.util.AtomicFile
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.nio.file.Files
import java.util.UUID
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import org.json.JSONArray
import org.json.JSONObject

/**
 * Serialize snapshot/build/apply and recover complete file sets before restoring the normal APK.
 *
 * A durable Start (`RunStore`) owns one session whose checkpoints continue after an interruption:
 * a published snapshot and STAGED build are reused after their bytes and the live layer are checked
 * again, an unfinished snapshot or build restarts only that stage, an unfinished apply rolls back from
 * the verified originals first, and a verified payload finishes forward without a rebuild. Recovery of
 * saved bytes and APKs never needs the Python engine; only new snapshot/build work loads it.
 */
class PatchCoordinator @JvmOverloads constructor(
    private val context: Context,
    private val device: IPrivilegedDeviceService,
    private val report: (String) -> Unit,
    private val installedVerifier: InstalledApkVerifier? = null,
) {
    /** Injectable only in-process; the application always uses the independent installed verifier. */
    fun interface InstalledApkVerifier { fun verify(expected: ApkIdentity) }
    private val store = RecoveryStore(context)
    private val sessions = File(RunStore.privateRoot(context), "sessions")
    /** The pristine delta and the staged-hash record: outside sessions/, so no release reclaims them. */
    private val pristine = PristineDelta.directory(context)
    private val cancelled = AtomicBoolean(false)
    private val activeJournal = AtomicReference<SessionJournal?>(null)
    /** The claimed durable Start this call continues; set only inside [dispatch]. */
    private var authorizedRun: RunStore.Run? = null
    /** A completion source is still needed while its owned output copy is being adopted. */
    private val adoptingSessions = mutableSetOf<String>()

    fun cancel() { cancelled.set(true) }

    /** The saved action now waits for the user (an approval or the game's download): not a failure. */
    private class WaitingForUser(message: String) : IllegalStateException(message)

    /**
     * A build refusal over damaged files whose measured plan the coordinator just approved itself (user decision
     * 2026-11-13): the same run goes straight on to [redownloadStage] on the snapshot it already verified.
     */
    private class RedownloadApproved(val consent: Redownload) :
        IllegalStateException("Damaged game files found; Re-download approved automatically")

    companion object {
        /** `validateGameSnapshot`'s reasons for a layer the game itself changed. */
        private val GAME_CHANGED = listOf("Game file set changed", "Game file changed: ")
        /** Root's refusals the UI shows as they are. */

        const val ROOT_ACCESS_INSTALLED = "The installed game app is the patcher's temporary access build. " +
            "Recover the game app with the provider that patched it, then try again."
        const val OTHER_PROVIDER = "This interrupted run was started with another shell provider. " +
            "Choose that provider to recover it."
        /**
         * A pinned Re-download plan (ticket 12). Normally approved automatically at once, so a run cut here
         * resumes it without asking; it waits for the user's review only when the loop guard
         * ([RedownloadConsent.automaticAllowed]) holds it back.
         */
        const val REDOWNLOAD_CONSENT = "redownload_consent_required"
        /** The approved Re-download deleted its files; the saved action waits for the game to download them. */
        const val REDOWNLOAD_DOWNLOAD = "redownload_download_required"
        /** The game changed its files since the snapshot; the saved action waits for its downloads to finish. */
        const val SOURCE_DOWNLOADS = "source_download_required"
        /** `android_bridge.NOTHING_TO_REDOWNLOAD`: the plan found nothing left to delete. */
        private const val NOTHING_TO_REDOWNLOAD = "No game files hold a translation the patcher cannot rebuild"
        /** `android_bridge.REDOWNLOAD_NAME` and `RESTORE_REFUSED_NAME`: the kept records a plan binds. */
        private const val REDOWNLOAD_RECORD = "redownload.json"
        private const val RESTORE_REFUSED_RECORD = "restore-refused.json"
        /**
         * What an approved Re-download does, as stable codes bound into its plan digest (and shown on the review
         * card the loop guard falls back to):
         * it deletes exactly the plan's package files and clears the game's update records (Watchdog), the game
         * downloads those packages again, the translation waits for that download, no other game data is deleted
         * and the login stays (Scan to login, as after every patch).
         */
        val REDOWNLOAD_CONSEQUENCES = listOf("delete_listed_package_files", "clear_watchdog",
            "game_downloads_listed_packages", "translation_waits_for_download", "no_other_game_data_deleted",
            "login_kept")
        const val INSTALLED_CHANGED = "The installed game app changed since this action started. " +
            "Keep the game closed and save a log for help."
    }

    fun pendingRecoveryResult(): JSONObject? {
        val journal = activeJournal.get() ?: return null
        if (journal.phase != PatchPhase.RECOVERY_REQUIRED) return null
        val saved = journal.snapshot()
        return JSONObject().put("status", "recovery_required").put("session", journal.id)
            .put("normal_verified", saved.optBoolean("normal_verified", false))
            .put("packages_dirty", journal.dirtyPackages).put("launch_allowed", false)
            .put("error", saved.optString("last_error", "Game recovery is incomplete"))
    }

    /** An unexpected loss (provider, timeout, process): consistency is recovered, the saved action is not revoked. */
    fun interrupted(reason: String) {
        cancelled.set(true)
        activeJournal.get()?.let { journal ->
            if (journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) journal.recoveryRequired(reason)
        }
    }

    /** A failure's line for the journal; a worker that died mid-call says so, which ③ reads as a lost provider. */
    private fun reason(error: Throwable) = error.message
        ?: if (error is DeadObjectException) "Worker disconnected" else error.javaClass.simpleName

    /** Between operations: a saved Stop or a lost worker ends the attempt here, before the next change. */
    private fun checkpoint() {
        check(!cancelled.get() && authorizedRun?.let { RunStore(context).load(it.id).mayContinue } != false) {
            "Patch cancelled; restoring verified originals"
        }
        check(device.asBinder().isBinderAlive) { "Worker service disconnected" }
    }

    private fun bridge(name: String, vararg arguments: Any): String {
        if (!Python.isStarted()) Python.start(AndroidPlatform(context))
        return DiagnosticTrace.timed("engine", name) {
            Python.getInstance().getModule("android_bridge").callAttr(name, *arguments).toString()
        }
    }

    private fun requireSpace(phase: String, vararg allocations: Long) =
        StorageBudget.requireAvailable(context.filesDir, phase, *allocations,
            reclaim = { reclaimForShortage(activeJournal.get()) })

    /**
     * Coordinator lock held, on a measured shortage only: every resolved session's bulk, <journal>'s retired
     * snapshots ([releaseRetiredSnapshots]) and the engine folders of earlier app builds ([releaseStaleEngines]).
     * Each part refuses on its own unreadable state; the caller remeasures the same budget afterwards.
     */
    private fun reclaimForShortage(journal: SessionJournal?) {
        releaseResolvedSessions(keepNewest = false)
        if (journal != null) releaseRetiredSnapshots(journal)
        releaseStaleEngines()
    }

    /**
     * The canonical targets of every symbolic link under <roots>, walking links, never their targets, and
     * skipping the canonical paths in <skip>. Null when any folder cannot be listed: cleanup then refuses
     * instead of guessing ownership.
     */
    private fun linkTargets(roots: List<File>, skip: Set<String> = emptySet()): List<String>? = runCatching {
        val found = mutableListOf<String>()
        fun inspect(file: File) {
            if (Files.isSymbolicLink(file.toPath())) { found += file.canonicalPath; return }
            if (file.isDirectory && (skip.isEmpty() || file.canonicalPath !in skip)) {
                checkNotNull(file.listFiles()).forEach { inspect(it) }
            }
        }
        roots.forEach { inspect(it) }
        found
    }.getOrNull()

    /** The private folders whose links may name bytes outside them; walked before any shortage release. */
    private fun referenceRoots(): List<File> = listOf(sessions) +
        listOf("preparations", "recovery", "pristine", "first-setups").map { File(context.filesDir, it) }

    /**
     * Release the bytes of <journal>'s retired snapshots ([RetiredSnapshots.releasable]): the run's own
     * session is pinned, so no session release reaches them. A retired snapshot is no rollback base (it is
     * retired only with no game file mid-change and is never read again) and no Re-download plan's bytes (a
     * plan binds the manifest digest and holds only against the canonical snapshot, [pinnedPlanHolds]; a plan
     * bound to a retired manifest re-measures and needs a new approval). Each must be a real directory at
     * `snapshot-attempts/<id>/retired` under no link, never the canonical snapshot or the current attempt, and
     * no live link may point into it. Its receipt is removed first, so a cut never leaves a receipt naming
     * deleted bytes; `retired_released` is recorded after the bytes are gone, and `retired_snapshots` stays.
     */
    private fun releaseRetiredSnapshots(journal: SessionJournal) {
        if (journal.runId == null) return
        val candidates = RetiredSnapshots.releasable(journal.snapshot())
        if (candidates.isEmpty()) return
        val base = context.filesDir.canonicalFile
        val canonical = File(journal.directory, "snapshot").canonicalPath
        val folders = candidates.mapNotNull { id ->
            val folder = File(journal.directory, "snapshot-attempts/$id/retired")
            val owned = runCatching {
                if (!Files.exists(folder.toPath(), java.nio.file.LinkOption.NOFOLLOW_LINKS)) return@runCatching true
                RunStore.safe(base, folder, true)
                check(folder.canonicalPath != canonical && !Files.isSymbolicLink(folder.toPath()))
                true
            }.getOrDefault(false)
            if (owned) id to folder else null
        }
        if (folders.isEmpty()) return
        val targets = linkTargets(referenceRoots(), folders.map { it.second.canonicalPath }.toSet()) ?: return
        var freed = 0L
        for ((id, folder) in folders) {
            val path = folder.canonicalPath
            if (targets.any { it == path || it.startsWith(path + File.separator) }) continue
            val done = runCatching {
                // The journal is rechecked before each release: a change in flight keeps every byte.
                check(id in RetiredSnapshots.releasable(journal.snapshot()))
                val receipt = File(folder, ArtifactReceipts.NAME)
                if (receipt.exists()) {
                    check(receipt.delete()) { "Cannot invalidate a retired snapshot receipt" }
                    DurableFiles.syncDirectory(folder)
                }
                freed += DurableFiles.deleteTree(folder)
                folder.parentFile?.takeIf { it.isDirectory }?.let { DurableFiles.syncDirectory(it) }
                journal.record(JSONObject().put(RetiredSnapshots.RELEASED, RetiredSnapshots.released(journal.snapshot(), id)))
            }
            if (done.isFailure) report("Could not remove a replaced snapshot of this run (${done.exceptionOrNull()?.javaClass?.simpleName})")
        }
        if (freed > 0) report("Freed ${StorageBudget.freeSpaceLabel(freed)} of a replaced snapshot of this run")
    }

    /**
     * Delete the engine folders of earlier app builds ([EngineAssets.releaseStale]). Kept: the current one,
     * every digest a pending run's saved identity or preparation names, every digest an unresolved or pinned
     * session or pending first setup names, and any folder a live link points into. Any unreadable record or
     * tree deletes nothing.
     */
    private fun releaseStaleEngines() {
        val keep = runCatching {
            val digest = Regex("[0-9a-f]{64}")
            val found = mutableSetOf<String>()
            fun collect(value: Any?) {
                when (value) {
                    is JSONObject -> value.keys().forEach { collect(value.get(it)) }
                    is JSONArray -> for (index in 0 until value.length()) collect(value.get(index))
                    is String -> if (digest.matches(value)) found += value
                }
            }
            val pending = RunStore(context).pending()
            for (run in pending) { collect(run.inputIdentity); collect(run.preparation) }
            val pinned = pending.map { it.sessionId }.toSet() + adoptingSessions
            for (journal in SessionJournal.history(sessions)) {
                if (journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED) || journal.id in pinned) {
                    found += journal.snapshot().getString("engine_id")
                }
            }
            for (setup in FirstSetupJournal.pending(context)) found += setup.snapshot().getString("engine_id")
            found
        }.getOrNull() ?: return
        val targets = linkTargets(referenceRoots()) ?: return
        val freed = runCatching { EngineAssets.releaseStale(context, keep, targets) }
            .getOrElse { report("Could not remove an earlier engine folder (${it.javaClass.simpleName})"); 0L }
        if (freed > 0) report("Freed ${StorageBudget.freeSpaceLabel(freed)} of engine files from earlier app versions")
    }

    /**
     * A resolved session keeps its journal and small receipts. Its game-data copy, build work, staged
     * packages and APK links are the bulk of a run (about twice the downloaded data). A schema-2 session's
     * receipts are removed first, so a cut part-way never leaves a receipt naming deleted bytes.
     */
    private fun releaseSession(directory: File): Long {
        var freed = 0L
        val receipts = listOf(File(directory, "completion-receipt.json"), File(directory, "snapshot/${ArtifactReceipts.NAME}")) +
            File(directory, "build-attempts").listFiles().orEmpty().map { File(it, "result/${ArtifactReceipts.NAME}") }
        for (receipt in receipts) if (receipt.exists()) {
            RunStore.safe(context.filesDir.canonicalFile, receipt)
            check(receipt.delete()) { "Cannot invalidate a released receipt" }
            DurableFiles.syncDirectory(checkNotNull(receipt.parentFile))
        }
        // A legacy session's pristine delta stays until a run promotes or discards it (promoteLegacySessionDelta).
        for (name in listOf("snapshot.tar", "access.apk", "normal.apk", "game", "work", PristineDelta.BUILD_COPY,
                "build-attempts", "snapshot-attempts", "redownload-plans")) {
            freed += DurableFiles.deleteTree(File(directory, name))
        }
        for ((folder, keep) in listOf("snapshot" to "manifest.json", "out" to "device_patch_summary.json")) {
            File(directory, folder).listFiles().orEmpty().filter { it.name != keep }.forEach { freed += DurableFiles.deleteTree(it) }
        }
        return freed
    }

    /**
     * The latest completed run's build estimate, or 0. A build is only measurable once the game data is
     * copied out; this lets the copy's own check reserve the build too. The build re-checks its actual
     * estimate before it starts. Older estimates (schema 1) counted every package and are ignored.
     */
    private fun previousBuildEstimate(): Long = sessions.listFiles().orEmpty()
        .filter { it.isDirectory && !Files.isSymbolicLink(it.toPath()) }
        .mapNotNull { runCatching { SessionJournal.load(it) }.getOrNull() }
        .filter { it.phase == PatchPhase.COMPLETE && it.snapshot().has("build_storage_estimate") }
        .maxByOrNull { it.snapshot().getLong("created_ms") }?.snapshot()
        ?.optJSONObject("build_storage_estimate")?.takeIf { it.optInt("schema") == 2 }
        ?.optLong("additional_bytes")?.takeIf { it in 0..(8L * 1024 * 1024 * 1024) } ?: 0L

    /**
     * Coordinator lock held. Legacy (schema-1) sessions only: makes the newest completed legacy session's
     * pristine delta the patcher's own, then discards every legacy session delta. A delta older than the
     * newest completed session no longer describes the phone and is never promoted. A legacy run closed
     * with its payload verified but its layer unconfirmed counts as completed here: the delta records
     * pristine bytes that run overwrote, and each entry applies only while its file holds the staged bytes.
     * A schema-2 session finalizes its own delta byte-only ([PristineDelta.finalize]); when it is the
     * newest, older legacy deltas are stale and only dropped.
     */
    private fun promoteLegacySessionDelta(enginePath: () -> String) {
        val completed = sessions.listFiles().orEmpty()
            .filter { it.isDirectory && !Files.isSymbolicLink(it.toPath()) }
            .mapNotNull { runCatching { SessionJournal.load(it) }.getOrNull() }
            .filter { it.phase == PatchPhase.COMPLETE || it.layerUnconfirmed }
        val newest = completed.maxByOrNull { it.snapshot().getLong("created_ms") } ?: return
        val legacy = completed.filter { it.runId == null }
        if (newest.runId == null && File(newest.directory, PristineDelta.SESSION_DELTA).isFile) {
            val kept = runCatching {
                val result = JSONObject(bridge("keep_delta", enginePath(), newest.directory.path, pristine.path))
                val files = result.getInt("files")
                report(if (files > 0) "Kept a pristine delta of $files files for the next language switch"
                       else "The game files are untranslated; no pristine delta is kept")
            }.onFailure { report("Could not keep the pristine delta (${it.javaClass.simpleName}); " +
                "switching languages will need the game's data cleared") }
            // A failed promotion keeps every legacy delta for a later attempt rather than losing it.
            if (kept.isFailure) return
        }
        for (journal in legacy) runCatching { File(journal.directory, PristineDelta.SESSION_DELTA).delete() }
    }

    /**
     * Coordinator lock held. A damaged journal or run record is left for recovery and export rather than
     * guessed at. Legacy resolved sessions release their bulk as before. A schema-2 session stays pinned
     * while its saved action is unresolved (continuation and recovery need it); among resolved ones only the
     * newest stays as the device target's reusable cache, so stopped reusable work survives until a newer
     * resolved action replaces it, Free up space removes it, or a measured budget needs its space.
     */
    private fun releaseResolvedSessions(keepNewest: Boolean = true) {
        // Unknown authorization can pin any session: do not infer that a damaged run is resolved.
        val pending = runCatching { RunStore(context).pending() }.getOrNull() ?: return
        val pinned = pending.map { it.sessionId }.toMutableSet().apply { addAll(adoptingSessions) }
        val references = mutableListOf<File>()
        var freed = 0L
        val resolved = mutableListOf<SessionJournal>()
        for (directory in sessions.listFiles().orEmpty()) {
            if (!directory.isDirectory || Files.isSymbolicLink(directory.toPath())) continue
            val journal = runCatching { SessionJournal.load(directory) }.getOrNull()
            if (journal == null || journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED) || directory.name in pinned) {
                references += directory; continue
            }
            val runId = journal.runId
            if (runId == null) { resolved += journal; continue }
            val run = runCatching { RunStore(context).load(runId) }.getOrNull()
            if (run != null && run.lifecycle in setOf("complete", "stopped")) resolved += journal
            else references += directory
        }
        // A kept APK or unfinished build may link into a resolved session. Walk links, never their targets;
        // an unreadable reference tree refuses cleanup instead of guessing ownership.
        references += listOf("preparations", "recovery", "pristine").map { File(context.filesDir, it) }
        val targets = linkTargets(references) ?: return
        val removable = resolved.filter { candidate ->
            val path = candidate.directory.canonicalPath
            candidate.id !in pinned && targets.none { it == path || it.startsWith(path + File.separator) }
        }
        val newest = resolved.filter { it.runId != null }.maxByOrNull { it.snapshot().getLong("created_ms") }?.id
        removable.filter { !keepNewest || it.runId == null || it.id != newest }.forEach { freed += release(it.directory) }
        if (freed > 0) report("Freed ${StorageBudget.freeSpaceLabel(freed)} of files left by earlier runs")
    }

    private fun release(directory: File): Long = runCatching { releaseSession(directory) }.getOrElse {
        report("Could not remove some files of an earlier run (${it.javaClass.simpleName})"); 0L
    }

    private fun <T> exclusive(action: () -> T): T = RunStore.coordinator(context, action)

    private fun install(journal: SessionJournal, file: File, access: Boolean, next: PatchPhase,
                        expected: ApkIdentity? = null, updates: JSONObject = JSONObject()) {
        val identity = ApkIdentity.read(context, file)
        check(expected == null || identity == expected) { "The session's APK changed after it was checked" }
        if (!access) identity.requireRecovery()
        else check(identity.debuggable && identity.certificateSha256 == GameSigner.CERTIFICATE_SHA256)
        journal.intent(if (access) "install_access" else "install_normal", identity.json())
        report(if (access) "Opening game data access" else "Restoring normal game APK")
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.replaceGameApk(it, identity.bytes)
        }
        verifyInstalled(identity)
        journal.outcome(next, updates.put("normal_verified", !access))
    }

    /**
     * The privileged tar streams through a pipe into the engine's extraction, with no archive on disk. Both
     * ends hash the stream; a short, extra or different byte refuses the snapshot.
     */
    private fun streamSnapshot(enginePath: String, destination: File, budget: Long) {
        val pipe = ParcelFileDescriptor.createPipe()
        val sender = Executors.newSingleThreadExecutor()
        try {
            // Our copy of the write end closes when the call returns, which ends the extraction's stream.
            val sent = sender.submit<String> { pipe[1].use { device.snapshotGame(it, budget) } }
            val received = try {
                JSONObject(bridge("unpack_snapshot_stream", enginePath, pipe[0].detachFd(), destination.path, budget))
            } catch (error: Throwable) {
                runCatching { sent.get(60, TimeUnit.SECONDS) }.exceptionOrNull()?.let { error.addSuppressed(it) }
                throw error
            }
            val result = JSONObject(try { sent.get(60, TimeUnit.SECONDS) }
                catch (wrapped: ExecutionException) { throw wrapped.cause ?: wrapped })
            check(received.getLong("bytes") == result.getLong("bytes") &&
                received.getString("sha256") == result.getString("sha256")) { "Snapshot transport differs" }
        } finally {
            pipe.forEach { runCatching { it.close() } }
            sender.shutdownNow()
        }
    }

    private fun verifyInstalled(expected: ApkIdentity) {
        installedVerifier?.let { it.verify(expected); return }
        InstalledGameVerifier(context, device).verify(expected)
    }

    /**
     * Whether <expected> is the installed game app: true only on a completed match. A check the shell provider's
     * loss cut short is no verdict either way, so it raises the provider loss ([InstalledGameVerifier.PROVIDER_LOST],
     * read by ③ as a lost provider that waits for the same provider) instead of answering false, which every
     * caller reports as [INSTALLED_CHANGED] (phone f15a72e, 2026-11-12).
     */
    private fun installed(expected: ApkIdentity): Boolean = try { verifyInstalled(expected); true } catch (error: Throwable) {
        val alive = runCatching { device.asBinder().isBinderAlive }.getOrDefault(false)
        if (InstalledGameVerifier.providerLost(error, alive)) {
            throw IllegalStateException(InstalledGameVerifier.PROVIDER_LOST, error)
        }
        false
    }

    fun verifyRecoveryInstalled(normalId: String) { exclusive { verifyInstalled(store.verify(normalId)) } }

    private fun validateLayer(manifest: File) {
        ParcelFileDescriptor.open(manifest, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.validateGameSnapshot(it)
        }
    }

    private fun gameChanged(error: Throwable) = GAME_CHANGED.any { error.message.orEmpty().contains(it) }

    /**
     * Measure the exact Re-download scope from this session's verified snapshot into a fresh plan folder and
     * bind it (ticket 12): run, session, action and target, the snapshot manifest, the kept delta and its
     * records, engine and producer, the run's APKs, every file deleted with its hash and size, the Watchdog
     * files cleared, and [REDOWNLOAD_CONSEQUENCES]. No game file changes. An approval names the plan's digest
     * ([ArtifactReceipts.identityKey] of `plan.json`). The staged list that the deletions and their rollback
     * read must be exactly the plan's files at their snapshot hashes. Returns the plan's id and content.
     */
    private fun planRedownload(journal: SessionJournal, apks: RunApks, enginePath: String,
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
    private fun savedPlan(journal: SessionJournal): Pair<String, JSONObject>? {
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
    private fun pinRedownload(journal: SessionJournal, run: RunStore.Run, id: String, plan: JSONObject,
                              waiting: Boolean) {
        val updates = JSONObject().put("redownload_plan", id)
            .put("redownload_plan_sha256", ArtifactReceipts.identityKey(plan)).put("build_attempt", "")
        if (waiting) updates.put("waiting_reason", REDOWNLOAD_CONSENT)
        journal.record(updates)
        offerRedownload(run, id, plan)
    }

    private fun offerRedownload(run: RunStore.Run, id: String, plan: JSONObject) {
        val files = plan.getJSONObject("files")
        val bytes = files.keys().asSequence().sumOf { files.getJSONObject(it).getLong("bytes") }
        val packages = plan.getJSONObject("packages").keys().asSequence().sortedBy { it.toBigInteger() }.toList()
        RunStore(context).proposeRedownload(run.id, id, ArtifactReceipts.identityKey(plan), files.length(),
            packages, bytes, automatic = true)
    }

    /** The run record's approval of exactly <plan>, or null when the loop guard left it for the user's review. */
    private fun approvedPlan(run: RunStore.Run, plan: JSONObject): Redownload? =
        RunStore(context).load(run.id).redownload?.takeIf { it.approved && it.planSha256 == ArtifactReceipts.identityKey(plan) }

    /** Why the loop guard held <plan> back, reported before the action waits for the user's review. */
    private fun heldBack(run: RunStore.Run, plan: JSONObject): WaitingForUser {
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
    private fun pinnedPlanHolds(journal: SessionJournal, plan: JSONObject, apks: RunApks, enginePath: String,
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

    /**
     * The approved Re-download, from a snapshot just revalidated against the live layer. The pinned plan must
     * still hold ([pinnedPlanHolds]); otherwise the scope is measured again, and only exactly the approved
     * digest proceeds. A changed plan deletes nothing under the old approval: it is pinned and approved again
     * automatically, or waits for the user's review when the loop guard holds it back. `deleting`, the
     * `redownload_delete` attempt and each `delete_file` intent are saved before their change. An interruption
     * rolls the deleted files and Watchdog back from the verified snapshot ([recoverLocked]), and a later
     * dispatch resumes this same approved plan without asking. Once the files are gone and Watchdog cleared,
     * the approval is consumed, the normal APK restored (Root: verified unchanged), and the saved action waits
     * for the game's download. Null when nothing is left to delete: the action goes on to its build.
     */
    private fun redownloadStage(journal: SessionJournal, apks: RunApks, enginePath: String, run: RunStore.Run,
                                approved: Redownload, manifest: File,
                                transaction: GameFileTransaction): JSONObject? {
        report(WorkerStep.DAMAGED_FILES_FOUND)
        if (journal.phase == PatchPhase.SNAPSHOT_READY) journal.outcome(PatchPhase.BUILDING)
        val pinned = savedPlan(journal)?.takeIf { (_, plan) ->
            ArtifactReceipts.identityKey(plan) == approved.planSha256 && pinnedPlanHolds(journal, plan, apks,
                enginePath, run, manifest, approved.state == RedownloadConsent.DELETING)
        }
        val (id, plan) = pinned ?: kotlin.run {
            report("Finding the package files the game update could not change")
            val measured = try { planRedownload(journal, apks, enginePath, run, manifest) } catch (error: Exception) {
                if (!error.message.orEmpty().contains(NOTHING_TO_REDOWNLOAD)) throw error
                // The game replaced those files itself: the approval is unused and the action goes on.
                journal.record(JSONObject().put("waiting_reason", "").put("redownload_plan", "")
                    .put("redownload_plan_sha256", ""))
                report("No damaged game files are left; continuing without Re-download")
                return null
            }
            pinRedownload(journal, run, measured.first, measured.second, waiting = true)
            if (ArtifactReceipts.identityKey(measured.second) != approved.planSha256) {
                report("The game files changed since the Re-download was approved; nothing was deleted")
                approvedPlan(run, measured.second) ?: throw heldBack(run, measured.second)
                report("Re-download planned again for the changed files")
            }
            measured
        }
        val digest = ArtifactReceipts.identityKey(plan)
        val root = checkNotNull(journal.redownloadPlanRoot)
        check(journal.resultRoot.canonicalPath == root.canonicalPath && root.name == id) { "Re-download plan is not pinned" }
        val hashes = ArtifactReceipts.parse(File(root, "staged-hashes.json").readBytes())
        transaction.verifyOriginals()
        requireSpace("normal restore", apks.restoreBytes)
        checkpoint()
        RunStore(context).redownloadProgress(run.id, digest, RedownloadConsent.DELETING)
        operation(journal, RedownloadConsent.DELETE_OPERATION)
        device.forceStopGame()
        validateLayer(manifest)
        // Kept before the first deletion: until the game downloads the packages again, a patch would read
        // a layer without them. A rollback puts them back, and the next run then drops the record.
        val kept = JSONObject(bridge("keep_redownload", enginePath, journal.directory.path, pristine.path, root.path))
        journal.record(JSONObject().put("redownload_kept", JSONObject().put("plan_sha256", digest)
            .put("record", kept.getJSONObject("record"))))
        journal.outcome(PatchPhase.STAGED)
        journal.outcome(PatchPhase.APPLYING)
        for (name in hashes.keys().asSequence().sorted()) {
            checkpoint()
            report("Deleting package file $name")
            transaction.delete("packages/$name", hashes.getString(name))
        }
        checkpoint()
        transaction.finishDeletion()
        // Consumed: the files are gone. Saved before the normal APK, so a cut from here waits for the download.
        val history = journal.snapshot().optJSONArray("redownloaded") ?: JSONArray()
        check(history.length() < 32) { "Too many Re-downloads in one action" }
        journal.record(JSONObject().put("redownloaded", history.put(JSONObject().put("plan_sha256", digest)
            .put("files", hashes.length()))).put("waiting_reason", REDOWNLOAD_DOWNLOAD))
        RunStore(context).redownloadProgress(run.id, digest, RedownloadConsent.DELETED)
        restoreGameApp(journal, apks, PatchPhase.RESTORING)
        journal.outcome(PatchPhase.CANCELLED, JSONObject().put("normal_verified", true))
        report("Damaged files deleted; the game downloads them again before the translation continues")
        return waitingResult(journal, run)
    }

    /**
     * A saved action that waits for the user: the plan's answer, or the game's download. Null lets it continue:
     * a download the user confirmed continues the original action, whose build checks readiness again, and a
     * legacy wait without a measured plan builds again to measure one. An approved plan whose deletion budget
     * is not spent resumes here, without another dialog. Anything else stays waiting, with the normal APK
     * verified first; a Stop resolves the action consistent.
     */
    private fun waitingStep(journal: SessionJournal, run: RunStore.Run, apks: RunApks): JSONObject? {
        val reason = journal.waitingReason ?: return null
        val runs = RunStore(context)
        val saved = runs.load(run.id)
        if (saved.stopRequested) {
            if (journal.phase != PatchPhase.CANCELLED) recoverWithNormalFallback(journal)
            settle(journal)
            return completedResult(journal, run)
        }
        when (reason) {
            "storage" -> {
                val budget = journal.snapshot().getJSONObject("storage_wait")
                val required = budget.getLong("required_bytes")
                check(required > 0) { "Invalid saved storage budget" }
                if (saved.mayContinue && context.filesDir.usableSpace < required) reclaimForShortage(journal)
                if (saved.mayContinue && context.filesDir.usableSpace >= required) {
                    journal.record(JSONObject().put("waiting_reason", "").put("storage_wait", JSONObject.NULL))
                    runs.waitFor(run.id, null)
                    return null
                }
            }
            SOURCE_DOWNLOADS -> {
                if (saved.mayContinue && saved.sourceDownloads == "confirmed") {
                    journal.record(JSONObject().put("waiting_reason", "")); return null
                }
            }
            REDOWNLOAD_CONSENT -> {
                val pinned = savedPlan(journal)
                if (pinned == null) {
                    // A wait saved before plans existed: nothing is approved, so the build measures one.
                    if (saved.mayContinue) { journal.record(JSONObject().put("waiting_reason", "")); return null }
                } else {
                    val (id, plan) = pinned
                    val digest = ArtifactReceipts.identityKey(plan)
                    // A cut between the journal and the run record: offer the pinned plan (same digest keeps its answer).
                    if (saved.mayContinue && saved.redownload?.let { it.planSha256 != digest || it.planId != id } != false) {
                        offerRedownload(run, id, plan)
                    }
                    val consent = runs.load(run.id).redownload
                    if (saved.mayContinue && consent != null && consent.approved && consent.planSha256 == digest) {
                        if (runs.load(run.id).attempts.optInt(RedownloadConsent.DELETE_OPERATION, 0) >= 2) {
                            // Two attempts already used this approval: ask again rather than delete a third time.
                            runs.requireFreshRedownloadConsent(run.id, digest)
                            report("The approved Re-download was interrupted twice; it needs a new approval")
                        } else {
                            if (journal.phase != PatchPhase.PREPARED) journal.resumeConsistent()
                            report("Continuing the approved Re-download")
                            return continueLocked(journal, apks, run.action == "remove", consent)
                        }
                    }
                }
            }
            REDOWNLOAD_DOWNLOAD -> {
                val consent = saved.redownload
                val history = journal.snapshot().optJSONArray("redownloaded")
                val last = history?.optJSONObject(history.length() - 1)
                // A cut after the deletion but before the run record: the journal is the truth.
                if (consent != null && consent.state == RedownloadConsent.DELETING &&
                    last?.optString("plan_sha256") == consent.planSha256) {
                    runs.redownloadProgress(run.id, consent.planSha256, RedownloadConsent.DELETED)
                }
                val answered = runs.load(run.id)
                if (saved.mayContinue && answered.redownload?.state == RedownloadConsent.DOWNLOADS_CONFIRMED) {
                    // The deletion made the saved snapshot stale on purpose, and the user just said the game's
                    // downloads finished: that answer covers that one snapshot's source-download gate, so the
                    // run does not open access only to wait for the same answer again. The snapshot is still
                    // retired and retaken, and the build still sends an unfinished download back here.
                    val deleted = last?.optString("plan_sha256")
                    val snapshot = File(journal.directory, "snapshot")
                    val manifest = File(snapshot, "manifest.json")
                    if (RedownloadConsent.answersSourceDownloads(answered.mayContinue, answered.redownload, deleted) &&
                        !Files.isSymbolicLink(snapshot.toPath()) && manifest.isFile && !Files.isSymbolicLink(manifest.toPath())) {
                        runs.confirmSourceDownloadsAfterRedownload(run.id, ApkIdentity.digest(manifest), deleted)
                    }
                    journal.record(JSONObject().put("waiting_reason", ""))
                    report("Continuing the saved action after the game's download")
                    return null
                }
            }
        }
        if (journal.phase != PatchPhase.CANCELLED) recoverWithNormalFallback(journal)
        return waitingResult(journal, run)
    }

    /** What the saved action waits for, with the plan's summary the screen shows before any approval. */
    private fun waitingResult(journal: SessionJournal, run: RunStore.Run): JSONObject {
        val result = JSONObject().put("status", "waiting").put("action", resultAction(run))
            .put("reason", journal.waitingReason ?: JSONObject.NULL).put("session", journal.id).put("run", run.id)
            .put("launch_allowed", journal.phase == PatchPhase.CANCELLED)
        if (journal.root) result.put("root", true)
        if (journal.waitingReason == "storage") {
            val budget = journal.snapshot().getJSONObject("storage_wait")
            val shortage = StorageBudget.Shortage(budget.getString("phase"), budget.getLong("required_bytes"), context.filesDir.usableSpace)
            result.put("error", shortage.message).put("storage_wait", shortage.json())
        }
        RunStore(context).load(run.id).redownload?.let { consent ->
            result.put("redownload", JSONObject().put("plan_sha256", consent.planSha256).put("state", consent.state)
                .put("files", consent.files).put("packages", JSONArray(consent.packages)).put("bytes", consent.bytes))
        }
        return result
    }

    /**
     * What a run reads and leaves installed. The shell path installs <access> for the run and the saved normal
     * APK <recoveryId> after it. Under root (<installed> set) nothing is installed: the run reads the saved copy
     * of the installed game app and leaves the app in place (ADR 0007). <restoreBytes> is the installer space
     * the normal restore needs, reserved beside every allocation; root needs none. <source> is the installed
     * game the preparation read (shell path), the only other identity a continuation may find installed.
     */
    private class RunApks(val recoveryId: String, val buildApk: File, val access: ApkIdentity?,
                          val accessApk: File?, val installed: ApkIdentity?, val restoreBytes: Long,
                          val source: ApkIdentity? = null) {
        val root: Boolean get() = installed != null
    }

    private fun requireNoPendingWork(remove: Boolean, redownload: Boolean) {
        check(!(remove && redownload)) { "Remove and Re-download are separate runs" }
        EmergencyRestoreStore(context).requireResolved()
        val unfinished = SessionJournal.pending(sessions)
        check(unfinished.isEmpty()) { "Recover the unfinished session before starting another patch" }
        check(FirstSetupJournal.pending(context).isEmpty()) { "Finish or recover first-time setup before starting a patch" }
    }

    /**
     * Existing converted installs only. Official-signature conversion requires a separate consent flow.
     * <remove> is Remove translation: the build step stages the rebuilt pristine files instead of a
     * translation, and everything else, the write-back and its rollback included, is the patch run's.
     * <redownload> stays refused: Re-download runs only inside a saved action, after its own scoped
     * approval ([redownloadStage]). Reachable only through [dispatch].
     */
    @JvmOverloads fun run(normalId: String, accessApk: File, sourceIdentity: ApkIdentity? = null,
                          remove: Boolean = false, redownload: Boolean = false): JSONObject = exclusive {
        requireNoPendingWork(remove, redownload)
        checkNotNull(authorizedRun) { "Explicit durable Start dispatch required" }
        val normal = store.verify(normalId)
        val installedSource = sourceIdentity ?: normal
        installedSource.requireRecovery()
        check(installedSource.versionCode == normal.versionCode && installedSource.versionName == normal.versionName) {
            "Prepared source and recovery versions do not match"
        }
        val access = ApkIdentity.read(context, accessApk)
        check(access.debuggable && access.certificateSha256 == normal.certificateSha256 &&
            access.versionCode == normal.versionCode && access.versionName == normal.versionName) {
            "Access and recovery APK identities do not match"
        }
        runLocked(RunApks(normalId, store.normal(normalId), access, accessApk, null, normal.bytes, installedSource),
            installedSource, remove, redownload)
    }

    /**
     * Root's run (ADR 0007): the same snapshot, build, write and rollback, with no APK installed. <installedApk>
     * is the saved copy of the installed game app <installed>, which the build reads and the run leaves in place.
     */
    @JvmOverloads fun runRoot(installedApk: File, installed: ApkIdentity, remove: Boolean = false,
                              redownload: Boolean = false): JSONObject = exclusive {
        requireNoPendingWork(remove, redownload)
        checkNotNull(authorizedRun) { "Explicit durable Start dispatch required" }
        check(installed.packageName == PrivilegedDeviceService.GAME) { "Unsupported game package" }
        check(!installed.debuggable) { ROOT_ACCESS_INSTALLED }
        runLocked(RunApks(installed.sha256, installedApk, null, null, installed, 0L), installed, remove, redownload)
    }

    /**
     * The one entry for a durable Start, fresh or continued. Under the shared coordinator lock it claims the
     * saved run (claim-before-journal crashes keep the same session UUID), then either starts the session or
     * continues the existing one from its checkpoints. A reconnect or reopen never launches a second
     * coordinator, resets Stop, grants consent or resets attempt budgets.
     */
    fun dispatch(request: String, action: String, provider: ShellProvider): JSONObject = exclusive {
        val requests = PatchRequestStore(context)
        val run = requests.claimRun(request, action, provider)
        val child = File(sessions, run.sessionId)
        authorizedRun = run
        try {
            if (child.exists() || Files.isSymbolicLink(child.toPath())) {
                val journal = SessionJournal.load(child)
                check(journal.runId == run.id && journal.authorizationKey == run.authorizationKey &&
                    journal.root == (provider == ShellProvider.ROOT)) { "Cannot correlate Start and journal" }
                activeJournal.set(journal)
                return@exclusive continueExisting(journal, run)
            }
            check(action != "first_setup" && action != "redownload") { "Separate scoped destructive consent required" }
            RunStore(context).beginAttempt(run.id, "dispatch")
            if (provider == ShellProvider.ROOT) {
                val prepared = requests.loadRoot(run)
                runRoot(prepared.apk, prepared.installed, action == "remove", false)
            } else {
                val prepared = requests.load(run)
                run(prepared.normal.sha256, prepared.accessFile, prepared.source, action == "remove", false)
            }
        } finally { authorizedRun = null }
    }

    /**
     * Continue a correlated session: finish safety first, then whole stages. A verified payload whose normal
     * APK is verified only finalizes. An unfinished file change rolls back from its verified originals. A
     * lost install reply is audited against the installed identity. A run waiting for a separate approval
     * stays waiting ([waitingStep]); an approved Re-download resumes there. Only then does the run re-enter its
     * stages, reusing what still verifies.
     */
    private fun continueExisting(journal: SessionJournal, run: RunStore.Run): JSONObject {
        if (journal.phase == PatchPhase.COMPLETE) {
            val durable = RunStore(context).load(run.id)
            if (durable.lifecycle == "complete" && !durable.stopRequested) return completedResult(journal, run)
            // Death between journal terminal publication and the run-store write:
            // the saved COMPLETE flag grants no restart live-byte proof.
            journal.recoveryRequired("Completion publication was interrupted; auditing current game bytes")
            recoverWithNormalFallback(journal)
            if (journal.phase == PatchPhase.COMPLETE ||
                (journal.phase == PatchPhase.CANCELLED && RunStore(context).load(run.id).stopRequested))
                return completedResult(journal, run)
        }
        val apks = runApks(run)
        val intent = journal.snapshot().optJSONObject("mutation_intent")
        if (intent?.optString("operation") == "install_access" && !journal.dirtyPackages && !journal.payloadVerified) {
            // A lost reply proves neither outcome: read what is installed before choosing the next step.
            val access = checkNotNull(apks.access)
            val observed = when {
                installed(access) -> access.sha256
                installed(store.verify(apks.recoveryId)) -> apks.recoveryId
                else -> null
            }
            journal.reconcileInstall(observed)
            report("Checked the game app an interrupted install left installed")
        }
        val pendingSafety = journal.dirtyPackages || journal.hasMutationIntent || journal.hasRecoveryNormalIntent ||
            (journal.payloadVerified && !journal.layerUnconfirmed)
        if (pendingSafety) {
            report("Restoring consistency before continuing the saved action")
            recoverWithNormalFallback(journal)
            if (journal.phase == PatchPhase.COMPLETE) { settle(journal); return completedResult(journal, run) }
        }
        waitingStep(journal, run, apks)?.let { return it }
        check(RunStore(context).load(run.id).mayContinue) { "The saved action was stopped" }
        // Whole stages restart from PREPARED; the saved snapshot/build checkpoints are revalidated, not reset.
        if (journal.phase != PatchPhase.PREPARED || journal.layerUnconfirmed) journal.resumeConsistent()
        report("Continuing the saved action from its verified checkpoints")
        return continueLocked(journal, apks, run.action == "remove")
    }

    // A saved normal/payload proof is insufficient after reopen: pendingSafety always audits live bytes.

    /** Safety recovery; a recovery that fails still tries to leave the verified normal APK installed. */
    private fun recoverWithNormalFallback(journal: SessionJournal) {
        if (journal.phase != PatchPhase.RECOVERY_REQUIRED) journal.recoveryRequired("Continuing after an interruption")
        try { recoverLocked(journal) } catch (error: Throwable) {
            journal.recoveryRequired(error.message ?: "Recovery interrupted")
            restoreNormalAfterFailure(journal, error)
            throw error
        }
    }

    /** The run's last step: the shell path installs the normal APK; root checks the game app it never replaced. */
    private fun restoreGameApp(journal: SessionJournal, apks: RunApks, next: PatchPhase,
                               updates: JSONObject = JSONObject()) {
        val installed = apks.installed
        if (installed == null) { install(journal, store.normal(apks.recoveryId), false, next, updates = updates); return }
        report("Checking the installed game app")
        verifyInstalled(installed)
        journal.outcome(next, updates.put("normal_verified", true))
        report(WorkerStep.ROOT_SKIPS_RESTORE)
    }

    private fun runApks(run: RunStore.Run): RunApks {
        val requests = PatchRequestStore(context)
        return if (run.provider == ShellProvider.ROOT) {
            val prepared = requests.loadRoot(run)
            RunApks(prepared.installed.sha256, prepared.apk, null, null, prepared.installed, 0)
        } else {
            val prepared = requests.load(run)
            val normal = store.verify(prepared.normal.sha256)
            RunApks(normal.sha256, store.normal(normal.sha256), prepared.access,
                prepared.accessFile, null, normal.bytes, prepared.source)
        }
    }

    private fun runLocked(apks: RunApks, installedSource: ApkIdentity, remove: Boolean, redownload: Boolean): JSONObject {
        check(!redownload) { "Separate scoped destructive consent required" }
        val run = checkNotNull(authorizedRun)
        val engine = EngineAssets.prepare(context)
        bridge("engine_preflight", engine.path)
        verifyInstalled(installedSource)
        promoteLegacySessionDelta { engine.path }
        // Space the patch can reclaim goes before the first budget, so that budget is not short by it.
        releaseResolvedSessions()
        val accessApk = apks.accessApk
        val access = apks.access
        if (accessApk != null && access != null) {
            runCatching { ApkPreparation(context).releaseUnneeded(installedSource, accessApk.parentFile?.parentFile, report) }
                .onFailure { report("Could not remove unneeded saved APKs (${it.javaClass.simpleName})") }
            StorageBudget.releaseReplacedGameApks(device, report)
            requireSpace("APK install and normal restore", maxOf(access.bytes, apks.restoreBytes))
        }
        checkpoint()
        val journal = SessionJournal.create(sessions, apks.recoveryId, engine.name, apks.installed,
            run.id, run.authorizationKey)
        activeJournal.set(journal)
        if (accessApk != null && access != null) linkSessionAccess(journal, accessApk, access, apks.restoreBytes)
        return continueLocked(journal, apks, remove)
    }

    /** Persist an attempt of logical <name> before it is sent; the budget never resets on reopen. */
    private fun operation(journal: SessionJournal, name: String) {
        journal.runId?.let { RunStore(context).beginAttempt(it, name) }
    }

    /**
     * Resume whole stages only; every retained consumer is revalidated after restart. The journal is clean
     * here (no file mid-change, no unresolved intent): either a fresh session or one [continueExisting]
     * made consistent. Any failure rolls back what this call changed, then leaves the saved action as it was.
     * <redownload> is an approved Re-download ([redownloadStage]), run on the revalidated snapshot before any
     * build. A wait for the user ([WaitingForUser]) is not a failure: the game files are rolled back, the
     * normal APK verified, and the waiting result returned.
     */
    private fun continueLocked(journal: SessionJournal, apks: RunApks, remove: Boolean,
                               redownload: Redownload? = null): JSONObject {
        val run = checkNotNull(authorizedRun)
        check(journal.runId == run.id && !journal.dirtyPackages && !journal.hasMutationIntent) { "Session is not consistent" }
        val engine = EngineAssets.prepare(context)
        bridge("engine_preflight", engine.path)
        val transaction = GameFileTransaction(journal, device)
        val metrics = RunMetrics(context, File(journal.directory, "resource-metrics.json"))
        var metricStatus = "interrupted"
        val restoreBytes = apks.restoreBytes
        try {
            report(if (remove) "Removing the translation" else "Language: ${PatchLanguage.name(run.language)}")
            checkpoint()
            device.forceStopGame()
            openAccess(journal, apks)
            val (manifest, identity) = snapshotStage(journal, apks, engine.path, run)
            if (journal.phase == PatchPhase.SNAPSHOT_ACCESS_INSTALLED) journal.outcome(PatchPhase.SNAPSHOT_READY)
            checkpoint()
            if (redownload != null) {
                redownloadStage(journal, apks, engine.path, run, redownload, manifest, transaction)?.let {
                    metricStatus = "waiting"
                    settle(journal)
                    return it
                }
                checkpoint()
            }
            val reused = if (redownload == null && identity != null && !journal.snapshot().has("build_attempt"))
                reuseCompletion(journal, apks, engine.path, run, identity) else null
            val result = try { buildStage(journal, apks, engine.path, run, identity, remove, reused) }
            catch (approved: RedownloadApproved) {
                // Same run, same verified snapshot and access: delete, restore the normal APK, wait for the download.
                checkpoint()
                redownloadStage(journal, apks, engine.path, run, approved.consent, manifest, transaction)?.let {
                    metricStatus = "waiting"
                    settle(journal)
                    return it
                }
                throw IllegalStateException("The damaged game files changed during their Re-download; tap Start again", approved)
            }
            checkpoint()
            val hashes = ArtifactReceipts.parse(File(result, "staged-hashes.json").readBytes())
            hashes.keys().asSequence().forEach { GameFilePolicy.validate("packages/$it", writable = true) }
            val verified = transaction.verifyOriginals()
            val originals = verified.files()
            val largestStaged = hashes.keys().asSequence().map { File(result, "out/$it").length() }.maxOrNull() ?: 0L
            val largestOriginal = originals.keys().asSequence().map { originals.getJSONObject(it).getLong("bytes") }
                .maxOrNull() ?: 0L
            val writeReserve = maxOf(largestStaged, largestOriginal)
            requireSpace("file writes and normal restore", restoreBytes, writeReserve)
            device.forceStopGame()
            // Still the access APK from the snapshot; the layer is checked again before the first write.
            validateLayer(manifest)
            val changed = transaction.changedWrites(hashes, verified)
            metrics.filePlan(originals, hashes, result, changed)
            operation(journal, "apply")
            journal.outcome(PatchPhase.APPLYING)
            for (name in changed) {
                checkpoint()
                requireSpace("package write and normal restore", restoreBytes, writeReserve)
                report("Applying package file $name")
                transaction.write("packages/$name", File(result, "out/$name"), hashes.getString(name))
                metrics.fileWritten(File(result, "out/$name").length())
            }
            checkpoint()
            transaction.finishApply(hashes, verified)
            // PAYLOAD_VERIFIED is durable. From here the run only finishes forward: no rebuild or rewrite.
            operation(journal, "final_install")
            restoreGameApp(journal, apks, PatchPhase.RESTORING, JSONObject().put("final_normal_verified", true))
            finalizeAndComplete(journal)
            metricStatus = "complete"
            settle(journal)
            return completedResult(journal, run)
        } catch (error: Throwable) {
            if (error is StorageBudget.Shortage) {
                journal.record(JSONObject().put("waiting_reason", "storage").put("storage_wait", error.json()))
                RunStore(context).waitFor(run.id, "storage")
            }
            val failedOperation = journal.runId?.let { runCatching { RunStore(context).load(it).lastOperation } }
            journal.recoveryRequired(reason(error))
            var recoveryFailed = false
            try { recoverLocked(journal) } catch (recovery: Throwable) {
                recoveryFailed = true
                journal.recoveryRequired("${reason(error)}; recovery: ${reason(recovery)}")
                if (restoreNormalAfterFailure(journal, recovery)) closeIfNothingToRecover(journal)
                error.addSuppressed(recovery)
            }
            if (journal.phase == PatchPhase.COMPLETE) {
                metricStatus = "complete"
                report("Verified patch and normal APK recovered after interrupted final installation")
                settle(journal)
                return completedResult(journal, run)
            }
            if (!recoveryFailed && failedOperation?.isSuccess == true) {
                journal.runId?.let { RunStore(context).restoreOperation(it, failedOperation.getOrNull()) }
            }
            settle(journal)
            // An explicit Stop made consistent is its own result, not a failure; an interruption still fails.
            if (journal.phase == PatchPhase.CANCELLED && journal.snapshot().optBoolean("stopped", false)) {
                return completedResult(journal, run)
            }
            if (!recoveryFailed && journal.phase == PatchPhase.CANCELLED && error is StorageBudget.Shortage) {
                metricStatus = "waiting"
                return waitingResult(journal, run)
            }
            // A wait for the user's answer or the game's download, made consistent: not a failure.
            if (journal.phase == PatchPhase.CANCELLED && error is WaitingForUser && journal.waitingReason != null) {
                metricStatus = "waiting"
                report(error.message.orEmpty())
                return waitingResult(journal, run)
            }
            throw error
        } finally {
            metrics.originalHashPasses(transaction.originalHashPasses)
            runCatching { metrics.finish(metricStatus) }.onFailure {
                android.util.Log.w("HokAceMetrics", "Resource metrics could not be retained", it)
            }
        }
    }

    /** Unlock game data: the shell path installs the access APK unless it is already the installed app. */
    private fun openAccess(journal: SessionJournal, apks: RunApks) {
        val installedRoot = apks.installed
        if (installedRoot != null) {
            report(WorkerStep.ROOT_SKIPS_ACCESS)
            // Root reads the game's files as they are: no access APK to install (ADR 0007).
            check(installed(installedRoot)) { INSTALLED_CHANGED }
            if (journal.phase == PatchPhase.PREPARED) journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED)
            return
        }
        val access = checkNotNull(apks.access)
        if (installed(access)) {
            report("Game data access is already open")
            if (journal.phase == PatchPhase.PREPARED) {
                journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, JSONObject().put("normal_verified", false))
            }
            return
        }
        // Never install over an identity this action did not prepare (a store update, another app build).
        val known = listOfNotNull(store.verify(apks.recoveryId), apks.source)
        check(known.any { installed(it) }) { INSTALLED_CHANGED }
        check(journal.phase == PatchPhase.PREPARED) { "Access install outside its checkpoint" }
        requireSpace("APK install and normal restore", maxOf(access.bytes, apks.restoreBytes))
        operation(journal, "access_install")
        // install() reads the session copy and requires it to be the access APK checked above.
        install(journal, File(journal.directory, "access.apk"), true, PatchPhase.SNAPSHOT_ACCESS_INSTALLED, access)
    }

    /**
     * SNAPSHOT_READY: the canonical snapshot verified against the live layer, plus the complete measured
     * input identity (null when the producer cannot be measured: ordinary work, no checkpoint reuse).
     * A published snapshot is reused after its retained bytes are rehashed (by the bridge) and the live layer
     * matches it. A layer the game changed since retires the old snapshot (unreferenced; kept until a measured
     * shortage releases it) and takes a
     * fresh one, once per call. Transport cut before publication restarts in a new owned attempt.
     */
    private fun snapshotStage(journal: SessionJournal, apks: RunApks, enginePath: String,
                              run: RunStore.Run): Pair<File, JSONObject?> {
        val snapshot = File(journal.directory, "snapshot")
        val manifest = File(snapshot, "manifest.json")
        var retired = false
        while (true) {
            if (!snapshot.exists() && !Files.isSymbolicLink(snapshot.toPath())) takeSnapshot(journal, apks, enginePath, run)
            requireOwnedSnapshot(journal, run)
            try { validateLayer(manifest) } catch (changed: Throwable) {
                if (!gameChanged(changed) || retired) throw changed
                retired = true
                val runs = RunStore(context)
                val snapshotHash = ApkIdentity.digest(manifest)
                runs.requireSourceDownloads(run.id, snapshotHash)
                if (!runs.sourceDownloadsConfirmed(run.id, snapshotHash)) {
                    journal.record(JSONObject().put("waiting_reason", SOURCE_DOWNLOADS))
                    throw WaitingForUser("The game files changed; finish all in-game downloads before continuing")
                }
                report("Downloads confirmed; taking a fresh snapshot of the changed game files")
                retireSnapshot(journal, run)
                runs.consumeSourceDownloads(run.id)
                continue
            }
            // A download answer the layer no longer needs (it matches its snapshot) is spent here, so it never
            // carries over to a later, unrelated change of the same snapshot.
            RunStore(context).let { runs ->
                val kept = runs.load(run.id)
                if (kept.mayContinue && kept.sourceDownloads == "confirmed") runs.consumeSourceDownloads(run.id)
            }
            val identity = measureInputs(journal, apks, enginePath, run, manifest)
            if (identity != null) {
                val receipt = File(snapshot, ArtifactReceipts.NAME)
                val published = runCatching {
                    bridge("snapshot_checkpoint", enginePath, journal.directory.path, run.id, identity.toString(),
                        !receipt.exists())
                }
                if (published.isFailure) {
                    if (retired) throw checkNotNull(published.exceptionOrNull())
                    retired = true
                    report("The saved snapshot no longer matches its inputs; taking a fresh one")
                    retireSnapshot(journal, run)
                    continue
                }
            }
            journal.record(JSONObject().put("snapshot_ready", true))
            return manifest to identity
        }
    }

    /** A fresh owned transport: attempt persisted before bytes, rename intent persisted before publication. */
    private fun takeSnapshot(journal: SessionJournal, apks: RunApks, enginePath: String, run: RunStore.Run) {
        val saved = journal.snapshot().optString("snapshot_attempt")
        if (saved.isNotEmpty()) {
            // Transport or rename was cut: only that owned attempt's incomplete destination is removed.
            GameFilePolicy.session(saved)
            bridge("reset_checkpoint_attempt", enginePath, journal.directory.path, run.id, saved, "snapshot")
            journal.record(JSONObject().put("snapshot_attempt", "").put("snapshot_rename", false))
        }
        report("Measuring downloaded game data and required backup space")
        val estimate = JSONObject(device.estimateGameSnapshot())
        val budget = estimate.getLong("archive_budget")
        check(budget in 1..(8L * 1024 * 1024 * 1024)) { "Invalid snapshot estimate" }
        // The snapshot stays while the build adds its own files. Reserve both now, so a copy that fits is not
        // followed by a build that cannot, plus independent installer space for normal restore.
        requireSpace("measured snapshot, extraction, build and normal restore", budget,
            previousBuildEstimate(), apks.restoreBytes)
        operation(journal, "snapshot")
        val attempt = JSONObject(bridge("begin_snapshot_attempt", enginePath, journal.directory.path, run.id))
        val id = attempt.getString("attempt"); GameFilePolicy.session(id)
        val destination = File(journal.directory, "snapshot-attempts/$id/snapshot")
        check(File(attempt.getString("destination")).canonicalPath == destination.canonicalPath) { "Unexpected snapshot attempt" }
        journal.record(JSONObject().put("snapshot_attempt", id).put("snapshot_rename", false).put("snapshot_ready", false))
        report("Saving complete game data and Watchdog snapshot")
        streamSnapshot(enginePath, destination, budget)
        validateLayer(File(destination, "manifest.json"))
        journal.record(JSONObject().put("snapshot_rename", true))
        val snapshot = File(journal.directory, "snapshot")
        check(!snapshot.exists() && destination.renameTo(snapshot)) { "Cannot publish owned snapshot" }
        DurableFiles.syncDirectory(journal.directory)
        DurableFiles.syncDirectory(checkNotNull(destination.parentFile))
    }

    /** The canonical snapshot belongs to this run only through its saved attempt and rename intent. */
    private fun requireOwnedSnapshot(journal: SessionJournal, run: RunStore.Run) {
        val snapshot = File(journal.directory, "snapshot")
        RunStore.safe(context.filesDir.canonicalFile, snapshot, true)
        val saved = journal.snapshot()
        check(saved.optBoolean("snapshot_rename", false)) { "Snapshot has no rename ownership" }
        val id = saved.getString("snapshot_attempt"); GameFilePolicy.session(id)
        val owner = File(journal.directory, "snapshot-attempts/$id/attempt-owner.json")
        RunStore.safe(context.filesDir.canonicalFile, owner)
        val record = ArtifactReceipts.parse(owner.readBytes())
        check(record.getString("run_id") == run.id && record.getString("stage") == "snapshot") { "Snapshot owner differs" }
    }

    /**
     * Move an unusable canonical snapshot back under its own attempt, kept for diagnosis until a measured
     * shortage releases it ([releaseRetiredSnapshots]), and drop every checkpoint derived from it. Only a
     * consistent journal reaches here: the snapshot is not rollback material for any file change in flight.
     */
    private fun retireSnapshot(journal: SessionJournal, run: RunStore.Run) {
        check(!journal.dirtyPackages && !journal.hasMutationIntent && !journal.payloadVerified)
        val saved = journal.snapshot()
        val id = saved.getString("snapshot_attempt"); GameFilePolicy.session(id)
        val snapshot = File(journal.directory, "snapshot")
        val retired = File(journal.directory, "snapshot-attempts/$id/retired")
        check(!retired.exists() && snapshot.renameTo(retired)) { "Cannot retire the saved snapshot" }
        DurableFiles.syncDirectory(journal.directory)
        val history = saved.optJSONArray("retired_snapshots") ?: JSONArray()
        check(history.length() < 32) { "Too many retired snapshots" }
        journal.record(JSONObject().put("retired_snapshots", history.put(id)).put("snapshot_attempt", "")
            .put("snapshot_rename", false).put("snapshot_ready", false).put("build_attempt", "")
            .put("inputs_invalidated", saved.optInt("inputs_invalidated", 0) + 1))
        if (RunStore(context).load(run.id).inputIdentity != null) RunStore(context).invalidateInputs(run.id)
    }

    /**
     * The complete current identity. The live layer was just validated against the snapshot manifest, so
     * the manifest is the independently measured source set; the bridge rehashes the retained bytes.
     * A changed identity (engine, delta, APK) invalidates the saved one first; it is never rebound silently.
     */
    private fun measureInputs(journal: SessionJournal, apks: RunApks, enginePath: String, run: RunStore.Run,
                              manifest: File): JSONObject? {
        val files = ArtifactReceipts.parse(manifest.readBytes()).getJSONObject("files")
        val current = JSONObject()
        for (name in files.keys()) {
            val entry = files.getJSONObject(name)
            current.put(name, JSONObject().put("size", entry.getLong("bytes")).put("sha256", entry.getString("sha256")))
        }
        val target = run.target.json().put("provider", run.provider.key)
        val request = JSONObject().put("action", run.action).put("language", run.language).put("options", JSONObject())
        val readiness = JSONObject().put("live_layer", "validated_against_snapshot").put("game", "force_stopped")
        val producer = EngineAssets.producerIdentity(context)
        val measured = JSONObject(bridge("checkpoint_identity", enginePath, journal.directory.path, apks.buildApk.path,
            pristine.path, target.toString(), request.toString(), current.toString(), readiness.toString(),
            checkNotNull(run.preparation).toString(), producer?.toString() ?: "null"))
        val identity = measured.optJSONObject("identity") ?: return null
        val saved = RunStore(context).load(run.id).inputIdentity
        if (saved != null && ArtifactReceipts.identityKey(saved) != ArtifactReceipts.identityKey(identity)) {
            report("Inputs changed since the saved checkpoint; reusing only what still matches")
            RunStore(context).invalidateInputs(run.id)
            journal.record(JSONObject().put("inputs_invalidated", journal.snapshot().optInt("inputs_invalidated", 0) + 1))
        }
        RunStore(context).bindInputs(run.id, identity)
        return identity
    }

    /**
     * STAGED: a published build of exactly these inputs is reused with zero stage calls; anything else builds
     * in a fresh owned attempt after resetting only this run's incomplete, unreferenced attempts. The chosen
     * attempt is pinned in the journal, and its finalization plan sealed, before any game file is written.
     */
    private fun buildStage(journal: SessionJournal, apks: RunApks, enginePath: String, run: RunStore.Run,
                           identity: JSONObject?, remove: Boolean, reused: JSONObject? = null): File {
        val savedAttempt = journal.snapshot().optString("build_attempt")
        var built: JSONObject? = reused
        if (savedAttempt.isNotEmpty() && identity != null) {
            GameFilePolicy.session(savedAttempt)
            built = runCatching {
                JSONObject(bridge("inspect_build_checkpoint", enginePath, journal.directory.path, run.id, savedAttempt,
                    apks.buildApk.path, pristine.path, identity.toString()))
            }.onFailure { report("The saved build no longer matches its inputs; building again") }.getOrNull()
            if (built != null) report("Reusing the verified build from the interrupted run")
        }
        if (journal.phase == PatchPhase.SNAPSHOT_READY) journal.outcome(PatchPhase.BUILDING)
        if (built == null) {
            resetIncompleteBuilds(journal, enginePath, run)
            val updates = JSONObject().put("language", run.language)
            if (remove) {
                val copyBytes = bridge("removal_bytes", enginePath, pristine.path, journal.directory.path).toLong()
                updates.put("build_storage_check", requireSpace("original game files and normal restore", copyBytes,
                    apks.restoreBytes))
                report("Rebuilding the original game files from the pristine delta")
            } else {
                // With a kept pristine delta the estimate includes the build input's copy of the files it
                // names, so the check below reserves it before the build makes it.
                val estimate = JSONObject(bridge("estimate_snapshot_build", enginePath, journal.directory.path,
                    apks.buildApk.path, run.language, pristine.path))
                check(estimate.getInt("schema") == 2 && estimate.getBoolean("estimate_only"))
                val bytes = estimate.getLong("additional_bytes")
                check(bytes > 0) { "Invalid offline build storage estimate" }
                updates.put("build_storage_estimate", estimate)
                    .put("build_storage_check", requireSpace("offline build and normal restore", bytes, apks.restoreBytes))
                report("Building text and graphics from the verified private snapshot")
            }
            journal.record(updates)
            operation(journal, "build")
            built = try {
                // Refuses, before any game file is written, a layer it can neither rebuild nor read as pristine.
                JSONObject(bridge("build_checkpoint", enginePath, journal.directory.path, run.id, apks.buildApk.path,
                    apks.recoveryId, run.language, pristine.path, identity?.toString() ?: "null", remove))
            } catch (refusal: Exception) {
                awaitUser(journal, apks, enginePath, run, refusal)
                throw refusal
            }
            built.optJSONObject("summary")?.optJSONObject("pristine")?.let { PristineDelta.describe(it).forEach(report) }
        }
        val result = checkNotNull(built)
        val attempt = result.getString("attempt"); GameFilePolicy.session(attempt)
        journal.record(JSONObject().put("build_attempt", attempt).put("build_identity", identity ?: JSONObject.NULL)
            .put("remove", remove))
        val root = journal.resultRoot
        check(File(result.getString("result_root")).canonicalPath == root.canonicalPath) { "Unexpected build result" }
        val summary = result.getJSONObject("summary")
        PristineDelta.seal(context, journal, JSONObject(bridge("finalization_plan", enginePath, root.path, remove)))
        if (journal.phase == PatchPhase.BUILDING) {
            val updates = JSONObject().put("counts", JSONObject(bridge("result_counts", enginePath, summary.toString())))
            summary.optJSONArray("removed")?.let { updates.put("removed_count", it.length()) }
            journal.outcome(PatchPhase.STAGED, updates)
        }
        return root
    }

    /**
     * A build refusal that needs the game's own download rather than a retry. Damaged files: the exact plan is
     * measured and pinned and, by the user's decision of 2026-11-13, approved automatically, so the same run
     * goes on to delete it ([RedownloadApproved]). The loop guard ([RedownloadConsent.automaticAllowed]) holds
     * back a package already re-downloaded in this run: that plan waits for the user's review instead. A plan
     * that cannot be measured leaves the refusal as it is: nothing is deleted that is not bound to verified
     * inputs. The game still downloading after a Re-download the user said was finished: the action waits for
     * the download again, without a new approval.
     */
    private fun awaitUser(journal: SessionJournal, apks: RunApks, enginePath: String, run: RunStore.Run,
                          refusal: Exception) {
        val message = refusal.message.orEmpty()
        val runs = RunStore(context)
        if (StopCard.damagedFiles(message)) {
            val (id, plan) = try {
                planRedownload(journal, apks, enginePath, run, File(journal.directory, "snapshot/manifest.json"))
            } catch (error: Exception) {
                refusal.addSuppressed(error)
                report("Damaged game files found, but their Re-download could not be planned (${error.javaClass.simpleName})")
                return
            }
            pinRedownload(journal, run, id, plan, waiting = true)
            throw RedownloadApproved(approvedPlan(run, plan) ?: throw heldBack(run, plan))
        }
        val consent = runs.load(run.id).redownload
        if ((message.contains(StopCard.UPDATE_WAITING) || message.contains(StopCard.DOWNLOAD_UNFINISHED)) &&
            consent?.state == RedownloadConsent.DOWNLOADS_CONFIRMED) {
            runs.redownloadProgress(run.id, consent.planSha256, RedownloadConsent.DELETED)
            journal.record(JSONObject().put("waiting_reason", REDOWNLOAD_DOWNLOAD))
            throw WaitingForUser("The game has not finished downloading the re-downloaded files yet")
        }
    }

    /** Only this run's own unreferenced attempts without a receipt; the bridge refuses anything else. */
    private fun resetIncompleteBuilds(journal: SessionJournal, enginePath: String, run: RunStore.Run) {
        val referenced = journal.snapshot().optString("build_attempt")
        for (attempt in File(journal.directory, "build-attempts").listFiles().orEmpty()) {
            if (attempt.name == referenced || !attempt.isDirectory || Files.isSymbolicLink(attempt.toPath())) continue
            if (File(attempt, "result/${ArtifactReceipts.NAME}").exists()) continue
            runCatching { GameFilePolicy.session(attempt.name)
                bridge("reset_checkpoint_attempt", enginePath, journal.directory.path, run.id, attempt.name, "staged")
            }.onFailure { android.util.Log.w("HokAceStorage", "Kept an unowned or published build attempt", it) }
        }
    }

    private fun same(left: Any?, right: Any?) = ArtifactReceipts.canonical(left) == ArtifactReceipts.canonical(right)

    /** Complete provenance is measured outside the short Stop/completion serialization section. */
    private fun completionRecord(journal: SessionJournal): JSONObject? {
        val identity = journal.snapshot().optJSONObject("build_identity") ?: return null
        val stage = ArtifactReceipts.verify(journal.resultRoot, identity = identity, stage = "staged")
        check(stage.getString("run_id") == journal.runId)
        val manifest = GameFileTransaction(journal, device).verifyAppliedManifest()
        val expected = ArtifactReceipts.parse(DurableFiles.readCommitted(manifest))
        val normal = journal.rootInstalled ?: store.verify(journal.recoveryId)
        val run = RunStore(context).load(checkNotNull(journal.runId))
        return JSONObject().put("schema", 1).put("run_id", run.id).put("identity", identity)
            .put("input_key", ArtifactReceipts.identityKey(identity)).put("expected", expected)
            .put("installed", normal.json()).put("delta", PristineDelta.activeIdentity(context))
            .put("build_receipt", ArtifactReceipts.fileIdentity(File(journal.resultRoot, ArtifactReceipts.NAME)))
            .put("summary", ArtifactReceipts.parse(DurableFiles.readCommitted(File(journal.resultRoot, "bridge-summary.json"))))
            .put("counts", journal.snapshot().opt("counts") ?: JSONObject.NULL)
    }

    private fun writeCompletion(journal: SessionJournal, record: JSONObject) {
        val path = File(journal.directory, "completion-receipt.json")
        for (name in listOf(path.name, path.name + ".bak", path.name + ".new"))
            check(!Files.isSymbolicLink(File(journal.directory, name).toPath()))
        val storage = AtomicFile(path)
        val bytes = ArtifactReceipts.canonical(record).toByteArray(Charsets.UTF_8)
        val stream = storage.startWrite()
        try { stream.write(bytes); stream.fd.sync(); storage.finishWrite(stream); DurableFiles.syncDirectory(journal.directory) }
        catch (error: Throwable) { storage.failWrite(stream); throw error }
        check(DurableFiles.readCommitted(path).contentEquals(bytes))
    }

    private fun finishFinalized(journal: SessionJournal) {
        val record = completionRecord(journal)
        RunStore(context).finishVerified(checkNotNull(journal.runId), journal) { stopped ->
            record?.let { writeCompletion(journal, it.put("outcome", if (stopped) "stopped_consistent" else "verified_complete")) }
        }
    }

    /** Validate actual current full bytes before adopting old output into this Start's owned copy. */
    private fun reuseCompletion(journal: SessionJournal, apks: RunApks, enginePath: String,
                                run: RunStore.Run, identity: JSONObject): JSONObject? {
        if (run.action != "translate") return null // Remove invalidates translation reuse.
        val started = android.os.SystemClock.elapsedRealtime()
        for (old in SessionJournal.history(sessions).filter { it.id != journal.id && it.phase == PatchPhase.COMPLETE }) {
            val marker = File(old.directory, "completion-receipt.json")
            if (!marker.isFile || Files.isSymbolicLink(marker.toPath())) continue
            val candidate = runCatching {
                val priorRun = RunStore(context).load(checkNotNull(old.runId))
                check(priorRun.lifecycle == "complete" && !priorRun.stopRequested && !old.layerUnconfirmed)
                val saved = ArtifactReceipts.parse(DurableFiles.readCommitted(marker))
                check(saved.getInt("schema") == 1 && saved.getString("run_id") == old.runId &&
                    saved.getString("outcome") == "verified_complete")
                val input = saved.getJSONObject("identity")
                for (key in listOf("target", "request", "translation", "producer")) check(same(input.get(key), identity.get(key)))
                check(same(input, old.snapshot().getJSONObject("build_identity")) &&
                    saved.getString("input_key") == ArtifactReceipts.identityKey(input))
                val priorApks = runApks(priorRun) // Full preparation/recovery APK read-back.
                check(ArtifactReceipts.fileIdentity(priorApks.buildApk).let {
                    same(it, input.getJSONObject("apks").getJSONObject("normal")) && same(it, ArtifactReceipts.fileIdentity(apks.buildApk))
                })
                val priorPreparation = checkNotNull(priorRun.preparation)
                // Retain/read the actual original source; a normalized APK never substitutes for it.
                val sourceIdentity = if (old.root) priorApks.installed!! else ApkIdentity.fromJson(priorPreparation.getJSONObject("source"))
                val source = if (sourceIdentity == (priorApks.installed ?: store.verify(priorApks.recoveryId))) priorApks.buildApk
                    else File(RunStore.privateRoot(context), "preparations/${priorPreparation.getString("id")}/original.apk")
                check(ApkIdentity.read(context, source) == sourceIdentity)
                if (sourceIdentity.sha256 != (priorApks.installed ?: store.verify(priorApks.recoveryId)).sha256)
                    InstalledGameVerifier.verifyManifestOnlySource(source, priorApks.buildApk)
                check(same(saved.get("installed"), (apks.installed ?: store.verify(apks.recoveryId)).json()))
                val stage = ArtifactReceipts.verify(old.resultRoot, identity = input, stage = "staged")
                check(stage.getString("run_id") == old.runId && same(saved.get("build_receipt"),
                    ArtifactReceipts.fileIdentity(File(old.resultRoot, ArtifactReceipts.NAME))))
                val manifest = GameFileTransaction(old, device).verifyAppliedManifest()
                check(same(saved.get("expected"), ArtifactReceipts.parse(DurableFiles.readCommitted(manifest))))
                check(same(saved.get("summary"), ArtifactReceipts.parse(DurableFiles.readCommitted(File(old.resultRoot, "bridge-summary.json")))) &&
                    same(saved.get("counts"), old.snapshot().get("counts")))
                check(same(saved.get("delta"), PristineDelta.activeIdentity(context)))
                PristineDelta.finalize(context, old) // Re-reads sealed final delta/record, independent of engine.
                validateLayer(manifest) // Fresh live audit under required access; no saved receipt attests the phone.
                val artifacts = stage.getJSONObject("artifacts")
                val bytes = artifacts.keys().asSequence().sumOf { artifacts.getJSONObject(it).getLong("size") }
                adoptingSessions += old.id
                try {
                    requireSpace("verified output copy and normal restore", bytes, apks.restoreBytes,
                        artifacts.keys().asSequence().maxOfOrNull { artifacts.getJSONObject(it).getLong("size") } ?: 0L)
                } finally { adoptingSessions -= old.id }
                old
            }.getOrNull() ?: continue
            checkpoint()
            val copied = JSONObject(bridge("copy_completed_checkpoint", enginePath, journal.directory.path, run.id,
                apks.buildApk.path, pristine.path, identity.toString(), candidate.resultRoot.path, ApkIdentity.digest(marker)))
            journal.record(JSONObject().put("completion_reuse", JSONObject().put("source_run", candidate.runId)
                .put("validation_and_copy_ms", android.os.SystemClock.elapsedRealtime() - started)
                .put("skipped", JSONArray(listOf("pristine_reconstruction", "translation_build")))))
            report("Reusing verified completed output; pristine reconstruction and translation build skipped")
            checkpoint()
            return copied
        }
        return null
    }

    /** NORMAL_VERIFIED → FINALIZED: idempotent byte-only delta promotion/removal, then the terminal record. */
    private fun finalizeAndComplete(journal: SessionJournal) {
        val plan = journal.snapshot()
        PristineDelta.finalize(context, journal)
        report(if (plan.optBoolean("remove", false)) "The original game files are back; no pristine delta is kept"
            else "Kept the pristine delta for the next language switch")
        finishFinalized(journal)
    }

    /**
     * Resolve the saved action from its session, never from a status projection. COMPLETE resolves it; a
     * consistent CANCELLED resolves it only after an explicit Stop (an unexpected interruption keeps it).
     */
    private fun settle(journal: SessionJournal) {
        val id = journal.runId ?: return
        runCatching {
            val runs = RunStore(context)
            val run = runs.load(id)
            if (run.lifecycle in setOf("complete", "stopped")) return
            when {
                journal.phase == PatchPhase.COMPLETE -> {
                    journal.recoveryRequired("Completion publication needs a fresh live audit before resolution")
                    report("Completion publication is unfinished; recovery must audit current game bytes")
                }
                journal.phase == PatchPhase.CANCELLED && run.stopRequested -> {
                    journal.record(JSONObject().put("stopped", true))
                    runs.resolve(id)
                    report("Stopped safely; the game files and app are consistent")
                }
            }
        }.onFailure { report("The saved action stays open until its records can be resolved (${it.javaClass.simpleName})") }
    }

    private fun resultAction(run: RunStore.Run) = if (run.action == "translate") "patch" else run.action

    private fun completedResult(journal: SessionJournal, run: RunStore.Run): JSONObject =
        WorkerStatus.afterStop(journal.terminalResult(), journal.snapshot()).put("action", resultAction(run)).put("run", run.id)

    /** A retained immutable inode keeps the session independently addressable without another 2 GB copy. */
    private fun linkSessionAccess(journal: SessionJournal, accessApk: File, access: ApkIdentity, restoreBytes: Long) {
        val sessionAccess = File(journal.directory, "access.apk")
        try {
            check(accessApk.setReadOnly()) { "Cannot protect the access APK" }
            try { android.system.Os.link(accessApk.path, sessionAccess.path) }
            catch (error: android.system.ErrnoException) {
                check(accessApk.canonicalPath.startsWith(context.filesDir.canonicalPath + File.separator)) {
                    "Access APK reference leaves private storage"
                }
                android.system.Os.symlink(accessApk.canonicalPath, sessionAccess.path)
            }
            DurableFiles.syncDirectory(journal.directory)
        } catch (error: android.system.ErrnoException) {
            requireSpace("access APK copy, install and normal restore", access.bytes, maxOf(access.bytes, restoreBytes))
            accessApk.inputStream().use { input -> sessionAccess.outputStream().use {
                input.copyTo(it, 1024 * 1024); it.fd.sync()
            } }
            check(sessionAccess.setReadOnly()) { "Cannot protect session access APK" }
            DurableFiles.syncDirectory(journal.directory)
        }
    }

    /** Legacy sessions only; a schema-2 session's bulk is retained by [releaseResolvedSessions]' policy. */
    private fun releaseIfResolved(journal: SessionJournal) {
        if (journal.runId != null) return
        if (journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) return
        // Runs in finally: never let cleanup or its message replace the run's own outcome.
        runCatching {
            val freed = releaseSession(journal.directory)
            if (freed > 0) report("Freed ${StorageBudget.freeSpaceLabel(freed)} of temporary patch files")
        }.onFailure { android.util.Log.w("HokAceStorage", "Resolved session files could not be removed", it) }
    }

    /**
     * <root> is whether the worker runs as root; a run recovers only through the kind of provider that
     * started it. Safety recovery only: it never continues a saved action, and needs no Python unless a
     * legacy session still holds an unpromoted delta.
     */
    @JvmOverloads fun recover(sessionId: String, root: Boolean = false) = exclusive {
        GameFilePolicy.session(sessionId)
        val journal = SessionJournal.load(File(sessions, sessionId))
        check(journal.root == root) { OTHER_PROVIDER }
        if (journal.phase == PatchPhase.COMPLETE && journal.runId?.let { RunStore(context).load(it).lifecycle != "complete" } == true)
            journal.recoveryRequired("Completion publication was interrupted; auditing current game bytes")
        check(journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) { "Session already resolved" }
        activeJournal.set(journal)
        try { recoverLocked(journal) } catch (error: Throwable) {
            journal.recoveryRequired(error.message ?: "Recovery interrupted")
            restoreNormalAfterFailure(journal, error)
            throw error
        }
        keepResolvedDelta(journal)
        releaseIfResolved(journal)
        settle(journal)
        WorkerStatus.afterStop(journal.terminalResult(), journal.snapshot())
    }

    /** A legacy recovery that resolves a run keeps its pristine delta now, not only at the next patch run. */
    private fun keepResolvedDelta(journal: SessionJournal) {
        if (journal.runId != null) return // Finalized byte-only before COMPLETE; no engine for saved bytes.
        if (journal.phase != PatchPhase.COMPLETE && !journal.layerUnconfirmed) return
        if (!File(journal.directory, PristineDelta.SESSION_DELTA).isFile) return
        runCatching { promoteLegacySessionDelta { EngineAssets.prepare(context).path } }.onFailure {
            report("Could not keep the pristine delta yet (${it.javaClass.simpleName}); the next patch keeps it")
        }
    }

    /**
     * Free up space without starting a patch: what a run frees before its first budget, plus each
     * unfinished run that left no game file mid-change, closed by [SessionJournal.closeUnconfirmed]
     * once the normal APK is verified installed. Pristine deltas, the saved normal APKs and this game
     * version's prepared APKs stay unless <removeSavedApks>; see [ApkPreparation.removeSaved]. A run that
     * stopped mid-change is refused: it needs recovery. An unresolved saved action pins everything.
     */
    @JvmOverloads fun freeSpace(removeSavedApks: Boolean = false): JSONObject = exclusive {
        check(RunStore(context).pending().isEmpty()) { "Stop or finish the authorized action before freeing space" }
        EmergencyRestoreStore(context).requireResolved()
        check(FirstSetupJournal.pending(context).isEmpty()) { "Finish or recover first-time setup before freeing space" }
        val before = context.filesDir.usableSpace
        var installed: ApkIdentity? = null
        val unfinished = SessionJournal.pending(sessions)
        for (journal in unfinished) check(!journal.dirtyPackages) {
            "Restore the interrupted patch first: it stopped while changing game files"
        }
        for (journal in unfinished) {
            report("Checking the installed normal game app")
            val normal = journal.rootInstalled ?: store.verify(journal.recoveryId)
            check(installed(normal)) {
                "Restore the interrupted patch first: the normal game app is not installed"
            }
            if (!journal.root) installed = normal

            journal.closeUnconfirmed("Closed by Free up space; the game files were not checked again")
            report("Closed an interrupted run that left no game file half-changed")
        }
        if (sessions.listFiles().orEmpty().any { File(it, PristineDelta.SESSION_DELTA).isFile }) {
            promoteLegacySessionDelta { EngineAssets.prepare(context).path }
        }
        releaseResolvedSessions(keepNewest = false)
        StorageBudget.releaseReplacedGameApks(device, report)
        val known = installed ?: File(RunStore.privateRoot(context), "recovery").listFiles().orEmpty()
            .filter { it.isDirectory && it.name.matches(Regex("[0-9a-f]{64}")) }
            .sortedByDescending { it.lastModified() }.asSequence()
            .mapNotNull { folder -> runCatching { store.verify(folder.name) }.getOrNull()?.takeIf { installed(it) } }
            .firstOrNull()
        var removed = false
        if (removeSavedApks) {
            if (known == null) report("Kept the saved game apps: the installed game app is not one of them")
            else removed = ApkPreparation(context).removeSaved(known, report)
        } else if (known != null) runCatching { ApkPreparation(context).releaseUnneeded(known, null, report) }
            .onFailure { report("Could not remove unneeded saved APKs (${it.javaClass.simpleName})") }
        val freed = (context.filesDir.usableSpace - before).coerceAtLeast(0L)
        JSONObject().put("status", "space_freed").put("action", "free_space").put("freed_bytes", freed)
            .put("closed_runs", unfinished.size).put("free_bytes", context.filesDir.usableSpace)
            .put("removed_saved_apks", removed)
    }

    /**
     * A blocked install failed recovery's normal restore, the emergency restore then verified the normal APK,
     * and no game file is mid-change or written: the run is over, and it stopped for the reason it raised.
     * Left open, its refusal (a stuck update, say) reads as recovery and never offers Re-download
     * (lab notebook, 2026-11-06). A run with a verified payload stays open for recovery's audit.
     */
    private fun closeIfNothingToRecover(journal: SessionJournal) {
        if (journal.dirtyPackages || journal.payloadVerified) return
        val blocked = journal.snapshot().optString("last_error")
        runCatching {
            journal.closeUnconfirmed("Normal APK verified after a blocked install")
            report("No game file is mid-change; the run is closed")
        }.onFailure { journal.recoveryRequired(blocked) }
    }

    /** Whether the normal APK is now verified installed. Root never replaced it, so it restores nothing. */
    private fun restoreNormalAfterFailure(journal: SessionJournal, cause: Throwable): Boolean {
        // Root never replaced the game app, so there is nothing to restore before package recovery.
        if (journal.root) return false
        try {
            val normal = store.verify(journal.recoveryId)
            check(device.asBinder().isBinderAlive) { "Worker disconnected before normal APK restoration" }
            if (!installed(normal)) {
                val access = ApkIdentity.read(context, File(journal.directory, "access.apk"))
                check(installed(access)) { INSTALLED_CHANGED }
                requireSpace("emergency normal APK restore", normal.bytes)
                journal.runId?.let { RunStore(context).beginSafetyAttempt(it, "recovery_emergency_normal") }
                journal.beginRecoveryNormal(normal)
                report("Restoring normal APK; package recovery remains required")
                ParcelFileDescriptor.open(store.normal(normal.sha256), ParcelFileDescriptor.MODE_READ_ONLY).use {
                    device.replaceGameApk(it, normal.bytes)
                }
                verifyInstalled(normal)
            }
            journal.recoveryNormalVerified()
            report("Normal APK verified; do not launch until package recovery is resolved")
            return true
        } catch (restore: Throwable) {
            cause.addSuppressed(restore)
            journal.recoveryRequired("${reason(cause)}; normal APK restore: ${reason(restore)}")
            return false
        }
    }

    /**
     * Under root ([SessionJournal.root]) nothing is installed: the audit and the rollback read and write the
     * game's files as they are, and the run closes once the game app it left in place is verified (ADR 0007).
     * Uses only saved bytes, saved APKs and the journal: no Python engine or codec.
     */
    private fun recoverLocked(journal: SessionJournal) {
        check(journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) { "Session already resolved" }
        var unconfirmed: String? = null
        val rootInstalled = journal.rootInstalled
        val normal = rootInstalled ?: store.verify(journal.recoveryId)
        val restoreBytes = if (rootInstalled != null) 0L else normal.bytes
        device.forceStopGame()
        if (rootInstalled != null) verifyInstalled(rootInstalled)
        if (rootInstalled == null) {
            val access = ApkIdentity.read(context, File(journal.directory, "access.apk"))
            check(installed(normal) || installed(access)) { INSTALLED_CHANGED }
            StorageBudget.releaseReplacedGameApks(device, report)
        }
        val transaction = if (journal.dirtyPackages) GameFileTransaction(journal, device) else null
        val forward = !journal.dirtyPackages && journal.snapshot().optBoolean("patch_payload_verified", false)
        val applied = if (forward) GameFileTransaction(journal, device).verifyAppliedManifest() else null
        // Refusing damaged originals must retain the prior unresolved package-write intent.
        if (transaction != null) report("Checking the original game files")
        val originals = transaction?.verifyOriginals()
        if (originals != null) {
            transaction.prepareRollback(originals)
            // A metric only: a legacy (schema-1) journal records no checkpoints and must still roll back.
            if (journal.runId != null)
                journal.record(JSONObject().put("recovery_original_hash_passes", transaction.originalHashPasses))
        }
        journal.outcome(PatchPhase.RESTORING)
        if (applied != null) {
            // A durable earlier verification cannot establish the layer after a restart or update.
            if (rootInstalled == null) {
                val accessFile = File(journal.directory, "access.apk")
                val access = ApkIdentity.read(context, accessFile)
                check(access.debuggable && access.certificateSha256 == normal.certificateSha256 &&
                    access.versionCode == normal.versionCode && access.versionName == normal.versionName) {
                    "Retained access and recovery APK identities differ"
                }
                requireSpace("applied-layer recovery audit and normal restore", maxOf(normal.bytes, access.bytes))
                if (!installed(access)) {
                    check(installed(normal)) { INSTALLED_CHANGED }
                    journal.runId?.let { RunStore(context).beginSafetyAttempt(it, "recovery_access_audit") }
                    install(journal, accessFile, true, PatchPhase.RESTORING)
                }
            }
            // The game may have run since the write was verified: it refills Watchdog, and may repair or
            // update packages. A clean run has nothing to roll back, so a changed layer closes it
            // unconfirmed rather than leaving it unrecoverable. Any other audit failure still stops here.
            try { validateLayer(applied) } catch (error: IllegalStateException) {
                val message = error.message.orEmpty()
                if (GAME_CHANGED.none { message.contains(it) }) throw error
                unconfirmed = message
                report("The game changed its files after the translation was written; " +
                    "closing the run without checking them again")
            }
        }
        if (transaction != null) {
            val files = checkNotNull(originals).files()
            val largest = files.keys().asSequence().map { files.getJSONObject(it).getLong("bytes") }.maxOrNull() ?: 0L
            if (rootInstalled == null) {
                val access = ApkIdentity.read(context, File(journal.directory, "access.apk"))
                requireSpace("complete rollback and normal restore", maxOf(normal.bytes, access.bytes), largest)
                if (!installed(access)) {
                    check(installed(normal)) { INSTALLED_CHANGED }
                    journal.runId?.let { RunStore(context).beginSafetyAttempt(it, "recovery_rollback_access") }
                    install(journal, File(journal.directory, "access.apk"), true, PatchPhase.RESTORING)
                }
            } else requireSpace("complete rollback", largest)
            report("Restoring the original game files")
            transaction.rollback(checkNotNull(originals)) { source -> requireSpace("rollback file and normal restore", restoreBytes, source.length()) }
        }
        // A failed offline build may fill storage while the already-verified normal APK stays
        // installed. Verify that identity before spending another APK-sized installer allocation.
        val completion = if (unconfirmed != null) PatchPhase.CANCELLED else journal.recoveryCompletionPhase
        fun closing() = JSONObject().apply { unconfirmed?.let { put("layer_unconfirmed", it.take(4096)) } }
        fun finish() {
            if (journal.runId != null && journal.payloadVerified) {
                journal.outcome(PatchPhase.RESTORING, JSONObject().put("normal_verified", true)
                    .put("final_normal_verified", true))
                // Required pristine knowledge must settle even after Stop/unconfirmed recovery.
                // Failure stays actionable and pins the attempt; it cannot close as consistent.
                PristineDelta.finalize(context, journal)
            }
            val stopped = journal.runId?.let { RunStore(context).load(it).stopRequested } == true
            if (journal.runId != null && completion == PatchPhase.COMPLETE) {
                finishFinalized(journal)
                return
            }
            journal.outcome(if (stopped) PatchPhase.CANCELLED else completion,
                closing().put("normal_verified", true).put("stopped", stopped))
        }
        if (rootInstalled != null) {
            report("Checking the installed game app")
            verifyInstalled(rootInstalled)
            finish()
            report("Game app verified; interrupted session recovered")
            return
        }
        val alreadyNormal = installed(normal)
        if (alreadyNormal) {
            finish()
            report("Normal game APK verified; interrupted session recovered")
            return
        }
        val access = ApkIdentity.read(context, File(journal.directory, "access.apk"))
        check(installed(access)) { INSTALLED_CHANGED }
        requireSpace("normal APK restore", normal.bytes)
        journal.runId?.let { RunStore(context).beginSafetyAttempt(it, "recovery_normal_restore") }
        install(journal, store.normal(normal.sha256), false, PatchPhase.RESTORING, updates = closing())
        finish()
        report("Normal game APK verified; interrupted session recovered")
    }
}
