package dev.halixm.hokacepatcher

import android.content.Context
import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.lang.reflect.Proxy
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Synthetic app-private metadata only. Any unexpected device call fails; no real game reads/writes. */
class StorageRetentionProbeTest {
    private val hash = "a".repeat(64)
    private fun context(space: (() -> Long)? = null): Context {
        val real = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(RunStore.privateRoot(real), "storage-probes/${UUID.randomUUID()}").apply { mkdirs() }
        val disk = object : File(root.path) { override fun getUsableSpace() = space?.invoke() ?: super.getUsableSpace() }
        return object : ContextWrapper(real) { override fun getFilesDir() = disk }
    }
    private fun resolvedCache(context: Context): Pair<SessionJournal, File> {
        val runs = RunStore(context)
        val run = runs.start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        val journal = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("normal_verified", true))
        journal.outcome(PatchPhase.CANCELLED, JSONObject().put("normal_verified", true))
        val bytes = File(journal.directory, "snapshot/packages/cache").apply { parentFile!!.mkdirs(); writeText("optional cache") }
        File(journal.directory, "snapshot/${ArtifactReceipts.NAME}").writeText("synthetic receipt")
        runs.stop(run.id); runs.resolve(run.id)
        return journal to bytes
    }
    private fun guard(context: Context): JSONObject = RunStore.coordinator(context) {
        val method = PatchCoordinator::class.java.getDeclaredMethod("requireSpace", String::class.java, LongArray::class.java)
            .apply { isAccessible = true }
        method.invoke(coordinator(context), "snapshot", longArrayOf(100L)) as JSONObject
    }
    @Test fun pressureEvictsResolvedCacheAndContinuesWithoutTouchingCurrentArtifacts() {
        lateinit var cache: File
        var enough = true
        val context = context { if (enough || !cache.exists()) Long.MAX_VALUE else 0L }
        val (old, bytes) = resolvedCache(context); cache = bytes
        val runs = RunStore(context)
        val run = runs.start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        val current = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        val required = File(current.directory, "snapshot/packages/required").apply { parentFile!!.mkdirs(); writeText("required") }
        val delta = File(PristineDelta.directory(context), "delta.bin").apply { parentFile!!.mkdirs(); writeText("pristine") }
        guard(context)
        assertTrue(cache.exists()) // A fitting budget never invalidates reusable cache.
        enough = false
        assertEquals(StorageBudget.required(100L), guard(context).getLong("required_bytes"))
        assertFalse(cache.exists())
        assertFalse(File(old.directory, "snapshot/${ArtifactReceipts.NAME}").exists())
        assertTrue(File(old.directory, "journal.json").exists())
        assertEquals("required", required.readText()); assertEquals("pristine", delta.readText())
        assertEquals(0, runs.load(run.id).attempts.length())
    }
    @Test fun unresolvedReferencePinsResolvedCacheDuringPressure() {
        val context = context { 0L }
        val (old, cache) = resolvedCache(context)
        val runs = RunStore(context)
        val run = runs.start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        val current = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        android.system.Os.symlink(cache.path, File(current.directory, "required-cache").path)
        try { guard(context); fail("Pinned bytes satisfied an empty budget") }
        catch (error: java.lang.reflect.InvocationTargetException) { assertTrue(error.cause is StorageBudget.Shortage) }
        assertTrue(cache.exists()); assertTrue(File(old.directory, "snapshot/${ArtifactReceipts.NAME}").exists())
        assertEquals(0, runs.load(run.id).attempts.length())
    }
    @Test fun corruptRunRecordPinsOptionalCacheRatherThanGuessing() {
        val context = context { 0L }
        val (_, cache) = resolvedCache(context)
        File(context.filesDir, "runs/${UUID.randomUUID()}.json").writeText("broken record")
        try { guard(context); fail("Corrupt authorization permitted cleanup") }
        catch (error: java.lang.reflect.InvocationTargetException) { assertTrue(error.cause is StorageBudget.Shortage) }
        assertTrue(cache.exists())
    }
    @Test fun adoptionSourceStaysPinnedUntilItsOwnedCopyExists() {
        val context = context { 0L }
        val (old, cache) = resolvedCache(context)
        val coordinator = coordinator(context)
        val field = PatchCoordinator::class.java.getDeclaredField("adoptingSessions").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST") val adopting = field.get(coordinator) as MutableSet<String>
        adopting += old.id
        val release = PatchCoordinator::class.java.getDeclaredMethod("releaseResolvedSessions", Boolean::class.javaPrimitiveType)
            .apply { isAccessible = true }
        RunStore.coordinator(context) { release.invoke(coordinator, false) }
        assertTrue(cache.exists())
        adopting -= old.id
        RunStore.coordinator(context) { release.invoke(coordinator, false) }
        assertFalse(cache.exists())
    }
    private fun coordinator(context: Context): PatchCoordinator {
        val fake = Proxy.newProxyInstance(IPrivilegedDeviceService::class.java.classLoader,
            arrayOf(IPrivilegedDeviceService::class.java)) { _, method, _ ->
            if (method.name == "releaseReplacedGameApks") "{\"freed_bytes\":0}"
            else throw AssertionError("Unexpected device call: ${method.name}")
        } as IPrivilegedDeviceService
        return PatchCoordinator(context, fake, {})
    }
    private fun pendingJournal(context: Context): SessionJournal {
        val run = RunStore(context).start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        return SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
    }
    private fun retire(journal: SessionJournal): File {
        val id = UUID.randomUUID().toString()
        val attempt = File(journal.directory, "snapshot-attempts/$id").apply { mkdirs() }
        File(attempt, "attempt-owner.json").writeText("owner marker")
        File(attempt, "retired/packages/old").apply { parentFile!!.mkdirs(); writeText("replaced snapshot bytes") }
        File(attempt, "retired/${ArtifactReceipts.NAME}").writeText("synthetic receipt")
        journal.record(JSONObject().put("retired_snapshots", org.json.JSONArray().put(id)).put("snapshot_attempt", ""))
        return File(attempt, "retired")
    }
    private fun activate(coordinator: PatchCoordinator, journal: SessionJournal) {
        val field = PatchCoordinator::class.java.getDeclaredField("activeJournal").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST") (field.get(coordinator) as java.util.concurrent.atomic.AtomicReference<SessionJournal?>).set(journal)
    }
    private fun guard(context: Context, coordinator: PatchCoordinator): JSONObject = RunStore.coordinator(context) {
        val method = PatchCoordinator::class.java.getDeclaredMethod("requireSpace", String::class.java, LongArray::class.java)
            .apply { isAccessible = true }
        method.invoke(coordinator, "snapshot", longArrayOf(100L)) as JSONObject
    }
    /** The 2026-11-12 phone case: the pinned run's own retired snapshot is the space the fresh snapshot needs. */
    @Test fun pressureReleasesActiveRunsRetiredSnapshotButKeepsItsHistoryAndCurrentSnapshot() {
        var marker: File? = null
        val context = context { if (marker?.exists() == true) 0L else Long.MAX_VALUE }
        val journal = pendingJournal(context)
        val retired = retire(journal); marker = retired
        val owner = File(retired.parentFile, "attempt-owner.json")
        val current = File(journal.directory, "snapshot/packages/required").apply { parentFile!!.mkdirs(); writeText("required") }
        val coordinator = coordinator(context); activate(coordinator, journal)
        assertEquals(StorageBudget.required(100L), guard(context, coordinator).getLong("required_bytes"))
        assertFalse(retired.exists())
        assertTrue(owner.exists()); assertEquals("required", current.readText())
        val saved = SessionJournal.load(journal.directory).snapshot()
        val id = retired.parentFile!!.name
        assertEquals(id, saved.getJSONArray("retired_snapshots").getString(0))
        assertEquals(id, saved.getJSONArray(RetiredSnapshots.RELEASED).getString(0))
    }
    @Test fun linkedRetiredSnapshotStaysAndTheBudgetStillWaits() {
        val context = context { 0L }
        val journal = pendingJournal(context)
        val retired = retire(journal)
        val preparations = File(context.filesDir, "preparations").apply { mkdirs() }
        android.system.Os.symlink(File(retired, "packages/old").path, File(preparations, "needed").path)
        val coordinator = coordinator(context); activate(coordinator, journal)
        try { guard(context, coordinator); fail("Linked retired bytes satisfied an empty budget") }
        catch (error: java.lang.reflect.InvocationTargetException) { assertTrue(error.cause is StorageBudget.Shortage) }
        assertTrue(File(retired, "packages/old").exists()); assertTrue(File(retired, ArtifactReceipts.NAME).exists())
        assertFalse(SessionJournal.load(journal.directory).snapshot().has(RetiredSnapshots.RELEASED))
    }
    @Test fun pressureRemovesOnlyUnreferencedEarlierEngineFolders() {
        val context = context { 0L }
        val journal = pendingJournal(context) // engine_id = hash: a pending session's engine stays.
        val digest = context.assets.open("engine/manifest.json").use { java.security.MessageDigest.getInstance("SHA-256").digest(it.readBytes()) }
            .joinToString("") { "%02x".format(it) }
        val engine = File(context.filesDir, "engine")
        fun folder(name: String) = File(engine, "$name/payload").apply { parentFile!!.mkdirs(); writeText(name) }
        val now = folder(digest); val pinned = folder(hash); val stale = folder("b".repeat(64))
        val linked = folder("c".repeat(64)); val other = folder("notes")
        android.system.Os.symlink(linked.path, File(journal.directory, "engine-link").path)
        val coordinator = coordinator(context); activate(coordinator, journal)
        try { guard(context, coordinator); fail("An empty disk satisfied the budget") }
        catch (error: java.lang.reflect.InvocationTargetException) { assertTrue(error.cause is StorageBudget.Shortage) }
        assertFalse(stale.exists()); assertFalse(stale.parentFile!!.exists())
        for (kept in listOf(now, pinned, linked, other)) assertTrue(kept.path, kept.exists())
    }
    @Test fun storageWaitSurvivesStoreReopenWithoutAttemptsOrAccessInstall() {
        val context = context(); val runs = RunStore(context)
        val run = runs.start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        val journal = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("normal_verified", true))
        journal.outcome(PatchPhase.CANCELLED, JSONObject().put("normal_verified", true))
        journal.record(JSONObject().put("waiting_reason", "storage").put("storage_wait",
            JSONObject().put("phase", "snapshot").put("required_bytes", 1_000_000_000_000L)))
        runs.waitFor(run.id, "storage")
        val coordinator = coordinator(context)
        val method = PatchCoordinator::class.java.declaredMethods.single { it.name == "waitingStep" }.apply { isAccessible = true }
        val constructor = method.parameterTypes[2].declaredConstructors.single { it.parameterTypes.size == 7 }.apply { isAccessible = true }
        val apks = constructor.newInstance(hash, File(context.filesDir, "unused.apk"), null, null, null, 0L, null)
        repeat(3) {
            val waiting = method.invoke(coordinator, SessionJournal.load(journal.directory), RunStore(context).load(run.id), apks) as JSONObject
            assertEquals("storage", waiting.getString("reason"))
            assertEquals(0, RunStore(context).load(run.id).attempts.length())
        }
        journal.record(JSONObject().put("storage_wait", JSONObject().put("phase", "snapshot").put("required_bytes", 1)))
        assertNull(method.invoke(coordinator, journal, runs.load(run.id), apks))
        assertNull(runs.load(run.id).waiting)
        assertEquals(0, runs.load(run.id).attempts.length())
    }
    @Test fun explicitFreeSpaceEvictsNewestResolvedCacheButKeepsActivePristineDelta() {
        val context = context(); val runs = RunStore(context)
        val run = runs.start("translate", "en", ShellProvider.SHIZUKU, RunStore.Target.local(context))
        val journal = SessionJournal.create(File(context.filesDir, "sessions"), hash, hash, null, run.id, run.authorizationKey)
        journal.outcome(PatchPhase.RESTORING, JSONObject().put("normal_verified", true))
        journal.outcome(PatchPhase.CANCELLED, JSONObject().put("normal_verified", true))
        val receipt = File(journal.directory, "snapshot/${ArtifactReceipts.NAME}").apply { parentFile!!.mkdirs(); writeText("synthetic receipt") }
        val bytes = File(journal.directory, "snapshot/packages/cache").apply { parentFile!!.mkdirs(); writeText("optional cache") }
        val active = File(PristineDelta.directory(context), "delta.bin").apply { parentFile!!.mkdirs(); writeText("required pristine bytes") }
        // Pending authorization must block cleanup, even when its journal is consistent.
        try { coordinator(context).freeSpace(); fail("Pending action released") } catch (_: IllegalStateException) { }
        assertTrue(receipt.exists()); assertTrue(bytes.exists())
        runs.stop(run.id); runs.resolve(run.id)
        val coordinator = coordinator(context)
        val auto = PatchCoordinator::class.java.getDeclaredMethod("releaseResolvedSessions", Boolean::class.javaPrimitiveType).apply { isAccessible = true }
        auto.invoke(coordinator, true)
        assertTrue(receipt.exists()); assertTrue(bytes.exists())
        coordinator.freeSpace()
        assertFalse(receipt.exists()); assertFalse(bytes.exists())
        assertEquals("required pristine bytes", active.readText())
    }
}
