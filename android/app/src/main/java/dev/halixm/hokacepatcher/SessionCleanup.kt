package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File
import java.nio.file.Files
import org.json.JSONArray
import org.json.JSONObject

/**
 * Release the bulk of resolved sessions, a run's retired snapshots and earlier app builds' engine folders.
 *
 * Moved verbatim out of [PatchCoordinator], which owns when each runs: always under the coordinator lock.
 * <adoptingSessions> is the coordinator's own live set of sessions whose completion is being adopted.
 */
internal class SessionCleanup(
    private val context: Context,
    private val sessions: File,
    private val adoptingSessions: Set<String>,
    private val report: (String) -> Unit,
) {
    /**
     * Coordinator lock held, on a measured shortage only: every resolved session's bulk, <journal>'s retired
     * snapshots ([releaseRetiredSnapshots]) and the engine folders of earlier app builds ([releaseStaleEngines]).
     * Each part refuses on its own unreadable state; the caller remeasures the same budget afterwards.
     */
    fun reclaimForShortage(journal: SessionJournal?) {
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
    fun releaseSession(directory: File): Long {
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
     * Coordinator lock held. A damaged journal or run record is left for recovery and export rather than
     * guessed at. Legacy resolved sessions release their bulk as before. A schema-2 session stays pinned
     * while its saved action is unresolved (continuation and recovery need it); among resolved ones only the
     * newest stays as the device target's reusable cache, so stopped reusable work survives until a newer
     * resolved action replaces it, Free up space removes it, or a measured budget needs its space.
     */
    fun releaseResolvedSessions(keepNewest: Boolean = true) {
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
}
