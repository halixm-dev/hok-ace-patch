package dev.halixm.hokacepatcher

import android.content.Context
import android.os.ParcelFileDescriptor
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.io.RandomAccessFile
import java.nio.file.Files
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import org.json.JSONObject

/** Serialize snapshot/build/apply and recover complete file sets before restoring the normal APK. */
class PatchCoordinator @JvmOverloads constructor(
    private val context: Context,
    private val device: IPrivilegedDeviceService,
    private val report: (String) -> Unit,
    private val installedVerifier: InstalledApkVerifier? = null,
) {
    /** Injectable only in-process; the application always uses the independent installed verifier. */
    fun interface InstalledApkVerifier { fun verify(expected: ApkIdentity) }
    private val store = RecoveryStore(context)
    private val sessions = File(context.filesDir, "sessions")
    /** The pristine delta and the staged-hash record: outside sessions/, so no release reclaims them. */
    private val pristine = PristineDelta.directory(context)
    private val cancelled = AtomicBoolean(false)
    private val activeJournal = AtomicReference<SessionJournal?>(null)

    fun cancel() { cancelled.set(true) }

    private companion object {
        /** `validateGameSnapshot`'s reasons for a layer the game itself changed. */
        val GAME_CHANGED = listOf("Game file set changed", "Game file changed: ")
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

    fun interrupted(reason: String) {
        cancelled.set(true)
        activeJournal.get()?.let { journal ->
            if (journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) journal.recoveryRequired(reason)
        }
    }

    private fun checkpoint() {
        check(!cancelled.get()) { "Patch cancelled; restoring verified originals" }
        check(device.asBinder().isBinderAlive) { "Shizuku service disconnected" }
    }

    private fun bridge(name: String, vararg arguments: Any): String {
        if (!Python.isStarted()) Python.start(AndroidPlatform(context))
        return DiagnosticTrace.timed("engine", name) {
            Python.getInstance().getModule("android_bridge").callAttr(name, *arguments).toString()
        }
    }

    private fun requireSpace(phase: String, vararg allocations: Long) =
        StorageBudget.requireAvailable(context.filesDir, phase, *allocations)

    /**
     * A resolved session keeps its journal and small receipts. Its game-data copy, build work, staged
     * packages and APK links are the bulk of a run (about twice the downloaded data) and are never read
     * again: rollback and forward recovery only ever use an unresolved session's.
     */
    private fun releaseSession(directory: File): Long {
        var freed = 0L
        // The session's pristine delta stays until a run promotes or discards it (promoteSessionDelta).
        for (name in listOf("snapshot.tar", "access.apk", "normal.apk", "game", "work", PristineDelta.BUILD_COPY)) {
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
     * Coordinator lock held. Makes the newest completed session's pristine delta the patcher's own, then
     * discards every session delta. A run promotes its own as soon as it completes; this catches one
     * whose last step was finished by recovery. A delta older than the newest completed session no
     * longer describes the phone and is never promoted. A run closed with its payload verified but its
     * layer unconfirmed counts as completed here: the delta records pristine bytes that run overwrote,
     * and each file's entry applies only while that file still holds the staged bytes it records.
     */
    private fun promoteSessionDelta(enginePath: String) {
        val completed = sessions.listFiles().orEmpty()
            .filter { it.isDirectory && !Files.isSymbolicLink(it.toPath()) }
            .mapNotNull { runCatching { SessionJournal.load(it) }.getOrNull() }
            .filter { it.phase == PatchPhase.COMPLETE || it.layerUnconfirmed }
        val newest = completed.maxByOrNull { it.snapshot().getLong("created_ms") } ?: return
        val delta = File(newest.directory, PristineDelta.SESSION_DELTA)
        if (delta.isFile) {
            runCatching {
                val kept = JSONObject(bridge("keep_delta", enginePath, newest.directory.path, pristine.path))
                val files = kept.getInt("files")
                report(if (files > 0) "Kept a pristine delta of $files files for the next language switch"
                       else "The game files are untranslated; no pristine delta is kept")
            }.onFailure { report("Could not keep the pristine delta (${it.javaClass.simpleName}); " +
                "switching languages will need the game's data cleared") }
        }
        for (journal in completed) runCatching { File(journal.directory, PristineDelta.SESSION_DELTA).delete() }
    }

    /** Coordinator lock held. A damaged journal is left for recovery and export rather than guessed at. */
    private fun releaseResolvedSessions() {
        var freed = 0L
        for (directory in sessions.listFiles().orEmpty()) {
            if (!directory.isDirectory || Files.isSymbolicLink(directory.toPath())) continue
            val journal = runCatching { SessionJournal.load(directory) }.getOrNull() ?: continue
            if (journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) continue
            freed += runCatching { releaseSession(directory) }.getOrElse {
                report("Could not remove some files of an earlier run (${it.javaClass.simpleName})"); 0L
            }
        }
        if (freed > 0) report("Freed ${StorageBudget.freeSpaceLabel(freed)} of files left by earlier runs")
    }

    private fun <T> exclusive(action: () -> T): T {
        DurableFiles.createDirectories(sessions)
        RandomAccessFile(File(sessions, "coordinator.lock"), "rw").use { file ->
            file.channel.use { channel ->
                val lock = checkNotNull(channel.tryLock()) { "Another patch or recovery is running" }
                lock.use { return action() }
            }
        }
    }

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

    fun verifyRecoveryInstalled(normalId: String) { exclusive { verifyInstalled(store.verify(normalId)) } }

    private fun validateLayer(manifest: File) {
        ParcelFileDescriptor.open(manifest, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.validateGameSnapshot(it)
        }
    }

    /**
     * Re-download damaged files, from the snapshot onwards: delete every file of each translated package
     * the game's update could not patch, clear Watchdog, and restore the normal APK. The game downloads
     * those packages again on its next launch. The snapshot is the rollback, as for a patch: an
     * interrupted run writes the deleted files back.
     */
    private fun redownloadLocked(journal: SessionJournal, transaction: GameFileTransaction, enginePath: String,
                                 normalId: String, normal: ApkIdentity): JSONObject {
        journal.outcome(PatchPhase.BUILDING, JSONObject().put("redownload", true))
        report("Finding the package files the game update could not change")
        // Refuses, before any game file is changed, a phone whose update is not stuck on translated files.
        val summary = JSONObject(bridge("plan_redownload", enginePath, journal.directory.path, pristine.path))
        journal.outcome(PatchPhase.STAGED)
        val hashes = JSONObject(File(journal.directory, "staged-hashes.json").readText())
        transaction.verifyOriginals()
        hashes.keys().asSequence().forEach { GameFilePolicy.validate("packages/$it", writable = true) }
        requireSpace("normal restore", normal.bytes)
        checkpoint()
        device.forceStopGame()
        validateLayer(File(journal.directory, "snapshot/manifest.json"))
        // Kept before the first deletion: until the game downloads the packages again, a patch would read
        // a layer without them. A rollback puts them back, and the next run then drops the record.
        bridge("keep_redownload", enginePath, journal.directory.path, pristine.path)
        journal.outcome(PatchPhase.APPLYING)
        for (name in hashes.keys().asSequence().sorted()) {
            checkpoint()
            report("Deleting package file $name")
            transaction.delete("packages/$name", hashes.getString(name))
        }
        checkpoint()
        transaction.finishDeletion()
        install(journal, store.normal(normalId), false, PatchPhase.COMPLETE)
        return summary
    }

    /**
     * Existing converted installs only. Official-signature conversion requires a separate consent flow.
     * <remove> is Remove translation: the build step stages the rebuilt pristine files instead of a
     * translation, and everything else, the write-back and its rollback included, is the patch run's.
     * <redownload> is Re-download damaged files ([redownloadLocked]).
     */
    @JvmOverloads fun run(normalId: String, accessApk: File, sourceIdentity: ApkIdentity? = null,
                          remove: Boolean = false, redownload: Boolean = false): JSONObject = exclusive {
        check(!(remove && redownload)) { "Remove and Re-download are separate runs" }
        EmergencyRestoreStore(context).requireResolved()
        val unfinished = SessionJournal.pending(sessions)
        check(unfinished.isEmpty()) { "Recover the unfinished session before starting another patch" }
        check(FirstSetupJournal.pending(context).isEmpty()) { "Finish or recover first-time setup before starting a patch" }
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
        val engine = EngineAssets.prepare(context)
        bridge("engine_preflight", engine.path)
        // Read once: the whole run builds one language even if the picker changes meanwhile.
        val language = PatchLanguage.current(context)
        verifyInstalled(installedSource)
        promoteSessionDelta(engine.path)
        // Space the patch can reclaim goes before the first budget, so that budget is not short by it.
        releaseResolvedSessions()
        runCatching { ApkPreparation(context).releaseUnneeded(installedSource, accessApk.parentFile?.parentFile, report) }
            .onFailure { report("Could not remove unneeded saved APKs (${it.javaClass.simpleName})") }
        StorageBudget.releaseReplacedGameApks(device, report)
        requireSpace("APK install and normal restore", maxOf(access.bytes, normal.bytes))
        checkpoint()
        val journal = SessionJournal.create(sessions, normalId, engine.name)
        activeJournal.set(journal)
        report(when {
            redownload -> "Re-downloading damaged game files"
            remove -> "Removing the translation"
            else -> "Language: ${PatchLanguage.name(language)}"
        })
        val transaction = GameFileTransaction(journal, device)
        val metrics = RunMetrics(context, File(journal.directory, "resource-metrics.json"))
        var metricStatus = "interrupted"
        try {
            val sessionAccess = File(journal.directory, "access.apk")
            try {
                // A retained immutable inode keeps the session independently addressable without another 2 GB copy.
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
                requireSpace("access APK copy, install and normal restore", access.bytes, maxOf(access.bytes, normal.bytes))
                accessApk.inputStream().use { input -> sessionAccess.outputStream().use {
                    input.copyTo(it, 1024 * 1024); it.fd.sync()
                } }
                check(sessionAccess.setReadOnly()) { "Cannot protect session access APK" }
                DurableFiles.syncDirectory(journal.directory)
            }
            checkpoint()
            device.forceStopGame()
            // install() reads the session copy and requires it to be the access APK checked above.
            install(journal, File(journal.directory, "access.apk"), true, PatchPhase.SNAPSHOT_ACCESS_INSTALLED, access)
            report("Measuring downloaded game data and required backup space")
            val snapshotEstimate = JSONObject(device.estimateGameSnapshot())
            val snapshotBudget = snapshotEstimate.getLong("archive_budget")
            check(snapshotBudget in 1..(8L * 1024 * 1024 * 1024)) { "Invalid snapshot estimate" }
            // The snapshot streams straight into its extraction, which then stays while the build adds
            // its own files. Reserve both now, so a copy that fits is not followed by a build that cannot,
            // plus independent installer space for normal restore.
            requireSpace("measured snapshot, extraction, build and normal restore", snapshotBudget,
                previousBuildEstimate(), normal.bytes)
            report("Saving complete game data and Watchdog snapshot")
            streamSnapshot(engine.path, File(journal.directory, "snapshot"), snapshotBudget)
            validateLayer(File(journal.directory, "snapshot/manifest.json"))
            journal.outcome(PatchPhase.SNAPSHOT_READY)
            // The access APK stays installed until the translation is written, as on Windows: the game
            // must stay closed throughout, and one install pair less is minutes less on a slow phone.
            checkpoint()
            if (redownload) {
                val result = redownloadLocked(journal, transaction, engine.path, normalId, normal)
                metricStatus = "complete"
                return@exclusive result
            }
            val summary = if (remove) {
                val copyBytes = bridge("removal_bytes", engine.path, pristine.path, journal.directory.path).toLong()
                val space = requireSpace("original game files and normal restore", copyBytes, normal.bytes)
                journal.outcome(PatchPhase.BUILDING, JSONObject().put("build_storage_check", space)
                    .put("remove", true))
                report("Rebuilding the original game files from the pristine delta")
                // Refuses, before any game file is written, a layer it cannot rebuild.
                JSONObject(bridge("build_removal", engine.path, journal.directory.path, pristine.path))
            } else {
                // With a kept pristine delta the estimate includes the build input's copy of the files it
                // names, so the check below reserves it before the build makes it.
                val buildEstimate = JSONObject(bridge("estimate_snapshot_build", engine.path,
                    journal.directory.path, store.normal(normalId).path, language, pristine.path))
                check(buildEstimate.getInt("schema") == 2 && buildEstimate.getBoolean("estimate_only"))
                val buildBytes = buildEstimate.getLong("additional_bytes")
                check(buildBytes > 0) { "Invalid offline build storage estimate" }
                val buildSpace = requireSpace("offline build and normal restore", buildBytes, normal.bytes)
                journal.outcome(PatchPhase.BUILDING, JSONObject().put("build_storage_estimate", buildEstimate)
                    .put("build_storage_check", buildSpace).put("language", language))
                report("Building text and graphics from the verified private snapshot")
                // Refuses, before any game file is written, a layer it can neither rebuild nor read as pristine.
                JSONObject(bridge("build_snapshot", engine.path, journal.directory.path,
                    store.normal(normalId).path, normalId, language, pristine.path))
            }
            summary.optJSONObject("pristine")?.let { PristineDelta.describe(it).forEach(report) }
            journal.outcome(PatchPhase.STAGED, JSONObject().put("counts", JSONObject(
                bridge("result_counts", engine.path, summary.toString()))))
            // Apply and rollback read only out/, the snapshot and the hash lists; the extracted APK
            // packages and replacement trees would otherwise sit through both installs below.
            runCatching { DurableFiles.deleteTree(File(journal.directory, "work")) }
            runCatching { DurableFiles.deleteTree(File(journal.directory, PristineDelta.BUILD_COPY)) }
            checkpoint()
            val hashes = JSONObject(File(journal.directory, "staged-hashes.json").readText())
            val verifiedOriginals = transaction.verifyOriginals()
            val originals = verifiedOriginals.getJSONObject("files")
            hashes.keys().asSequence().forEach { GameFilePolicy.validate("packages/$it", writable = true) }
            val largestStaged = hashes.keys().asSequence().map {
                File(journal.directory, "out/$it").length()
            }.maxOrNull() ?: 0L
            val largestOriginal = originals.keys().asSequence().map {
                originals.getJSONObject(it).getLong("bytes")
            }.maxOrNull() ?: 0L
            val writeReserve = maxOf(largestStaged, largestOriginal)
            requireSpace("file writes and normal restore", normal.bytes, writeReserve)
            device.forceStopGame()
            // Still the access APK from the snapshot; the layer is checked again before the first write.
            validateLayer(File(journal.directory, "snapshot/manifest.json"))
            journal.outcome(PatchPhase.APPLYING)
            for (name in hashes.keys().asSequence().sorted()) {
                checkpoint()
                requireSpace("package write and normal restore", normal.bytes, writeReserve)
                report("Applying package file $name")
                transaction.write("packages/$name", File(journal.directory, "out/$name"), hashes.getString(name))
            }
            checkpoint()
            transaction.finishApply(hashes, verifiedOriginals)
            install(journal, store.normal(normalId), false, PatchPhase.COMPLETE)
            metricStatus = "complete"
            promoteSessionDelta(engine.path)
            summary
        } catch (error: Throwable) {
            journal.recoveryRequired(error.message ?: error.javaClass.simpleName)
            try { recoverLocked(journal) } catch (recovery: Throwable) {
                journal.recoveryRequired("${error.message}; recovery: ${recovery.message}")
                restoreNormalAfterFailure(journal, recovery)
                error.addSuppressed(recovery)
            }
            if (journal.phase == PatchPhase.COMPLETE) {
                metricStatus = "complete"
                report("Verified patch and normal APK recovered after interrupted final installation")
                JSONObject(File(journal.directory, "out/device_patch_summary.json").readText())
            } else throw error
        } finally {
            runCatching { metrics.finish(metricStatus) }.onFailure {
                android.util.Log.w("HokAceMetrics", "Resource metrics could not be retained", it)
            }
            releaseIfResolved(journal)
        }
    }

    private fun releaseIfResolved(journal: SessionJournal) {
        if (journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) return
        // Runs in finally: never let cleanup or its message replace the run's own outcome.
        runCatching {
            val freed = releaseSession(journal.directory)
            if (freed > 0) report("Freed ${StorageBudget.freeSpaceLabel(freed)} of temporary patch files")
        }.onFailure { android.util.Log.w("HokAceStorage", "Resolved session files could not be removed", it) }
    }

    fun recover(sessionId: String) = exclusive {
        GameFilePolicy.session(sessionId)
        val journal = SessionJournal.load(File(sessions, sessionId))
        activeJournal.set(journal)
        try { recoverLocked(journal) } catch (error: Throwable) {
            journal.recoveryRequired(error.message ?: "Recovery interrupted")
            restoreNormalAfterFailure(journal, error)
            throw error
        }
        keepResolvedDelta(journal)
        releaseIfResolved(journal)
        journal.terminalResult()
    }

    /** Recovery that resolves a run keeps its pristine delta now, not only at the next patch run. */
    private fun keepResolvedDelta(journal: SessionJournal) {
        if (journal.phase != PatchPhase.COMPLETE && !journal.layerUnconfirmed) return
        if (!File(journal.directory, PristineDelta.SESSION_DELTA).isFile) return
        runCatching { promoteSessionDelta(EngineAssets.prepare(context).path) }.onFailure {
            report("Could not keep the pristine delta yet (${it.javaClass.simpleName}); the next patch keeps it")
        }
    }

    /**
     * Free up space without starting a patch: what a run frees before its first budget, plus each
     * unfinished run that left no game file mid-change, closed by [SessionJournal.closeUnconfirmed]
     * once the normal APK is verified installed. Pristine deltas, the saved normal APKs and this game
     * version's prepared APKs stay unless <removeSavedApks>; see [ApkPreparation.removeSaved]. A run that
     * stopped mid-change is refused: it needs recovery.
     */
    @JvmOverloads fun freeSpace(removeSavedApks: Boolean = false): JSONObject = exclusive {
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
            val normal = store.verify(journal.recoveryId)
            check(runCatching { verifyInstalled(normal) }.isSuccess) {
                "Restore the interrupted patch first: the normal game app is not installed"
            }
            installed = normal
            journal.closeUnconfirmed("Closed by Free up space; the game files were not checked again")
            report("Closed an interrupted run that left no game file half-changed")
        }
        if (sessions.listFiles().orEmpty().any { File(it, PristineDelta.SESSION_DELTA).isFile }) {
            promoteSessionDelta(EngineAssets.prepare(context).path)
        }
        releaseResolvedSessions()
        StorageBudget.releaseReplacedGameApks(device, report)
        val known = installed ?: File(context.filesDir, "recovery").listFiles().orEmpty()
            .filter { it.isDirectory && it.name.matches(Regex("[0-9a-f]{64}")) }
            .sortedByDescending { it.lastModified() }.asSequence()
            .mapNotNull { folder -> runCatching { store.verify(folder.name).also { verifyInstalled(it) } }.getOrNull() }
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

    private fun restoreNormalAfterFailure(journal: SessionJournal, cause: Throwable) {
        try {
            val normal = store.verify(journal.recoveryId)
            check(device.asBinder().isBinderAlive) { "Shizuku is unavailable for normal APK restoration" }
            if (!runCatching { verifyInstalled(normal) }.isSuccess) {
                requireSpace("emergency normal APK restore", normal.bytes)
                journal.beginRecoveryNormal(normal)
                report("Restoring normal APK; package recovery remains required")
                ParcelFileDescriptor.open(store.normal(normal.sha256), ParcelFileDescriptor.MODE_READ_ONLY).use {
                    device.replaceGameApk(it, normal.bytes)
                }
                verifyInstalled(normal)
            }
            journal.recoveryNormalVerified()
            report("Normal APK verified; do not launch until package recovery is resolved")
        } catch (restore: Throwable) {
            cause.addSuppressed(restore)
            journal.recoveryRequired("${cause.message}; normal APK restore: ${restore.message}")
        }
    }

    private fun recoverLocked(journal: SessionJournal) {
        check(journal.phase !in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED)) { "Session already resolved" }
        var unconfirmed: String? = null
        val normal = store.verify(journal.recoveryId)
        device.forceStopGame()
        StorageBudget.releaseReplacedGameApks(device, report)
        val transaction = if (journal.dirtyPackages) GameFileTransaction(journal, device) else null
        val forward = !journal.dirtyPackages && journal.snapshot().optBoolean("patch_payload_verified", false)
        val applied = if (forward) GameFileTransaction(journal, device).verifyAppliedManifest() else null
        // Refusing damaged originals must retain the prior unresolved package-write intent.
        val originals = transaction?.verifyOriginals()
        journal.outcome(PatchPhase.RESTORING)
        if (applied != null) {
            // A durable earlier verification cannot establish the layer after a restart or update.
            val accessFile = File(journal.directory, "access.apk")
            val access = ApkIdentity.read(context, accessFile)
            check(access.debuggable && access.certificateSha256 == normal.certificateSha256 &&
                access.versionCode == normal.versionCode && access.versionName == normal.versionName) {
                "Retained access and recovery APK identities differ"
            }
            requireSpace("applied-layer recovery audit and normal restore", maxOf(normal.bytes, access.bytes))
            install(journal, accessFile, true, PatchPhase.RESTORING)
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
            val files = checkNotNull(originals).getJSONObject("files")
            val largest = files.keys().asSequence().map { files.getJSONObject(it).getLong("bytes") }.maxOrNull() ?: 0L
            val access = ApkIdentity.read(context, File(journal.directory, "access.apk"))
            requireSpace("complete rollback and normal restore", maxOf(normal.bytes, access.bytes), largest)
            install(journal, File(journal.directory, "access.apk"), true, PatchPhase.RESTORING)
            transaction.rollback { source -> requireSpace("rollback file and normal restore", normal.bytes, source.length()) }
        }
        // A failed offline build may fill storage while the already-verified normal APK stays
        // installed. Verify that identity before spending another APK-sized installer allocation.
        val completion = if (unconfirmed != null) PatchPhase.CANCELLED else journal.recoveryCompletionPhase
        fun closing() = JSONObject().apply { unconfirmed?.let { put("layer_unconfirmed", it.take(4096)) } }
        val alreadyNormal = runCatching { verifyInstalled(normal) }.isSuccess
        if (alreadyNormal) {
            journal.outcome(completion, closing().put("normal_verified", true))
            report("Normal game APK verified; interrupted session recovered")
            return
        }
        requireSpace("normal APK restore", normal.bytes)
        install(journal, store.normal(normal.sha256), false, completion, updates = closing())
        report("Normal game APK verified; interrupted session recovered")
    }
}
