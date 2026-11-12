package dev.halixm.hokacepatcher

import android.content.Context
import android.content.ContextWrapper
import android.os.Binder
import android.os.ParcelFileDescriptor
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.lang.reflect.Proxy
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Isolated fixture files and a fake root transport; no shell, installer or real game is called. */
class RedownloadReviewProbeTest {
    private class Fixture(val failFinalVerify: Boolean = false, val failDelete: Boolean = false) {
        val actual = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(actual.filesDir, "redownload-probes/${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(actual) { override fun getFilesDir() = root }
        val engine = EngineAssets.prepare(context)
        val normal = ApkIdentity(1L, "a".repeat(64), PrivilegedDeviceService.GAME, 1L,
            "fixture", GameSigner.CERTIFICATE_SHA256, false)
        val journal = SessionJournal.create(File(root, "sessions"), normal.sha256, engine.name, normal)
        val keep = PristineDelta.directory(context)
        val files = mutableMapOf<String, ByteArray>()
        var deletes = 0
        var clears = 0
        val binder = Binder()
        val device = Proxy.newProxyInstance(IPrivilegedDeviceService::class.java.classLoader,
            arrayOf(IPrivilegedDeviceService::class.java)) { _, method, arguments ->
            val args = arguments ?: emptyArray()
            when (method.name) {
                "asBinder" -> binder
                "diagnostics" -> "{\"uid\":0}"
                "forceStopGame" -> null
                "validateGameSnapshot" -> {
                    val descriptor = args[0] as ParcelFileDescriptor
                    val value = ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.fileDescriptor))
                        .use { JSONObject(String(it.readBytes())) }.getJSONObject("files")
                    check(value.keys().asSequence().toSet() == files.keys) { "Game file set changed" }
                    for ((name, bytes) in files) {
                        check(value.getJSONObject(name).getString("sha256") == digest(bytes)) { "Game file changed: $name" }
                    }
                    "verified fixture"
                }
                "deleteGameFile" -> {
                    val name = args[1] as String
                    check(digest(checkNotNull(files[name])) == args[2])
                    files.remove(name); deletes++
                    if (deletes == 1 && failDelete) error("Synthetic deletion acknowledgment lost")
                    null
                }
                "writeGameFile" -> {
                    val descriptor = args[2] as ParcelFileDescriptor
                    val body = ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.fileDescriptor))
                        .use { it.readBytes() }
                    check(body.size.toLong() == args[3] && digest(body) == args[4])
                    files[args[1] as String] = body
                    "verified fixture"
                }
                "clearSessionTemp", "restoreWatchdogDirectory" -> null
                "clearGameWatchdog" -> { files.keys.removeAll { it.startsWith("Watchdog/") }; clears++; null }
                else -> error("Unexpected device call: ${method.name}")
            }
        } as IPrivilegedDeviceService
        var verifications = 0
        val coordinator = PatchCoordinator(context, device, {}, PatchCoordinator.InstalledApkVerifier {
            assertEquals(normal, it)
            if (++verifications == 2 && failFinalVerify) error("Synthetic final verification interruption")
        })
        val review: JSONObject
        init {
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(actual))
                val code = """
                    import sys, json, hashlib
                    from pathlib import Path
                    sys.path.insert(0, ${pythonString(File(engine, "tools").path)})
                    import android_bridge as b
                    session = Path(${pythonString(journal.directory.path)})
                    bodies = {'packages/1/1.info': b'{"version":"fixture"}', 'packages/1/1.db': b'unrelated',
                        'packages/15/15.db': b'fixture index', 'packages/15/15_0.db': b'fixture shard',
                        'packages/15/15.info': b'fixture info', 'Watchdog/BrokenList.db': b''}
                    entries = {}
                    for name, body in bodies.items():
                        path = session / 'snapshot' / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(body)
                        entries[name] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                    (session / 'snapshot/manifest.json').write_text(json.dumps({'schema': 1, 'files': entries,
                        'directories': [], 'bytes': sum(len(body) for body in bodies.values())}))
                    mixed, graphics = b._mixed_packages, b._graphics_candidates
                    try:
                        b._mixed_packages = lambda *args: {'15': 'synthetic mixed package'}
                        b._graphics_candidates = lambda *args: set()
                        result = b.review_redownload(${pythonString(engine.path)}, str(session), ${pythonString(keep.path)})
                        (session / 'fixture-review.json').write_text(result)
                    finally:
                        b._mixed_packages, b._graphics_candidates = mixed, graphics
                """.trimIndent()
                val builtins = Python.getInstance().getModule("builtins")
                builtins.callAttr("exec", code, builtins.callAttr("dict"))
                val snapshot = File(journal.directory, "snapshot")
                snapshot.walkTopDown().filter { it.isFile && it.name != "manifest.json" }.forEach {
                    files[it.relativeTo(snapshot).invariantSeparatorsPath] = it.readBytes()
                }
                review = JSONObject(File(journal.directory, "fixture-review.json").readText())
                journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED)
                journal.outcome(PatchPhase.SNAPSHOT_READY)
                journal.outcome(PatchPhase.BUILDING, JSONObject().put("redownload", true))
                journal.outcome(PatchPhase.STAGED, JSONObject().put("redownload_review", review))
                journal.outcome(PatchPhase.RESTORING)
                journal.outcome(PatchPhase.REDOWNLOAD_REVIEW, JSONObject().put("normal_verified", true))
            } catch (error: Throwable) {
                root.deleteRecursively()
                throw error
            }
        }
        fun close() { root.deleteRecursively() }
    }

    @Test fun exactApprovalDeletesOnceAndWaitsForTheExplicitDownloadAnswer() {
        val f = Fixture()
        try {
            val loaded = SessionJournal.load(f.journal.directory)
            assertEquals(PatchPhase.REDOWNLOAD_REVIEW, loaded.phase)
            assertEquals(0, f.deletes); assertEquals(0, f.clears)
            try {
                f.coordinator.deleteReviewedRedownload(loaded.id, "0".repeat(64))
                fail("A different displayed plan was accepted")
            } catch (_: IllegalStateException) { }
            assertEquals(0, f.deletes)
            f.coordinator.deleteReviewedRedownload(loaded.id, f.review.getString("digest"))
            assertEquals(3, f.deletes); assertEquals(1, f.clears)
            assertTrue(f.files.keys.none { it.startsWith("packages/15/") || it.startsWith("Watchdog/") })
            assertTrue(f.files.containsKey("packages/1/1.db"))
            val complete = SessionJournal.load(f.journal.directory)
            assertEquals(PatchPhase.COMPLETE, complete.phase)
            assertFalse(complete.snapshot().optBoolean("redownload_downloads_finished"))
            complete.confirmRedownloadFinished()
            assertTrue(SessionJournal.load(complete.directory).snapshot().getBoolean("redownload_downloads_finished"))
        } finally { f.close() }
    }

    @Test fun finalVerificationRecoveryDoesNotRepeatDeletion() {
        val f = Fixture(failFinalVerify = true)
        try {
            f.coordinator.deleteReviewedRedownload(f.journal.id, f.review.getString("digest"))
            assertEquals(3, f.deletes); assertEquals(1, f.clears)
            assertEquals(PatchPhase.COMPLETE, SessionJournal.load(f.journal.directory).phase)
        } finally { f.close() }
    }

    @Test fun interruptedDeletionRollsBackWithoutClaimingFilesWereDeleted() {
        val f = Fixture(failDelete = true)
        try {
            val original = f.files.mapValues { it.value.copyOf() }
            try {
                f.coordinator.deleteReviewedRedownload(f.journal.id, f.review.getString("digest"))
                fail("Interrupted deletion reported success")
            } catch (_: IllegalStateException) { }
            assertEquals(original.keys, f.files.keys)
            original.forEach { (name, body) -> assertArrayEquals(body, f.files[name]) }
            val recovered = SessionJournal.load(f.journal.directory)
            assertEquals(PatchPhase.CANCELLED, recovered.phase)
            assertFalse(recovered.snapshot().optBoolean("redownload_deleted"))
        } finally { f.close() }
    }

    @Test fun aChangedLiveLayerDeletesNothing() {
        val f = Fixture()
        try {
            f.files["packages/15/15_0.db"] = "new game data".toByteArray()
            try {
                f.coordinator.deleteReviewedRedownload(f.journal.id, f.review.getString("digest"))
                fail("Changed game data was deleted")
            } catch (_: IllegalStateException) { }
            assertEquals(0, f.deletes); assertEquals(0, f.clears)
            assertArrayEquals("new game data".toByteArray(), f.files["packages/15/15_0.db"])
        } finally { f.close() }
    }

    companion object {
        private fun pythonString(value: String) = JSONObject.quote(value).replace("\\/", "/")

        private fun digest(bytes: ByteArray) = java.security.MessageDigest.getInstance("SHA-256")
            .digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
