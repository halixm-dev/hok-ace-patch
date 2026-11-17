package dev.halixm.hokacepatcher

import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.nio.file.Files
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Synthetic app-private metadata only. No binder/device/game APIs. Authored in pass 1; run in pass 2. */
class RunStoreProbeTest {
    private fun context(): Context {
        val actual = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(RunStore.privateRoot(actual), "run-store-probes/${UUID.randomUUID()}").apply { mkdirs() }
        return object : ContextWrapper(actual) { override fun getFilesDir() = root }
    }
    private fun start(context: Context, provider: ShellProvider = ShellProvider.SHIZUKU) =
        RunStore(context).start("translate", "en", provider, RunStore.Target.local(context))
    private fun path(context: Context, id: String) = File(context.filesDir, "runs/$id.json")
    private fun read(context: Context, id: String) = ArtifactReceipts.parse(path(context, id).readBytes())
    private fun save(context: Context, id: String, value: JSONObject) {
        value.remove("record_sha256"); value.put("record_sha256", ArtifactReceipts.identityKey(value))
        path(context, id).writeText(ArtifactReceipts.canonical(value))
    }
    private fun reject(action: () -> Unit) {
        try { action(); fail("Unapproved or malformed work accepted") } catch (_: Exception) { }
    }
    @Test fun durableIntentHasNoRoutineExpiryAndChoicesStayExact() {
        val context = context(); val run = start(context, ShellProvider.WIRELESS)
        val value = read(context, run.id)
        val auth = value.getJSONObject("authorization").put("authorized_ms", System.currentTimeMillis() - 24 * 60 * 60 * 1000L)
        value.put("authorization_key", ArtifactReceipts.identityKey(auth)); save(context, run.id, value)
        val oldProvider = ShellProvider.current(context); val oldLanguage = PatchLanguage.current(context)
        ShellProvider.set(context, ShellProvider.ROOT); PatchLanguage.set(context, "id")
        try {
            val restored = RunStore(context).load(run.id)
            assertTrue(restored.mayContinue); assertEquals(ShellProvider.WIRELESS, restored.provider); assertEquals("en", restored.language)
            assertEquals("translate", restored.action); assertEquals(restored.id, restored.sessionId)
            reject { RunStore(context).start("remove", "id", ShellProvider.ROOT, RunStore.Target.local(context)) }
        } finally { ShellProvider.set(context, oldProvider); PatchLanguage.set(context, oldLanguage) }
    }
    @Test fun attemptsAndStopSurviveNewStoreInstances() {
        val context = context(); val run = start(context)
        RunStore(context).beginAttempt(run.id, "preparation")
        RunStore(context).beginAttempt(run.id, "preparation")
        reject { RunStore(context).beginAttempt(run.id, "preparation") }
        RunStore(context).stop(run.id)
        val loaded = RunStore(context).load(run.id)
        assertFalse(loaded.continuation); assertTrue(loaded.stopRequested)
        assertEquals(2, loaded.attempts.getInt("preparation"))
        reject { RunStore(context).beginAttempt(run.id, "dispatch") }
        RunStore(context).resolve(run.id)
        assertEquals("stopped", RunStore(context).load(run.id).lifecycle)
    }
    @Test fun stopDoesNotWaitForCoordinatorHeldByLongWork() {
        val context = context(); val run = start(context)
        val acquired = CountDownLatch(1); val release = CountDownLatch(1)
        val thread = Thread { RunStore.coordinator(context) { acquired.countDown(); check(release.await(10, TimeUnit.SECONDS)) } }
        thread.start(); assertTrue(acquired.await(5, TimeUnit.SECONDS))
        try { assertTrue(RunStore(context).stop(run.id).stopRequested) }
        finally { release.countDown(); thread.join(5000) }
        assertFalse(thread.isAlive)
    }
    @Test fun wrongTypesProvidersUnknownFieldsAndTargetRefuseEvenWithRecomputedDigest() {
        val changes: List<(JSONObject) -> Unit> = listOf(
            { it.put("schema", "1") }, { it.put("stop_requested", "false") }, { it.put("continuation", 1) },
            { it.put("extra", true) }, { it.getJSONObject("attempts").put("dispatch", "1") },
            { it.getJSONObject("authorization").put("provider", "unknown") },
            { it.getJSONObject("authorization").getJSONObject("target").put("android_user", "0") },
            { it.getJSONObject("authorization").put("work_root", "/wrong-root") })
        for (change in changes) {
            val context = context(); val run = start(context); val value = read(context, run.id)
            change(value); value.put("authorization_key", ArtifactReceipts.identityKey(value.getJSONObject("authorization")))
            save(context, run.id, value); reject { RunStore(context).load(run.id) }
        }
    }
    @Test fun duplicateOversizeTraversalLinksAndNoStatusAuthorization() {
        val context = context(); val run = start(context); val path = path(context, run.id); val bytes = path.readBytes()
        path.writeText("{\"schema\":1," + String(bytes).removePrefix("{")); reject { RunStore(context).load(run.id) }
        path.writeBytes(ByteArray(ArtifactReceipts.MAX_JSON + 1) { 32 }); reject { RunStore(context).load(run.id) }
        path.writeBytes(bytes); reject { RunStore(context).load("../${run.id}") }
        val actual = File(context.filesDir, "saved-run"); path.renameTo(actual); Files.createSymbolicLink(path.toPath(), actual.toPath())
        reject { RunStore(context).load(run.id) }; Files.delete(path.toPath()); actual.renameTo(path)
        val missing = UUID.randomUUID().toString()
        File(context.filesDir, "worker-state.json").writeText("{\"status\":\"running\",\"run\":\"$missing\"}")
        reject { PatchWorkerService.dispatchRun(context, Intent().setAction("patch").putExtra("request", missing)) }
        reject { PatchWorkerService.dispatchRun(context, Intent().setAction("prepare")) }
        reject { PatchWorkerService.dispatchRun(context, Intent().setAction("remove").putExtra("request", run.id)) }
        assertFalse(PatchWorkerService.isWorking)
    }
    @Test fun legacyJournalIsSafetyOnlyAndCannotSupplyStartAuthority() {
        val context = context(); val hash = "a".repeat(64)
        val journal = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash)
        assertNull(journal.runId)
        reject { RunStore(context).load(journal.id) }
        reject { start(context) }
        reject { PatchCoordinator(context, IPrivilegedDeviceService.Stub.asInterface(android.os.Binder()), {}).run(hash, File(context.filesDir, "absent.apk")) }
    }
    @Test fun directFreshMutationPrimitivesRequireDispatchBeforeAnyDeviceCall() {
        val context = context(); val hash = "a".repeat(64)
        val noDevice = java.lang.reflect.Proxy.newProxyInstance(javaClass.classLoader,
            arrayOf(IPrivilegedDeviceService::class.java)) { _, _, _ -> error("Unauthorised primitive reached device") } as IPrivilegedDeviceService
        val coordinator = PatchCoordinator(context, noDevice, {})
        try { coordinator.run(hash, File(context.filesDir, "absent.apk")); fail("No Start accepted") }
        catch (error: IllegalStateException) { assertTrue(error.message.orEmpty().contains("durable Start")) }
        val identity = ApkIdentity(1, hash, PrivilegedDeviceService.GAME, 1, "private", GameSigner.CERTIFICATE_SHA256, false)
        try { coordinator.runRoot(File(context.filesDir, "absent.apk"), identity); fail("No Root Start accepted") }
        catch (error: IllegalStateException) { assertTrue(error.message.orEmpty().contains("durable Start")) }
        assertTrue(SessionJournal.history(File(context.filesDir, "sessions")).isEmpty())
    }
    @Test fun linkedRecoveryUsesSavedProviderEvenAfterStop() {
        val context = context(); val run = start(context, ShellProvider.WIRELESS); val hash = "a".repeat(64)
        SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        RunStore(context).stop(run.id)
        val restored = checkNotNull(PatchWorkerService.dispatchRun(context,
            Intent().setAction("recover").putExtra("session", run.id)))
        assertEquals(ShellProvider.WIRELESS, restored.provider); assertTrue(restored.stopRequested)
        reject { RunStore(context).resolve(run.id) }
    }
    private fun claimed(context: Context): RunStore.Run {
        val run = start(context); val value = read(context, run.id)
        value.put("lifecycle", "claimed"); save(context, run.id, value)
        return RunStore(context).load(run.id)
    }
    private fun identity(run: RunStore.Run, marker: String) = JSONObject()
        .put("target", run.target.json().put("provider", run.provider.key))
        .put("request", JSONObject().put("action", run.action).put("language", run.language).put("options", JSONObject()))
        .put("source", JSONObject().put("marker", marker))
    @Test fun postClaimInputLinkageNeedsTheCoordinatorAndStaysImmutable() {
        val context = context(); val run = claimed(context)
        reject { RunStore(context).bindInputs(run.id, identity(run, "a")) }
        assertNull(RunStore(context).load(run.id).inputIdentity)
        RunStore.coordinator(context) { RunStore(context).bindInputs(run.id, identity(run, "a")) }
        RunStore.coordinator(context) { RunStore(context).bindInputs(run.id, identity(run, "a")) }
        reject { RunStore.coordinator(context) { RunStore(context).bindInputs(run.id, identity(run, "b")) } }
        val wrong = identity(run, "a").put("request", JSONObject().put("action", "remove").put("language", run.language))
        reject { RunStore.coordinator(context) { RunStore(context).bindInputs(run.id, wrong) } }
        assertEquals(run.authorizationKey, RunStore(context).load(run.id).authorizationKey)
    }
    /** Pass 2: production roots resolve the platform's own data-folder alias once; app-made links never pass. */
    @Test fun privateRootTrustsOnlyThePlatformAlias() {
        val actual = InstrumentationRegistry.getInstrumentation().targetContext
        val root = RunStore.privateRoot(actual)
        android.util.Log.i("HokAceProbe", "filesDir=${actual.filesDir} canonical=${actual.filesDir.canonicalPath} " +
            "dataDir=${actual.dataDir} canonicalData=${actual.dataDir.canonicalPath}")
        assertEquals(root.toPath(), root.canonicalFile.toPath())
        assertEquals(File(root, "pristine"), PristineDelta.directory(actual))
        val nested = File(actual.filesDir, "run-store-probes/${UUID.randomUUID()}").apply { mkdirs() }
        assertEquals(nested.canonicalFile, RunStore.privateRoot(object : ContextWrapper(actual) { override fun getFilesDir() = nested }))
        assertEquals(nested.canonicalFile, RunStore.privateRoot(object : ContextWrapper(actual) {
            override fun getFilesDir() = nested.canonicalFile }))
        // A record built from the resolved root passes RunStore.safe's exact comparison.
        val record = File(nested.canonicalFile, "sessions/${UUID.randomUUID()}").apply { mkdirs() }
        RunStore.safe(nested.canonicalFile, record, true)
        val target = File(root, "run-store-probes/${UUID.randomUUID()}").apply { mkdirs() }
        val link = File(root, "run-store-probes/link-${UUID.randomUUID()}")
        Files.createSymbolicLink(link.toPath(), target.toPath())
        reject { RunStore.privateRoot(object : ContextWrapper(actual) { override fun getFilesDir() = link }) }
        reject { RunStore.privateRoot(object : ContextWrapper(actual) { override fun getFilesDir() = File(link, "inner") }) }
        reject { RunStore.privateRoot(object : ContextWrapper(actual) { override fun getFilesDir() = File("/data/local/tmp") }) }
        reject { RunStore.privateRoot(object : ContextWrapper(actual) { override fun getFilesDir() = actual.dataDir }) }
    }
    @Test fun invalidationNeedsAConsistentLinkedJournal() {
        val context = context(); val run = claimed(context); val hash = "a".repeat(64)
        RunStore.coordinator(context) { RunStore(context).bindInputs(run.id, identity(run, "a")) }
        // No journal yet: nothing proves consistency.
        reject { RunStore.coordinator(context) { RunStore(context).invalidateInputs(run.id) } }
        val journal = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        reject { RunStore(context).invalidateInputs(run.id) }
        journal.intent("write_file", JSONObject().put("path", "packages/1/1.db"))
        reject { RunStore.coordinator(context) { RunStore(context).invalidateInputs(run.id) } }
        assertNotNull(RunStore(context).load(run.id).inputIdentity)
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("packages_dirty", false))
        RunStore.coordinator(context) {
            RunStore(context).invalidateInputs(run.id)
            RunStore(context).bindInputs(run.id, identity(run, "b"))
        }
        assertEquals(ArtifactReceipts.identityKey(identity(run, "b")),
            ArtifactReceipts.identityKey(checkNotNull(RunStore(context).load(run.id).inputIdentity)))
        RunStore(context).stop(run.id)
        reject { RunStore.coordinator(context) { RunStore(context).invalidateInputs(run.id) } }
    }
    @Test fun oneAutomaticRetryPerLogicalOperationSurvivesReopenAndOnlyExplicitRetryRearmsSafeWork() {
        val context = context(); val run = start(context)
        // A failure before any operation began is charged to the start pseudo-operation.
        assertTrue(RunStore(context).recordFailure(run.id, "provider_lost"))
        assertEquals(RunStore.START_OPERATION, RunStore(context).load(run.id).failedOperation)
        assertFalse(RunStore(context).load(run.id).retryExhausted)
        // Waiting for the provider is saved as a reason, never as an attempt.
        RunStore(context).waitFor(run.id, "provider")
        assertEquals("provider", RunStore(context).load(run.id).waiting)
        assertEquals(1, RunStore(context).load(run.id).attempts.getInt(RunStore.START_OPERATION))
        // Each logical operation gets the initial attempt plus one automatic retry, persisted before dispatch.
        RunStore(context).beginAttempt(run.id, "snapshot")
        assertNull("Beginning work ends the wait", RunStore(context).load(run.id).waiting)
        assertTrue(RunStore(context).recordFailure(run.id, "error"))
        RunStore(context).beginAttempt(run.id, "snapshot")
        // The retry got further: a different operation fails and has its own budget.
        RunStore(context).beginAttempt(run.id, "build")
        assertTrue(RunStore(context).recordFailure(run.id, "interrupted"))
        assertEquals("build", RunStore(context).load(run.id).failedOperation)
        assertEquals("interrupted", RunStore(context).load(run.id).failureClass)
        assertFalse(RunStore(context).load(run.id).retryExhausted)
        // The same operation failing on its retry pauses persistently: a new store instance (reopen) sees it.
        RunStore(context).beginAttempt(run.id, "build")
        assertFalse(RunStore(context).recordFailure(run.id, "recovery_required"))
        val paused = RunStore(context).load(run.id)
        assertTrue(paused.retryExhausted); assertEquals("explicit_retry", paused.waiting)
        assertEquals("build", paused.failedOperation); assertEquals("recovery_required", paused.failureClass)
        reject { RunStore(context).beginAttempt(run.id, "build") }
        RunStore(context).beginAttempt(run.id, "uninstall")
        RunStore(context).beginAttempt(run.id, "redownload_delete")
        RunStore(context).beginAttempt(run.id, "first_setup")
        reject { RunStore(context).waitFor(run.id, "anything") }
        // Explicit Retry re-arms safe operations only; destructive counts and consent stay.
        val rearmed = RunStore(context).rearm(run.id)
        assertFalse(rearmed.retryExhausted); assertNull(rearmed.failure); assertNull(rearmed.waiting); assertNull(rearmed.lastOperation)
        assertFalse(rearmed.attempts.has("build")); assertFalse(rearmed.attempts.has("snapshot"))
        assertFalse(rearmed.attempts.has(RunStore.START_OPERATION))
        for (destructive in listOf("uninstall", "redownload_delete", "first_setup"))
            assertEquals("$destructive is never re-armed", 1, rearmed.attempts.getInt(destructive))
        RunStore(context).beginAttempt(run.id, "build")
        RunStore(context).stop(run.id)
        reject { RunStore(context).rearm(run.id) }
        reject { RunStore(context).recordFailure(run.id, "error") }
        reject { RunStore(context).waitFor(run.id, "provider") }
        assertTrue(RunStore(context).load(run.id).stopRequested)
    }
    private val sha = "0".repeat(64)
    private fun setupJournal(context: Context, parent: String?): FirstSetupJournal {
        val normal = ApkIdentity(1, sha, PrivilegedDeviceService.GAME, 1, "fixture", GameSigner.CERTIFICATE_SHA256, false)
        val source = ApkIdentity(1, sha, PrivilegedDeviceService.GAME, 1, "fixture", sha, false)
        val access = ApkIdentity(1, sha, PrivilegedDeviceService.GAME, 1, "fixture", GameSigner.CERTIFICATE_SHA256, true)
        val prepared = ApkPreparation.Prepared(File(context.filesDir, UUID.randomUUID().toString()), source, normal, access)
        return FirstSetupJournal.create(File(context.filesDir, "first-setups"), prepared, sha, true, null, parent)
    }
    @Test fun setupRecoveryUsesTheParentStartsProviderEvenAfterStop() {
        val context = context(); val run = start(context, ShellProvider.WIRELESS)
        val journal = setupJournal(context, run.id)
        assertEquals(run.id, FirstSetupJournal.load(journal.directory).parentRun)
        RunStore(context).stop(run.id)
        for (action in listOf("setup_recover", "setup_update")) {
            val restored = checkNotNull(PatchWorkerService.dispatchRun(context, Intent().setAction(action).putExtra("setup", journal.id)))
            assertEquals(ShellProvider.WIRELESS, restored.provider); assertTrue(restored.stopRequested)
        }
        // The parent stays unresolved while its setup is unfinished.
        reject { RunStore(context).resolve(run.id) }
        assertFalse(FirstSetupJournal.readyFor(context, run.id))
        // A legacy setup has no Start: it keeps the old current-provider path, never another run's.
        val legacy = context(); val old = setupJournal(legacy, null)
        assertNull(PatchWorkerService.dispatchRun(legacy, Intent().setAction("setup_recover").putExtra("setup", old.id)))
    }
    @Test fun destructiveSetupNeedsAContinuingNonRootParentStart() {
        for (case in 0..2) {
            val context = context()
            val run = start(context, if (case == 2) ShellProvider.ROOT else ShellProvider.SHIZUKU)
            val request = UUID.randomUUID().toString()
            File(context.filesDir, "setup-requests").mkdirs()
            File(context.filesDir, "setup-requests/$request.json").writeText(JSONObject().put("schema", 1).put("id", request)
                .put("parent_run", run.id).toString())
            assertEquals(run.id, FirstSetupRequestStore(context).parent(request))
            if (case == 1) RunStore(context).stop(run.id)
            val dispatch = { PatchWorkerService.dispatchRun(context, Intent().setAction("first_setup").putExtra("request", request)) }
            if (case == 0) assertEquals(run.id, checkNotNull(dispatch()).id) else reject { dispatch() }
        }
        assertFalse(PatchWorkerService.isWorking)
    }
    private fun offer(context: Context, run: RunStore.Run, digest: String, plan: String = UUID.randomUUID().toString()) =
        RunStore.coordinator(context) { RunStore(context).proposeRedownload(run.id, plan, digest, 3, listOf("1", "21"), 4096) }
    @Test fun redownloadConsentIsScopedToOnePlanDigestAndOnlyTheUserAnswers() {
        val context = context(); val run = claimed(context); val a = "a".repeat(64); val b = "b".repeat(64)
        // Only the coordinator measures and offers a plan; nothing is approved by offering it.
        reject { RunStore(context).proposeRedownload(run.id, UUID.randomUUID().toString(), a, 3, listOf("1"), 1) }
        offer(context, run, a)
        val offered = checkNotNull(RunStore(context).load(run.id).redownload)
        assertEquals(RunStore.REDOWNLOAD_AWAITING, offered.state); assertFalse(offered.approved); assertTrue(offered.needsAnswer)
        assertNull(offered.approvalId); assertEquals(listOf("1", "21"), offered.packages); assertEquals(3, offered.files)
        // The progress primitives never stand in for an approval.
        reject { RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) } }
        reject { RunStore(context).approveRedownload(run.id, b) }
        reject { RunStore(context).declineRedownload(run.id, b) }
        // A refusal is saved and deterministic: no deletion state, and the same digest keeps the answer.
        RunStore(context).declineRedownload(run.id, a)
        assertEquals(RunStore.REDOWNLOAD_DECLINED, RunStore(context).load(run.id).redownload?.state)
        offer(context, run, a)
        assertEquals(RunStore.REDOWNLOAD_DECLINED, RunStore(context).load(run.id).redownload?.state)
        reject { RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) } }
        // The user can still approve the same plan after a refusal.
        val approved = checkNotNull(RunStore(context).approveRedownload(run.id, a).redownload)
        assertTrue(approved.approved); assertNotNull(approved.approvalId); assertTrue(checkNotNull(approved.approvedMs) > 0)
        reject { RunStore(context).approveRedownload(run.id, a) }
        // Re-offering the same digest after a restart keeps the approval; a changed plan needs a new one.
        offer(context, run, a)
        assertEquals(approved.approvalId, RunStore(context).load(run.id).redownload?.approvalId)
        offer(context, run, b)
        val changed = checkNotNull(RunStore(context).load(run.id).redownload)
        assertEquals(RunStore.REDOWNLOAD_AWAITING, changed.state); assertNull(changed.approvalId); assertEquals(b, changed.planSha256)
        reject { RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) } }
    }
    @Test fun anApprovedRedownloadIsConsumedOnceAndItsDeletionBudgetNeverRearms() {
        val context = context(); val run = claimed(context); val a = "a".repeat(64)
        offer(context, run, a)
        RunStore(context).beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        RunStore(context).beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        // A fresh approval is the only thing that resets the deletion budget.
        RunStore(context).approveRedownload(run.id, a)
        assertFalse(RunStore(context).load(run.id).attempts.has(RunStore.REDOWNLOAD_DELETE))
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) }
        RunStore(context).beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        assertEquals(1, RunStore(context).rearm(run.id).attempts.getInt(RunStore.REDOWNLOAD_DELETE))
        // Downloads cannot be confirmed before the deletion finished.
        reject { RunStore(context).confirmRedownloadDownloads(run.id) }
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETED) }
        val deleted = checkNotNull(RunStore(context).load(run.id).redownload)
        assertFalse("A consumed approval deletes nothing again", deleted.approved); assertFalse(deleted.needsAnswer)
        reject { RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) } }
        assertEquals(RunStore.REDOWNLOAD_DOWNLOADS_CONFIRMED, RunStore(context).confirmRedownloadDownloads(run.id).redownload?.state)
        // The game still downloading sends it back to the download wait, never to deletion.
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETED) }
        assertEquals(RunStore.REDOWNLOAD_DELETED, RunStore(context).load(run.id).redownload?.state)
    }
    @Test fun aConfirmedRedownloadDownloadAnswersOnlyTheSnapshotItMadeStaleOnce() {
        val context = context(); val run = claimed(context); val runs = RunStore(context)
        val a = "a".repeat(64); val stale = "c".repeat(64); val later = "d".repeat(64)
        offer(context, run, a)
        runs.approveRedownload(run.id, a)
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) }
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETED) }
        // Before Downloads finished, the deletion answers nothing.
        reject { RunStore.coordinator(context) { RunStore(context).confirmSourceDownloadsAfterRedownload(run.id, stale, a) } }
        runs.confirmRedownloadDownloads(run.id)
        // Coordinator only, and only for this run's own deleted plan.
        reject { runs.confirmSourceDownloadsAfterRedownload(run.id, stale, a) }
        reject { RunStore.coordinator(context) { RunStore(context).confirmSourceDownloadsAfterRedownload(run.id, stale, "b".repeat(64)) } }
        RunStore.coordinator(context) { RunStore(context).confirmSourceDownloadsAfterRedownload(run.id, stale, a) }
        assertTrue(runs.sourceDownloadsConfirmed(run.id, stale))
        assertFalse(runs.sourceDownloadsConfirmed(run.id, later))
        // The coordinator spends it on the retake; a later change of the retaken snapshot needs a new answer.
        runs.consumeSourceDownloads(run.id)
        runs.requireSourceDownloads(run.id, later)
        assertFalse(runs.sourceDownloadsConfirmed(run.id, later))
        // A readiness refusal sends the plan back to the download wait: nothing answers until Downloads finished.
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETED) }
        reject { RunStore.coordinator(context) { RunStore(context).confirmSourceDownloadsAfterRedownload(run.id, later, a) } }
        runs.stop(run.id)
        reject { RunStore.coordinator(context) { RunStore(context).confirmSourceDownloadsAfterRedownload(run.id, later, a) } }
    }
    private fun offerAutomatically(context: Context, run: RunStore.Run, digest: String, packages: List<String> = listOf("15")) =
        RunStore.coordinator(context) {
            RunStore(context).proposeRedownload(run.id, UUID.randomUUID().toString(), digest, 3, packages, 4096, automatic = true)
        }
    // User decision 2026-11-13: the coordinator approves a measured plan itself, at most once per package per run.
    @Test fun automaticRedownloadApprovesOncePerPackageAndAChangedPlanAgain() {
        val context = context(); val run = claimed(context); val runs = RunStore(context)
        val a = "a".repeat(64); val b = "b".repeat(64); val c = "c".repeat(64); val d = "d".repeat(64)
        // Only the coordinator approves automatically.
        reject { runs.proposeRedownload(run.id, UUID.randomUUID().toString(), a, 3, listOf("15"), 1, automatic = true) }
        val first = checkNotNull(offerAutomatically(context, run, a).redownload)
        assertTrue(first.approved); assertEquals(RunStore.APPROVAL_AUTOMATIC, first.approvalSource)
        // A changed plan before any deletion replaces the approval and is approved again automatically.
        val changed = checkNotNull(offerAutomatically(context, run, b).redownload)
        assertTrue(changed.approved); assertEquals(b, changed.planSha256); assertNotEquals(first.approvalId, changed.approvalId)
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, b, RunStore.REDOWNLOAD_DELETING) }
        runs.beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, b, RunStore.REDOWNLOAD_DELETED) }
        assertEquals(listOf("15"), runs.load(run.id).redownloadedPackages)
        runs.confirmRedownloadDownloads(run.id)
        // The loop guard: the same package damaged again after its download waits for the user's review.
        val again = checkNotNull(offerAutomatically(context, run, c, listOf("1", "15")).redownload)
        assertEquals(RunStore.REDOWNLOAD_AWAITING, again.state); assertFalse(again.approved); assertTrue(again.needsAnswer)
        // Re-offering it (a restart) still holds it back; the user's review can approve it.
        assertFalse(checkNotNull(offerAutomatically(context, run, c, listOf("1", "15")).redownload).approved)
        val reviewed = checkNotNull(runs.approveRedownload(run.id, c).redownload)
        assertTrue(reviewed.approved); assertEquals(RunStore.APPROVAL_USER, reviewed.approvalSource)
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, c, RunStore.REDOWNLOAD_DELETING) }
        RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, c, RunStore.REDOWNLOAD_DELETED) }
        assertEquals(setOf("1", "15"), runs.load(run.id).redownloadedPackages.toSet())
        runs.confirmRedownloadDownloads(run.id)
        // Another package in the same run is still approved automatically.
        assertTrue(checkNotNull(offerAutomatically(context, run, d, listOf("21")).redownload).approved)
    }
    @Test fun automaticRedownloadLeavesASpentDeletionBudgetToTheUser() {
        val context = context(); val run = claimed(context); val a = "a".repeat(64)
        offerAutomatically(context, run, a)
        RunStore(context).beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        RunStore(context).beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        RunStore.coordinator(context) { RunStore(context).requireFreshRedownloadConsent(run.id, a) }
        // Interrupted twice: neither the same plan nor a changed one is approved by itself.
        assertFalse(checkNotNull(offerAutomatically(context, run, a).redownload).approved)
        assertFalse(checkNotNull(offerAutomatically(context, run, "b".repeat(64)).redownload).approved)
    }
    @Test fun aSpentApprovalAsksAgainAndStopEndsEveryAnswer() {
        val context = context(); val run = claimed(context); val a = "a".repeat(64)
        offer(context, run, a)
        RunStore(context).approveRedownload(run.id, a)
        reject { RunStore(context).requireFreshRedownloadConsent(run.id, a) }
        RunStore.coordinator(context) { RunStore(context).requireFreshRedownloadConsent(run.id, a) }
        val fresh = checkNotNull(RunStore(context).load(run.id).redownload)
        assertEquals(RunStore.REDOWNLOAD_AWAITING, fresh.state); assertNull(fresh.approvalId)
        RunStore(context).stop(run.id)
        reject { RunStore(context).approveRedownload(run.id, a) }
        reject { RunStore(context).confirmRedownloadDownloads(run.id) }
        reject { offer(context, run, a) }
        reject { RunStore.coordinator(context) { RunStore(context).redownloadProgress(run.id, a, RunStore.REDOWNLOAD_DELETING) } }
    }
    @Test fun malformedRedownloadRecordsRefuseEvenWithRecomputedDigest() {
        val a = "a".repeat(64)
        val changes: List<(JSONObject) -> Unit> = listOf(
            { it.put("state", "approved") }, // approved without an approval
            { it.put("state", "granted") }, { it.put("plan_sha256", "A".repeat(64)) }, { it.put("files", 0) },
            { it.put("packages", org.json.JSONArray().put("1").put("1")) }, { it.put("packages", org.json.JSONArray().put("x")) },
            { it.put("bytes", -1) }, { it.put("extra", true) }, { it.put("plan_id", "../plan") },
            { it.put("approval", JSONObject().put("id", UUID.randomUUID().toString()).put("approved_ms", 1)) },
            // An approval names only the coordinator or the user as its source.
            { it.put("state", "approved").put("approval", JSONObject().put("id", UUID.randomUUID().toString())
                .put("approved_ms", 1).put("source", "start")) })
        for (change in changes) {
            val context = context(); val run = claimed(context); offer(context, run, a)
            val value = read(context, run.id); change(value.getJSONObject("redownload"))
            save(context, run.id, value); reject { RunStore(context).load(run.id) }
        }
    }
    @Test fun changedSourceRequiresASeparatePersistedDownloadAnswerOnSameAuthorization() {
        val context = context(); val run = claimed(context); val runs = RunStore(context)
        val first = "a".repeat(64); val second = "b".repeat(64)
        runs.requireSourceDownloads(run.id, first)
        assertEquals("required", RunStore(context).load(run.id).sourceDownloads)
        assertFalse(runs.sourceDownloadsConfirmed(run.id, first))
        runs.rearm(run.id) // Retry cannot answer readiness.
        assertFalse(runs.sourceDownloadsConfirmed(run.id, first))
        runs.confirmSourceDownloads(run.id)
        assertTrue(RunStore(context).sourceDownloadsConfirmed(run.id, first))
        assertFalse(runs.sourceDownloadsConfirmed(run.id, second))
        runs.requireSourceDownloads(run.id, second)
        assertEquals("required", runs.load(run.id).sourceDownloads)
        assertEquals(run.authorizationKey, runs.load(run.id).authorizationKey)
        runs.stop(run.id)
        reject { runs.confirmSourceDownloads(run.id) }
        reject { runs.consumeSourceDownloads(run.id) }
    }
    @Test fun safetyAccessAuditBudgetSurvivesReopenAndStopWithoutLooping() {
        val context = context(); val run = claimed(context)
        RunStore(context).beginSafetyAttempt(run.id, "recovery_access_audit")
        RunStore(context).stop(run.id)
        RunStore(context).beginSafetyAttempt(run.id, "recovery_access_audit")
        reject { RunStore(context).beginSafetyAttempt(run.id, "recovery_access_audit") }
        reject { RunStore(context).beginSafetyAttempt(run.id, "uninstall") }
        assertEquals(2, RunStore(context).load(run.id).attempts.getInt("recovery_access_audit"))
        assertFalse(RunStore(context).load(run.id).mayContinue)
    }

    @Test fun explicitStoppedRecoveryRetryRearmsOnlySafetyInstalls() {
        val context = context(); val run = claimed(context); val runs = RunStore(context)
        runs.beginAttempt(run.id, "uninstall")
        runs.beginAttempt(run.id, RunStore.REDOWNLOAD_DELETE)
        runs.stop(run.id)
        for (operation in listOf("recovery_access_audit", "recovery_rollback_access",
            "recovery_normal_restore", "recovery_emergency_normal")) {
            runs.beginSafetyAttempt(run.id, operation); runs.beginSafetyAttempt(run.id, operation)
            reject { RunStore(context).beginSafetyAttempt(run.id, operation) }
        }
        runs.rearmSafety(run.id)
        val saved = RunStore(context).load(run.id)
        assertTrue(saved.stopRequested); assertFalse(saved.mayContinue)
        assertEquals(1, saved.attempts.getInt("uninstall"))
        assertEquals(1, saved.attempts.getInt(RunStore.REDOWNLOAD_DELETE))
        runs.beginSafetyAttempt(run.id, "recovery_normal_restore")
        assertEquals(1, RunStore(context).load(run.id).attempts.getInt("recovery_normal_restore"))
    }

    @Test fun concurrentStoreOperationsSerializeInProcessWithoutOverlappingFileLock() {
        val context = context(); val run = start(context)
        val ready = CountDownLatch(8)
        val go = CountDownLatch(1)
        val errors = java.util.Collections.synchronizedList(mutableListOf<Throwable>())
        val workers = (0 until 8).map { worker ->
            Thread {
                ready.countDown()
                if (!go.await(5, TimeUnit.SECONDS)) return@Thread
                try {
                    val runs = RunStore(context)
                    repeat(25) { step ->
                        assertEquals(1, runs.pending().size)
                        assertEquals(run.id, runs.load(run.id).id)
                        assertFalse(runs.sourceDownloadsConfirmed(run.id, sha))
                        if (worker == 0) runs.waitFor(run.id, if (step % 2 == 0) "provider" else null)
                    }
                } catch (t: Throwable) {
                    errors.add(t)
                }
            }
        }
        workers.forEach { it.start() }
        assertTrue(ready.await(5, TimeUnit.SECONDS))
        go.countDown()
        workers.forEach { it.join(15_000); assertFalse(it.isAlive) }
        assertTrue("Concurrent store access failed: ${errors.firstOrNull()}", errors.isEmpty())
    }

    @Test fun cleanSafetyFallbackRestoresFailingOperationWhileFailedSafetyStaysChargedToSafety() {
        val context = context(); val run = claimed(context); val runs = RunStore(context)
        runs.beginAttempt(run.id, "build")
        runs.beginSafetyAttempt(run.id, "recovery_normal_restore")
        RunStore.coordinator(context) { runs.restoreOperation(run.id, "build") }
        assertTrue(runs.recordFailure(run.id, "error"))
        val afterOrdinary = runs.load(run.id)
        assertEquals("build", afterOrdinary.failedOperation)
        assertEquals(1, afterOrdinary.attempts.getInt("recovery_normal_restore"))
        runs.beginAttempt(run.id, "apply")
        runs.beginSafetyAttempt(run.id, "recovery_rollback_access")
        assertTrue(runs.recordFailure(run.id, "recovery_required"))
        assertEquals("recovery_rollback_access", runs.load(run.id).failedOperation)
    }

}
