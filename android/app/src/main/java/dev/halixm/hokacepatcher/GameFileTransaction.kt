package dev.halixm.hokacepatcher

import android.os.ParcelFileDescriptor
import android.util.AtomicFile
import java.io.File
import java.nio.file.Files
import org.json.JSONObject

/** Whole-set byte restoration requires no Python runtime, codec or translation engine revision. */
class GameFileTransaction(private val journal: SessionJournal, private val device: IPrivilegedDeviceService) {
    private val snapshot = File(journal.directory, "snapshot")

    fun verifyOriginals(): JSONObject {
        check(snapshot.isDirectory && !Files.isSymbolicLink(snapshot.toPath())) { "Invalid snapshot root" }
        val path = File(snapshot, "manifest.json")
        check(path.length() in 1..(1024 * 1024)) { "Invalid original snapshot manifest" }
        val manifest = JSONObject(path.readText())
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
        return manifest
    }

    fun write(relative: String, source: File, hash: String, rollback: Boolean = false) {
        GameFilePolicy.validate(relative, writable = true)
        check(source.isFile && !Files.isSymbolicLink(source.toPath()) && ApkIdentity.digest(source) == hash) {
            "Retained file changed: $relative"
        }
        journal.intent(if (rollback) "rollback_file" else "write_file",
            JSONObject().put("path", relative).put("sha256", hash).put("bytes", source.length()))
        ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.writeGameFile(journal.id, relative, it, source.length(), hash)
        }
        if (rollback) journal.outcome(PatchPhase.RESTORING) else journal.fileCommitted(relative)
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
    private fun expectedApplied(hashes: JSONObject, verified: JSONObject? = null): JSONObject {
        check(hashes.length() in 0..8192) { "Unsupported staged file count" }
        val expected = verified?.let { JSONObject(it.toString()) } ?: verifyOriginals()
        val files = expected.getJSONObject("files")
        files.keys().asSequence().filter { it.startsWith("Watchdog/") }.toList().forEach { files.remove(it) }
        for (name in hashes.keys()) {
            val relative = "packages/$name"
            GameFilePolicy.validate(relative, writable = true)
            val source = File(journal.directory, "out/$name")
            check(source.isFile && !Files.isSymbolicLink(source.toPath()) &&
                (verified != null || ApkIdentity.digest(source) == hashes.getString(name))) {
                "Retained staged file changed: $name"
            }
            files.put(relative, JSONObject().put("sha256", hashes.getString(name))
                .put("bytes", source.length()))
        }
        return expected
    }

    /** Reconstruct the retained expected layer before granting forward recovery any completion. */
    fun verifyAppliedManifest(): File {
        val staged = File(journal.directory, "staged-hashes.json")
        check(staged.length() in 1..(1024 * 1024)) { "Invalid retained stage manifest" }
        val expected = expectedApplied(JSONObject(staged.readText()))
        val manifest = File(journal.directory, "applied-manifest.json")
        check(!Files.isSymbolicLink(manifest.toPath())) { "Applied manifest is a link" }
        val bytes = AtomicFile(manifest).readFully()
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
    @JvmOverloads fun finishApply(hashes: JSONObject, originals: JSONObject? = null) {
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
        check(storage.readFully().contentEquals(bytes)) { "Applied manifest read-back differs" }
        validate(manifest)
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("packages_dirty", false)
            .put("patch_payload_verified", true))
    }

    @JvmOverloads fun rollback(beforeWrite: (File) -> Unit = {}) {
        val original = verifyOriginals()
        val files = original.getJSONObject("files")
        val staged = File(journal.directory, "staged-hashes.json")
        check(staged.length() in 1..(1024 * 1024)) { "Invalid retained stage manifest" }
        val hashes = JSONObject(staged.readText())
        check(hashes.length() in 0..8192) { "Unsupported staged file count" }
        for (name in hashes.keys().asSequence().sorted()) {
            val relative = "packages/$name"
            GameFilePolicy.validate(relative, writable = true)
            device.clearSessionTemp(journal.id, relative)
            val source = File(snapshot, relative)
            beforeWrite(source)
            write(relative, source, files.getJSONObject(relative).getString("sha256"), true)
        }
        journal.intent("restore_watchdog")
        device.clearGameWatchdog()
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
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("packages_dirty", false)
            .put("patch_payload_verified", false))
    }
}
