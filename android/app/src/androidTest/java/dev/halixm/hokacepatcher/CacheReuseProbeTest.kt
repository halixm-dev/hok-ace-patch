package dev.halixm.hokacepatcher

import android.content.Context
import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.nio.file.Files
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Synthetic private metadata only: no service dispatch, installed game, binder or real APK operations. */
class CacheReuseProbeTest {
    private val hash = "a".repeat(64)
    private fun context(): Context {
        val actual = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(RunStore.privateRoot(actual), "completion-probes/${UUID.randomUUID()}").apply { mkdirs() }
        return object : ContextWrapper(actual) { override fun getFilesDir() = root }
    }
    private fun reject(action: () -> Unit) {
        try { action(); fail("Unverified metadata accepted") } catch (_: Exception) { }
    }
    private fun fixture(context: Context, remove: Boolean = false, run: RunStore.Run? = null): SessionJournal {
        val journal = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null,
            run?.id ?: UUID.randomUUID().toString(), run?.authorizationKey ?: hash)
        val attempt = UUID.randomUUID().toString()
        File(journal.directory, "build-attempts/$attempt/result").mkdirs()
        journal.record(JSONObject().put("build_attempt", attempt).put("remove", remove))
        File(journal.resultRoot, "staged-hashes.json").writeText("{}")
        File(journal.resultRoot, PristineDelta.SESSION_DELTA).writeText("synthetic-kept-pristine-body")
        PristineDelta.seal(context, journal, JSONObject().put("schema", 1).put("remove", remove)
            .put("files", if (remove) 0 else 1).put("bytes", 1)
            .put("delta_sha256", ApkIdentity.digest(File(journal.resultRoot, PristineDelta.SESSION_DELTA)))
            .put("staged_hashes", if (remove) JSONArray() else JSONArray().put(hash)))
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("normal_verified", true).put("patch_payload_verified", true))
        return journal
    }
    @Test fun finalizedFlagNeverReplacesActiveDeltaAndRecordReadback() {
        val context = context(); val journal = fixture(context)
        PristineDelta.finalize(context, journal)
        val active = File(PristineDelta.directory(context), "delta.bin")
        val before = active.readBytes()
        active.writeBytes(ByteArray(before.size) { 88 })
        reject { PristineDelta.finalize(context, SessionJournal.load(journal.directory)) }
        assertArrayEquals(ByteArray(before.size) { 88 }, active.readBytes())
        active.writeBytes(before)
        File(PristineDelta.directory(context), "staged-hashes.json").delete()
        reject { PristineDelta.finalize(context, journal) }
    }
    @Test fun stageSealRefusesNewActiveKnowledgeBeforeFirstIntent() {
        val context = context(); val journal = fixture(context)
        val keep = PristineDelta.directory(context).apply { mkdirs() }
        val foreign = File(keep, "staged-hashes.json")
        foreign.writeText(JSONObject().put("schema", 1).put("sha256", JSONArray().put("b".repeat(64))).toString())
        val before = foreign.readBytes()
        reject { PristineDelta.finalize(context, journal) }
        assertArrayEquals(before, foreign.readBytes())
        assertFalse(journal.snapshot().optBoolean("finalization_pending"))
        reject { journal.closeUnconfirmed("must remain actionable") }
    }
    @Test fun justifiedInterruptedRecordThenDeltaPromotionIsIdempotent() {
        val context = context(); val journal = fixture(context)
        PristineDelta.finalize(context, journal)
        journal.record(JSONObject().put("finalization_pending", true).put("finalized", false))
        // Original active delta was explicitly absent. Record was promoted first.
        File(PristineDelta.directory(context), "delta.bin").delete()
        PristineDelta.finalize(context, SessionJournal.load(journal.directory))
        val finalBytes = PristineDelta.activeIdentity(context).toString()
        PristineDelta.finalize(context, SessionJournal.load(journal.directory))
        assertEquals(finalBytes, PristineDelta.activeIdentity(context).toString())
    }
    @Test fun missingIntentChangedBackupAndNewRefusalCannotBeAdopted() {
        val context = context(); val journal = fixture(context)
        PristineDelta.finalize(context, journal)
        val refusal = File(PristineDelta.directory(context), "restore-refused.json").apply { writeText("new classification") }
        reject { PristineDelta.finalize(context, journal) }; assertTrue(refusal.exists())
        refusal.delete()
        val previous = File(journal.resultRoot.parentFile, "finalization/previous-delta.bin")
        previous.writeText("unrelated prior knowledge")
        reject { PristineDelta.finalize(context, journal) }
        previous.delete()
        File(journal.resultRoot.parentFile, "finalization/intent.json").delete()
        reject { PristineDelta.finalize(context, journal) }
    }
    @Test fun removeSealsRequiredAbsenceAndDoesNotAcceptForeignDelta() {
        val context = context(); val journal = fixture(context, remove = true)
        PristineDelta.finalize(context, journal)
        val active = File(PristineDelta.directory(context), "delta.bin")
        assertFalse(active.exists()); active.writeText("foreign knowledge")
        reject { PristineDelta.finalize(context, journal) }; assertEquals("foreign knowledge", active.readText())
    }
    @Test fun explicitAbsenceRejectsLinkedAncestor() {
        val context = context(); val elsewhere = File(context.filesDir, "elsewhere").apply { mkdirs() }
        Files.createSymbolicLink(PristineDelta.directory(context).toPath(), elsewhere.toPath())
        reject { PristineDelta.activeIdentity(context) }
    }
    @Test fun originalSourceCannotBeReplacedWithNormalizedOrChangedPrimeContent() {
        val context = context()
        fun apk(name: String, manifest: String, prime: String): File = File(context.filesDir, name).also { file ->
            ZipOutputStream(file.outputStream()).use { zip ->
                for ((path, value) in mapOf("AndroidManifest.xml" to manifest, "assets/prime.bin" to prime)) {
                    zip.putNextEntry(ZipEntry(path)); zip.write(value.toByteArray()); zip.closeEntry()
                }
            }
        }
        val source = apk("source.apk", "official", "ABCD")
        val normal = apk("normal.apk", "normal", "ABCD")
        InstalledGameVerifier.verifyManifestOnlySource(source, normal)
        apk("normal.apk", "normal", "WXYZ") // Same length changed prime bytes.
        reject { InstalledGameVerifier.verifyManifestOnlySource(source, normal) }
    }
    private fun claimed(context: Context): RunStore.Run {
        val store = RunStore(context)
        val run = store.start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        // Synthetic durable dispatch fixture; never claims a device preparation.
        val path = File(context.filesDir, "runs/${run.id}.json")
        val value = ArtifactReceipts.parse(path.readBytes()).put("lifecycle", "claimed")
        value.remove("record_sha256"); value.put("record_sha256", ArtifactReceipts.identityKey(value))
        path.writeText(ArtifactReceipts.canonical(value))
        return store.load(run.id)
    }
    @Test fun stopDuringReceiptHashingWinsPublicationAndRemainsStopped() {
        val context = context(); val run = claimed(context); val journal = fixture(context, run = run)
        PristineDelta.finalize(context, journal)
        // Production hashes before finishVerified, allowing Stop without waiting for that work.
        RunStore(context).stop(run.id)
        var publishedStopped = false
        RunStore.coordinator(context) { RunStore(context).finishVerified(run.id, journal) { publishedStopped = it } }
        assertTrue(publishedStopped); assertEquals(PatchPhase.CANCELLED, journal.phase)
        assertEquals("stopped", RunStore(context).load(run.id).lifecycle)
        assertEquals("stopped_consistent", journal.terminalResult().getString("status"))
    }
    @Test fun publicationCutNeverResolvesOrMakesReceiptAuthority() {
        val context = context(); val run = claimed(context); val journal = fixture(context, run = run)
        PristineDelta.finalize(context, journal)
        reject { RunStore.coordinator(context) {
            RunStore(context).finishVerified(run.id, journal) { error("cut after candidate receipt, before terminal") }
        } }
        assertEquals("claimed", RunStore(context).load(run.id).lifecycle)
        assertEquals(PatchPhase.RESTORING, SessionJournal.load(journal.directory).phase)
    }
    @Test fun stopRacingShortPublicationOrdersAfterAlreadyLinearizedCompletion() {
        val context = context(); val run = claimed(context); val journal = fixture(context, run = run)
        PristineDelta.finalize(context, journal)
        val queued = CountDownLatch(1)
        // As MainActivity.saveStop does: a store lock held by this process's completion refuses Stop
        // (an in-process tryLock throws), so Stop retries briefly and lands after the completion.
        var saved = false
        val stop = Thread {
            queued.countDown()
            repeat(200) { if (!saved && runCatching { RunStore(context).stop(run.id) }.isSuccess) saved = true
                else if (!saved) Thread.sleep(20) }
        }
        RunStore.coordinator(context) {
            RunStore(context).finishVerified(run.id, journal) { stopped ->
                assertFalse(stopped)
                stop.start(); assertTrue(queued.await(5, TimeUnit.SECONDS))
                // Store lock already selected the terminal outcome. No hashing/device operation occurs here.
            }
        }
        stop.join(10000); assertFalse(stop.isAlive); assertTrue(saved)
        assertEquals(PatchPhase.COMPLETE, journal.phase)
        assertEquals("complete", RunStore(context).load(run.id).lifecycle)
        assertFalse(RunStore(context).load(run.id).stopRequested)
    }
}
