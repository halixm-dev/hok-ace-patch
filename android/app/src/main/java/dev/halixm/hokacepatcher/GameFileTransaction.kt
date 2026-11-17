package dev.halixm.hokacepatcher

import android.os.ParcelFileDescriptor
import android.util.AtomicFile
import java.io.File
import java.nio.file.Files
import org.json.JSONObject
import org.json.JSONArray
import java.nio.file.attribute.BasicFileAttributes

/** Whole-set byte restoration requires no Python runtime, codec or translation engine revision. */
class GameFileTransaction(private val journal: SessionJournal, private val device: IPrivilegedDeviceService) {
    private val snapshot = File(journal.directory, "snapshot")

    private val proofOwner = Any()
    private var generation = 0
    var originalHashPasses = 0
        private set
    private var rollbackPolicy: JSONObject? = null
    private var rollbackPaths: Set<String> = emptySet()

    /** Opaque, single-consumer proof: never serialised or accepted from caller JSON. */
    class VerifiedOriginals internal constructor(private val owner: Any, private val generation: Int,
        private val encoded: String, private val stamps: Map<String, String>) {
        fun files(): JSONObject = JSONObject(encoded).getJSONObject("files")
        internal fun manifest(requester: Any, current: Int, observed: Map<String, String>): JSONObject {
            check(owner === requester && generation == current && stamps == observed) {
                "Originals proof expired; verify this transaction again"
            }
            return JSONObject(encoded)
        }
    }
    private fun stamps(): Map<String, String> = Files.walk(snapshot.toPath()).use { paths ->
        paths.iterator().asSequence().associate { path ->
            check(!Files.isSymbolicLink(path)) { "Snapshot contains a link" }
            val a = Files.readAttributes(path, BasicFileAttributes::class.java)
            path.toString() to "${a.fileKey()}:${a.size()}:${a.lastModifiedTime()}:${a.creationTime()}"
        }
    }
    private fun original(proof: VerifiedOriginals): JSONObject = proof.manifest(proofOwner, generation, stamps())
    fun verifyOriginals(): VerifiedOriginals {
        generation++
        rollbackPolicy = null; rollbackPaths = emptySet()
        val before = stamps()
        check(snapshot.isDirectory && !Files.isSymbolicLink(snapshot.toPath())) { "Invalid snapshot root" }
        val path = File(snapshot, "manifest.json")
        check(path.length() in 1..(1024 * 1024)) { "Invalid original snapshot manifest" }
        val manifest = ArtifactReceipts.parse(path.readBytes())
        check(manifest.getInt("schema") == 1)
        val files = manifest.getJSONObject("files")
        check(files.length() in 1..8192)
        val actual = mutableSetOf<String>()
        for (root in listOf(File(snapshot, "packages"), File(snapshot, "Watchdog"))) {
            check(!Files.isSymbolicLink(root.toPath())) { "Snapshot root is a link" }
            if (root.exists()) Files.walk(root.toPath()).use { paths ->
                paths.forEach { path ->
                    check(!Files.isSymbolicLink(path)) { "Snapshot contains a link" }
                    if (Files.isRegularFile(path)) actual += snapshot.toPath().relativize(path).toString().replace('\\', '/')
                    check(actual.size <= 8192) { "Snapshot contains too many files" }
                }
            }
        }
        check(actual == files.keys().asSequence().toSet()) { "Original snapshot file set changed" }
        for (relative in files.keys()) {
            GameFilePolicy.validate(relative)
            val expected = files.getJSONObject(relative)
            val file = File(snapshot, relative)
            check(file.length() == expected.getLong("bytes") &&
                ApkIdentity.digest(file) == expected.getString("sha256")) { "Original snapshot changed: $relative" }
        }
        check(before == stamps()) { "Snapshot changed while verifying" }
        originalHashPasses++
        return VerifiedOriginals(proofOwner, generation, manifest.toString(), before)
    }

    /** Exact full staged hash/length comparison, only after independent current-layer verification. */
    fun changedWrites(hashes: JSONObject, proof: VerifiedOriginals): List<String> {
        val files = original(proof).getJSONObject("files")
        validate(File(snapshot, "manifest.json"))
        return hashes.keys().asSequence().sorted().filter { name ->
            GameFilePolicy.validate("packages/$name", writable = true)
            val source = File(journal.resultRoot, "out/$name")
            check(source.isFile && !Files.isSymbolicLink(source.toPath()) &&
                ApkIdentity.digest(source) == hashes.getString(name)) { "Retained staged file changed: $name" }
            val old = files.optJSONObject("packages/$name")
            old == null || old.getLong("bytes") != source.length() || old.getString("sha256") != hashes.getString(name)
        }.toList()
    }

    private fun guarded(operation: String, relative: String = "", source: File? = null, hash: String = "") {
        val policy = checkNotNull(rollbackPolicy)
        val path = File(journal.directory, "recovery-policy.json")
        check(!Files.isSymbolicLink(path.toPath()))
        val storage = AtomicFile(path)
        val output = storage.startWrite()
        try { output.write(policy.toString().toByteArray(Charsets.UTF_8)); output.fd.sync(); storage.finishWrite(output)
            DurableFiles.syncDirectory(journal.directory)
        } catch (error: Throwable) { storage.failWrite(output); throw error }
        ParcelFileDescriptor.open(path, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            if (source == null) device.reconcileGameFiles(journal.id, operation, relative, descriptor, null, 0, "")
            else ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY).use {
                device.reconcileGameFiles(journal.id, operation, relative, descriptor, it, source.length(), hash)
            }
        }
    }

    fun write(relative: String, source: File, hash: String, rollback: Boolean = false) {
        GameFilePolicy.validate(relative, writable = true)
        check(source.isFile && !Files.isSymbolicLink(source.toPath()) && ApkIdentity.digest(source) == hash) {
            "Retained file changed: $relative"
        }
        journal.intent(if (rollback) "rollback_file" else "write_file",
            JSONObject().put("path", relative).put("sha256", hash).put("bytes", source.length()))
        if (rollback) guarded("write", relative, source, hash)
        else ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.writeGameFile(journal.id, relative, it, source.length(), hash)
        }
        if (rollback) journal.outcome(PatchPhase.RESTORING) else journal.fileCommitted(relative)
    }

    /** Re-download: delete one package file still at its snapshot <hash>; [rollback] writes it back. */
    fun delete(relative: String, hash: String) {
        GameFilePolicy.validate(relative, writable = true)
        journal.intent("delete_file", JSONObject().put("path", relative).put("sha256", hash))
        device.deleteGameFile(journal.id, relative, hash)
        journal.fileCommitted(relative)
    }

    /**
     * Re-download's last game-file step: clear Watchdog, which drops the broken list, so the game's next
     * launch downloads the deleted packages instead of repairing them. Nothing was written to verify.
     */
    fun finishDeletion() {
        journal.intent("clear_watchdog")
        device.clearGameWatchdog()
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("packages_dirty", false)
            .put("patch_payload_verified", false))
    }

    fun validate(manifest: File) {
        ParcelFileDescriptor.open(manifest, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.validateGameSnapshot(it)
        }
    }

    /**
     * [verified] is this run's own [verifyOriginals] result from just before the apply, whose [write]s
     * each hashed their staged file; only then are the originals and staged files not hashed again.
     */
    private fun expectedApplied(hashes: JSONObject, verified: VerifiedOriginals? = null): JSONObject {
        check(hashes.length() in 0..8192) { "Unsupported staged file count" }
        val expected = original(verified ?: verifyOriginals())
        val files = expected.getJSONObject("files")
        files.keys().asSequence().filter { it.startsWith("Watchdog/") }.toList().forEach { files.remove(it) }
        for (name in hashes.keys()) {
            val relative = "packages/$name"
            GameFilePolicy.validate(relative, writable = true)
            val source = File(journal.resultRoot, "out/$name")
            check(source.isFile && !Files.isSymbolicLink(source.toPath()) &&
                ApkIdentity.digest(source) == hashes.getString(name)) {
                "Retained staged file changed: $name"
            }
            files.put(relative, JSONObject().put("sha256", hashes.getString(name))
                .put("bytes", source.length()))
        }
        return expected
    }

    /** Reconstruct the retained expected layer before granting forward recovery any completion. */
    fun verifyAppliedManifest(): File {
        val staged = File(journal.resultRoot, "staged-hashes.json")
        check(staged.length() in 1..(1024 * 1024)) { "Invalid retained stage manifest" }
        val expected = expectedApplied(JSONObject(staged.readText()))
        val manifest = File(journal.directory, "applied-manifest.json")
        check(!Files.isSymbolicLink(manifest.toPath())) { "Applied manifest is a link" }
        val bytes = DurableFiles.readCommitted(manifest)
        check(bytes.size in 1..(1024 * 1024)) { "Invalid applied manifest" }
        val actual = JSONObject(String(bytes, Charsets.UTF_8))
        val files = actual.getJSONObject("files")
        val wanted = expected.getJSONObject("files")
        check(actual.getInt("schema") == 1 && files.keys().asSequence().toSet() == wanted.keys().asSequence().toSet()) {
            "Retained applied manifest file set differs"
        }
        for (name in wanted.keys()) {
            val entry = files.getJSONObject(name)
            val original = wanted.getJSONObject(name)
            check(entry.getLong("bytes") == original.getLong("bytes") &&
                entry.getString("sha256") == original.getString("sha256")) { "Retained applied manifest differs: $name" }
        }
        return manifest
    }

    /** [originals] is the [verifyOriginals] result the apply started from; without it they are verified again. */
    @JvmOverloads fun finishApply(hashes: JSONObject, originals: VerifiedOriginals? = null) {
        val expected = expectedApplied(hashes, originals)
        journal.intent("clear_watchdog")
        device.clearGameWatchdog()
        val manifest = File(journal.directory, "applied-manifest.json")
        val storage = AtomicFile(manifest)
        val bytes = expected.toString().toByteArray(Charsets.UTF_8)
        val stream = storage.startWrite()
        try {
            stream.write(bytes); stream.fd.sync(); storage.finishWrite(stream)
            DurableFiles.syncDirectory(journal.directory)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
        check(DurableFiles.readCommitted(storage.baseFile).contentEquals(bytes)) { "Applied manifest read-back differs" }
        validate(manifest)
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("packages_dirty", false)
            .put("patch_payload_verified", true))
        generation++
    }

    /** Capture intent before recovery installs/outcomes can clear it. No device mutation here. */
    fun prepareRollback(proof: VerifiedOriginals) {
        val original = original(proof)
        val files = original.getJSONObject("files")
        val saved = journal.snapshot()
        val touched = mutableSetOf<String>()
        for (list in listOfNotNull(saved.optJSONArray("attempted_files"), saved.optJSONArray("committed_files")))
            for (index in 0 until list.length()) touched += list.getString(index)
        saved.optJSONObject("mutation_intent")?.let { intent ->
            if (intent.optString("operation") in setOf("write_file", "delete_file", "rollback_file"))
                touched += intent.getJSONObject("detail").getString("path")
        }
        val staged = File(journal.resultRoot, "staged-hashes.json")
        check(staged.length() in 1..(1024 * 1024)) { "Invalid retained stage manifest" }
        val hashes = ArtifactReceipts.parse(staged.readBytes())
        check(hashes.length() in 0..8192)
        val stagedPaths = hashes.keys().asSequence().map { "packages/$it" }.toSet()
        check(touched.filter { it.startsWith("packages/") }.all { it in stagedPaths }) { "Touched path is outside staged plan" }
        rollbackPaths = touched.filter { it.startsWith("packages/") }.toSet()
        val policy = JSONObject()
        for (name in files.keys()) policy.put(name, JSONObject().put("absent",
            name.startsWith("Watchdog/") && saved.optBoolean("watchdog_touched", false))
            .put("states", JSONArray().put(files.getJSONObject(name))))
        val deletion = journal.redownloadPlanRoot != null && saved.optString("build_attempt").isEmpty()
        for (name in hashes.keys()) {
            val relative = "packages/$name"
            GameFilePolicy.validate(relative, writable = true)
            if (relative !in touched) continue
            val item = policy.optJSONObject(relative) ?: JSONObject().put("absent", true).put("states", JSONArray())
            if (deletion) {
                check(files.getJSONObject(relative).getString("sha256") == hashes.getString(name))
                item.put("absent", true)
            } else {
                val out = File(journal.resultRoot, "out/$name")
                check(out.isFile && !Files.isSymbolicLink(out.toPath()) && ApkIdentity.digest(out) == hashes.getString(name))
                val states = item.getJSONArray("states")
                if ((0 until states.length()).none { states.getJSONObject(it).getString("sha256") == hashes.getString(name) })
                    states.put(JSONObject().put("sha256", hashes.getString(name)).put("bytes", out.length()))
            }
            policy.put(relative, item)
        }
        rollbackPolicy = JSONObject().put("schema", 1).put("watchdog_absent", saved.optBoolean("watchdog_touched", false)).put("files", policy)
        RecoveryFilePolicy.parse(checkNotNull(rollbackPolicy))
    }

    @JvmOverloads fun rollback(beforeWrite: (File) -> Unit = {}) = rollback(verifyOriginals(), beforeWrite)

    fun rollback(proof: VerifiedOriginals, beforeWrite: (File) -> Unit) {
        val original = original(proof)
        if (rollbackPolicy == null) prepareRollback(proof)
        val files = original.getJSONObject("files")
        val policy = checkNotNull(rollbackPolicy).getJSONObject("files")
        // Only our own temps are removed; foreign temps/extra files remain an actionable refusal.
        for (name in rollbackPaths) device.clearSessionTemp(journal.id, name)
        if (journal.snapshot().optBoolean("watchdog_touched", false))
            for (name in files.keys().asSequence().filter { it.startsWith("Watchdog/") }) device.clearSessionTemp(journal.id, name)
        guarded("audit")
        generation++ // Consumed even if the provider later refuses or the invocation is interrupted.
        for (relative in rollbackPaths.sorted()) {
            val old = files.optJSONObject(relative)
            if (old == null) {
                journal.intent("delete_file", JSONObject().put("path", relative))
                guarded("delete", relative)
                journal.outcome(PatchPhase.RESTORING)
            } else {
                val source = File(snapshot, relative)
                beforeWrite(source)
                write(relative, source, old.getString("sha256"), true)
            }
        }
        journal.intent("restore_watchdog")
        guarded("clear_watchdog")
        for (name in policy.keys()) if (name.startsWith("Watchdog/")) policy.getJSONObject(name).put("absent", true)
        device.restoreWatchdogDirectory("Watchdog")
        // Derive parents from every original file too: a valid tar need not carry directory entries.
        val directories = mutableSetOf<String>()
        for (relative in files.keys().asSequence().filter { it.startsWith("Watchdog/") }) {
            var parent = relative.substringBeforeLast('/')
            while (parent != "Watchdog") { directories += parent; parent = parent.substringBeforeLast('/') }
        }
        val originalDirectories = original.getJSONArray("directories")
        for (index in 0 until originalDirectories.length()) {
            val relative = originalDirectories.getString(index)
            if (relative.startsWith("Watchdog/")) directories += relative
        }
        for (relative in directories.sorted()) {
            GameFilePolicy.watchdogDirectory(relative)
            device.restoreWatchdogDirectory(relative)
        }
        journal.outcome(PatchPhase.RESTORING)
        for (relative in files.keys().asSequence().filter { it.startsWith("Watchdog/") }.sorted()) {
            device.clearSessionTemp(journal.id, relative)
            val source = File(snapshot, relative)
            beforeWrite(source)
            write(relative, source, files.getJSONObject(relative).getString("sha256"), true)
        }
        validate(File(snapshot, "manifest.json"))
        generation++
        rollbackPolicy = null
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("packages_dirty", false)
            .put("patch_payload_verified", false))
    }
}
