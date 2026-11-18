package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Run the real recovery coordinator in an isolated context. APK installation is strictly fake. */
@RunWith(AndroidJUnit4.class)
public final class CoordinatorRecoveryProbeTest {
    private static byte[] bytes(String text) { return text.getBytes(StandardCharsets.UTF_8); }
    private static String hash(byte[] value) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(value));
    }
    private static String hex(byte[] value) {
        StringBuilder result = new StringBuilder();
        for (byte part : value) result.append(String.format("%02x", part & 255));
        return result.toString();
    }
    private static void put(File path, byte[] value) throws Exception {
        assertTrue(path.getParentFile().isDirectory() || path.getParentFile().mkdirs());
        try (FileOutputStream output = new FileOutputStream(path)) { output.write(value); output.getFD().sync(); }
    }
    private static byte[] small(ParcelFileDescriptor source) throws Exception {
        try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
            ParcelFileDescriptor.dup(source.getFileDescriptor()))) {
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) >= 0) {
                result.write(buffer, 0, count);
                if (result.size() > 1024 * 1024) throw new IllegalStateException("Oversized fake file");
            }
            return result.toByteArray();
        }
    }
    private static final class Device extends IPrivilegedDeviceService.Stub {
        final Map<String, byte[]> files = new HashMap<>();
        final ApkIdentity normal, access;
        ApkIdentity installed;
        int writes, failWriteAt, installs;
        boolean failNormalOnce;
        /** The audit's own wording for a layer the game changed; anything else is an audit failure. */
        String changedLayerMessage = "Device command failed (1): Game file changed: ";
        Device(ApkIdentity normal, ApkIdentity access) { this.normal = normal; this.access = access; installed = access; }
        @Override public String estimateGameSnapshot() { throw new UnsupportedOperationException("No snapshot measurement in this fixture"); }
        @Override public void forceStopGame() { /* Fake installed game only; never invoke Android shell. */ }
        @Override public String replaceGameApk(ParcelFileDescriptor source, long length) {
            try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
                ParcelFileDescriptor.dup(source.getFileDescriptor()))) {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] buffer = new byte[1024 * 1024]; long total = 0; int count;
                while ((count = input.read(buffer)) >= 0) { total += count; assertTrue(total <= length); digest.update(buffer, 0, count); }
                assertEquals(length, total);
                String actual = hex(digest.digest());
                assertTrue("Unknown fake APK", actual.equals(normal.getSha256()) || actual.equals(access.getSha256()));
                installed = actual.equals(normal.getSha256()) ? normal : access;
                installs++;
                if (installed == normal && failNormalOnce) {
                    failNormalOnce = false;
                    throw new IllegalStateException("Fake normal install committed before acknowledgment loss");
                }
                return "fake installed";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String writeGameFile(String session, String relative, ParcelFileDescriptor source, long length, String sha256) {
            try {
                GameFilePolicy.INSTANCE.session(session); GameFilePolicy.INSTANCE.validate(relative, true);
                byte[] value = small(source); assertEquals(length, value.length); assertEquals(sha256, hash(value));
                files.put(relative, value);
                if (++writes == failWriteAt) throw new IllegalStateException("Fake file committed before acknowledgment loss");
                return "fake verified";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String reconcileGameFiles(String session, String operation, String relative,
                ParcelFileDescriptor policy, ParcelFileDescriptor source, long length, String sha256) {
            return PrivateRecoveryPolicy.apply(this, files, session, operation, relative, policy, source, length, sha256);
        }
        @Override public String validateGameSnapshot(ParcelFileDescriptor descriptor) {
            try {
                JSONObject expected = new JSONObject(new String(small(descriptor), StandardCharsets.UTF_8)).getJSONObject("files");
                assertEquals(expected.length(), files.size());
                for (String name : files.keySet()) if (!expected.getJSONObject(name).getString("sha256").equals(hash(files.get(name))))
                    throw new IllegalStateException(changedLayerMessage + name);
                return "fake verified";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public void clearGameWatchdog() { files.keySet().removeIf(name -> name.startsWith("Watchdog/")); }
        @Override public void clearSessionTemp(String session, String relative) { GameFilePolicy.INSTANCE.session(session); }
        @Override public void restoreWatchdogDirectory(String relative) { GameFilePolicy.INSTANCE.watchdogDirectory(relative); }
        @Override public String diagnostics() { throw new UnsupportedOperationException(); }
        @Override public String gameApkInfo() { throw new UnsupportedOperationException(); }
        @Override public String copyGameApk(ParcelFileDescriptor destination) { throw new UnsupportedOperationException(); }
        @Override public byte[] probeFixture(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String reinstallFixture(boolean abandon) { throw new UnsupportedOperationException(); }
        @Override public String probeGame(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String snapshotGame(ParcelFileDescriptor destination, long maximumBytes) { throw new UnsupportedOperationException(); }
        @Override public void validateFirstSetupSource(String sha) { throw new UnsupportedOperationException(); }
        @Override public void checkGameProfiles() { throw new UnsupportedOperationException(); }
        @Override public String releaseReplacedGameApks() { return "{\"released\":false,\"freed_bytes\":0}"; }
        @Override public void deleteGameFile(String session, String relative, String sha) { files.remove(relative); }
        @Override public boolean firstSetupGameAbsent() { throw new UnsupportedOperationException(); }
        @Override public void removeGameForFirstSetup(String sha) { throw new UnsupportedOperationException(); }
        @Override public String installFirstSetupGame(ParcelFileDescriptor source, long length) { throw new UnsupportedOperationException(); }
        @Override public void destroy() { throw new UnsupportedOperationException(); }
    }
    private static final class Fixture {
        final Context context;
        final Device device;
        final SessionJournal journal;
        final Map<String, byte[]> original;
        final JSONObject hashes = new JSONObject();
        Fixture() throws Exception {
            Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
            // Canonical, like the coordinator's own root: journals built here must pass RunStore.safe.
            File root = new File(actual.getFilesDir().getCanonicalFile(), "coordinator-probes/" + UUID.randomUUID());
            assertTrue(root.mkdirs());
            context = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
            PrivateProbeFixtures fixture = PrivateProbeFixtures.load(actual);
            String id = fixture.normal.getSha256();
            File actualNormal = fixture.normalFile, actualAccess = fixture.accessFile;
            ApkIdentity normal = fixture.normal, access = fixture.access;
            File cached = new RecoveryStore(context).normal(id);
            assertTrue(cached.getParentFile().mkdirs());
            Files.createSymbolicLink(cached.toPath(), actualNormal.toPath());
            put(new File(cached.getParentFile(), "identity.json"), bytes(normal.json().toString()));
            device = new Device(normal, access);
            journal = SessionJournal.Companion.create(new File(root, "sessions"), id, id);
            Files.createSymbolicLink(new File(journal.getDirectory(), "access.apk").toPath(), actualAccess.toPath());
            journal.intent("install_access", new JSONObject()); journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
            journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
            journal.intent("install_normal", new JSONObject());
            journal.outcome(PatchPhase.NORMAL_RESTORED_FOR_BUILD, new JSONObject().put("normal_verified", true));
            journal.outcome(PatchPhase.BUILDING, new JSONObject());
            journal.outcome(PatchPhase.STAGED, new JSONObject().put("counts", new JSONObject()
                .put("text_tables", 391).put("applied_textures", 395).put("skipped_tables", 1).put("skipped_textures", 0)));
            journal.intent("install_access", new JSONObject()); journal.outcome(PatchPhase.APPLY_ACCESS_INSTALLED, new JSONObject());
            journal.outcome(PatchPhase.APPLYING, new JSONObject());
            device.files.put("packages/1/1.info", bytes("{\"version\":\"1.4.0.2\"}"));
            device.files.put("packages/1/1.db", bytes("original-index"));
            device.files.put("packages/1/1_0.db", bytes("original-shard"));
            device.files.put("Watchdog/dst/PatchList.db", bytes("original-watchdog"));
            original = new HashMap<>(device.files);
            JSONObject manifest = new JSONObject();
            for (Map.Entry<String, byte[]> entry : original.entrySet()) {
                put(new File(journal.getDirectory(), "snapshot/" + entry.getKey()), entry.getValue());
                manifest.put(entry.getKey(), new JSONObject().put("bytes", entry.getValue().length).put("sha256", hash(entry.getValue())));
            }
            put(new File(journal.getDirectory(), "snapshot/manifest.json"), bytes(new JSONObject().put("schema", 1)
                .put("files", manifest).put("directories", new JSONArray()).toString()));
            for (String name : new String[]{"1/1.db", "1/1_0.db"}) {
                byte[] value = bytes("translated-" + name);
                put(new File(journal.getDirectory(), "out/" + name), value); hashes.put(name, hash(value));
            }
            put(new File(journal.getDirectory(), "staged-hashes.json"), bytes(hashes.toString()));
        }
        /** Re-home the fixture files and APKs under <linked>, through a sealed owned build attempt. */
        Fixture(Fixture legacy, SessionJournal linked, boolean restoreNormal) throws Exception {
            context = legacy.context; device = legacy.device; journal = linked;
            device.files.clear(); device.files.putAll(legacy.original); device.installed = device.normal;
            original = new HashMap<>(legacy.original);
            String attempt = UUID.randomUUID().toString();
            JSONObject manifest = new JSONObject();
            for (Map.Entry<String, byte[]> entry : original.entrySet()) {
                put(new File(journal.getDirectory(), "snapshot/" + entry.getKey()), entry.getValue());
                manifest.put(entry.getKey(), new JSONObject().put("bytes", entry.getValue().length).put("sha256", hash(entry.getValue())));
            }
            put(new File(journal.getDirectory(), "snapshot/manifest.json"), bytes(new JSONObject().put("schema", 1)
                .put("files", manifest).put("directories", new JSONArray()).toString()));
            journal.intent("install_access", new JSONObject()); device.installed = device.access;
            journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
            journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
            journal.outcome(PatchPhase.BUILDING, new JSONObject());
            // As the engine does: the attempt's result folder exists before the journal pins it.
            assertTrue(new File(journal.getDirectory(), "build-attempts/" + attempt + "/result").mkdirs());
            journal.record(new JSONObject().put("build_attempt", attempt).put("remove", false));
            File result = journal.getResultRoot();
            JSONArray staged = new JSONArray();
            for (String name : new String[]{"1/1.db", "1/1_0.db"}) {
                byte[] value = bytes("translated-" + name);
                put(new File(result, "out/" + name), value); hashes.put(name, hash(value)); staged.put(hash(value));
            }
            put(new File(result, "staged-hashes.json"), bytes(hashes.toString()));
            put(new File(result, PristineDelta.SESSION_DELTA), bytes("sealed-delta"));
            PristineDelta.INSTANCE.seal(context, journal, new JSONObject().put("schema", 1).put("remove", false).put("files", 2)
                .put("bytes", 12).put("delta_sha256", hash(bytes("sealed-delta"))).put("staged_hashes", staged));
            journal.outcome(PatchPhase.STAGED, new JSONObject().put("counts", new JSONObject()
                .put("text_tables", 391).put("applied_textures", 395).put("skipped_tables", 1).put("skipped_textures", 0)));
            journal.outcome(PatchPhase.APPLYING, new JSONObject());
            GameFileTransaction transaction = new GameFileTransaction(journal, device);
            for (String name : new String[]{"1/1.db", "1/1_0.db"}) transaction.write("packages/" + name,
                new File(result, "out/" + name), hashes.getString(name), false);
            transaction.finishApply(hashes);
            if (restoreNormal) {
                journal.intent("install_normal", new JSONObject()); device.installed = device.normal;
                journal.outcome(PatchPhase.RESTORING, new JSONObject().put("normal_verified", true)
                    .put("final_normal_verified", true));
            }
            // Killed before the pristine delta was finalized.
            journal.recoveryRequired("Fake kill before finalization");
        }
        PatchCoordinator coordinator() {
            return new PatchCoordinator(context, device, message -> kotlin.Unit.INSTANCE,
                expected -> { if (!expected.equals(device.installed)) throw new IllegalStateException("Fake installed identity differs"); });
        }
    }
    @Test public void testCoordinatorRetriesInterruptedWholeSetRollback() throws Exception {
        boolean pythonStarted = Python.isStarted();
        Fixture fixture = new Fixture();
        fixture.device.failWriteAt = 1;
        try {
            new GameFileTransaction(fixture.journal, fixture.device).write("packages/1/1.db",
                new File(fixture.journal.getDirectory(), "out/1/1.db"), fixture.hashes.getString("1/1.db"), false);
            fail("Initial interruption missing");
        } catch (IllegalStateException expected) { }
        fixture.journal.recoveryRequired("Fake post-index process loss");
        fixture.device.failWriteAt = fixture.device.writes + 2;
        PatchCoordinator failed = fixture.coordinator();
        try { failed.recover(fixture.journal.getId()); fail("Rollback interruption missing"); }
        catch (IllegalStateException expected) { }
        SessionJournal pending = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertEquals(PatchPhase.RECOVERY_REQUIRED, pending.getPhase()); assertTrue(pending.getDirtyPackages());
        assertTrue(pending.getHasMutationIntent());
        assertEquals(fixture.device.normal, fixture.device.installed);
        assertTrue(pending.snapshot().getBoolean("normal_verified"));
        assertFalse(pending.getHasRecoveryNormalIntent());
        JSONObject state = failed.pendingRecoveryResult();
        assertEquals("recovery_required", state.getString("status"));
        assertTrue(state.getBoolean("normal_verified")); assertTrue(state.getBoolean("packages_dirty"));
        assertFalse(state.getBoolean("launch_allowed"));
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        assertEquals("recovered", result.getString("status")); assertFalse(result.has("counts"));
        assertEquals(fixture.device.normal, fixture.device.installed);
        assertEquals(fixture.original.keySet(), fixture.device.files.keySet());
        for (String name : fixture.original.keySet()) assertArrayEquals(fixture.original.get(name), fixture.device.files.get(name));
        assertEquals(pythonStarted, Python.isStarted());
    }
    @Test public void testCorruptOriginalsRefuseRollbackButRestoreNormal() throws Exception {
        Fixture fixture = new Fixture();
        fixture.device.failWriteAt = 1;
        try {
            new GameFileTransaction(fixture.journal, fixture.device).write("packages/1/1.db",
                new File(fixture.journal.getDirectory(), "out/1/1.db"), fixture.hashes.getString("1/1.db"), false);
            fail("Initial interruption missing");
        } catch (IllegalStateException expected) { }
        fixture.journal.recoveryRequired("Fake post-index failure");
        put(new File(fixture.journal.getDirectory(), "snapshot/packages/1/1.db"), bytes("corrupt-original"));
        int writes = fixture.device.writes;
        try { fixture.coordinator().recover(fixture.journal.getId()); fail("Corrupt backup accepted"); }
        catch (IllegalStateException expected) { }
        assertEquals(writes, fixture.device.writes);
        assertEquals(fixture.device.normal, fixture.device.installed);
        SessionJournal pending = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertEquals(PatchPhase.RECOVERY_REQUIRED, pending.getPhase());
        assertTrue(pending.getDirtyPackages()); assertTrue(pending.getHasMutationIntent());
        assertTrue(pending.snapshot().getBoolean("normal_verified"));
        try { pending.terminalResult(); fail("Mixed packages reported completion"); }
        catch (IllegalStateException expected) { }
    }
    @Test public void testCoordinatorAuditsLayerAfterCommittedFinalNormal() throws Exception {
        boolean pythonStarted = Python.isStarted();
        Fixture fixture = new Fixture();
        GameFileTransaction transaction = new GameFileTransaction(fixture.journal, fixture.device);
        for (String name : new String[]{"1/1.db", "1/1_0.db"}) transaction.write("packages/" + name,
            new File(fixture.journal.getDirectory(), "out/" + name), fixture.hashes.getString(name), false);
        transaction.finishApply(fixture.hashes);
        fixture.device.failNormalOnce = true;
        try { fixture.coordinator().recover(fixture.journal.getId()); fail("Final installer fault missing"); }
        catch (IllegalStateException expected) { }
        assertEquals(fixture.device.normal, fixture.device.installed);
        int installs = fixture.device.installs;
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        assertEquals("complete", result.getString("status")); assertEquals(395, result.getJSONObject("counts").getInt("applied_textures"));
        assertEquals(installs + 2, fixture.device.installs);
        for (java.util.Iterator<String> names = fixture.hashes.keys(); names.hasNext();) {
            String name = names.next();
            assertEquals(fixture.hashes.getString(name), hash(fixture.device.files.get("packages/" + name)));
        }
        assertEquals(pythonStarted, Python.isStarted());
    }

    /** A verified payload the game changed afterwards closes unconfirmed: nothing is rolled back. */
    @Test public void testForwardRecoveryClosesChangedLiveLayerUnconfirmed() throws Exception {
        Fixture fixture = changedAfterVerifiedPayload();
        int writes = fixture.device.writes;
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        assertEquals("recovered_unconfirmed", result.getString("status"));
        assertEquals(writes, fixture.device.writes);
        assertArrayEquals(bytes("external-update"), fixture.device.files.get("packages/1/1.db"));
        assertEquals(fixture.device.normal, fixture.device.installed);
        SessionJournal closed = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertEquals(PatchPhase.CANCELLED, closed.getPhase());
        assertTrue(closed.getLayerUnconfirmed());
    }

    /** An audit that fails for any other reason still leaves the run for recovery. */
    @Test public void testForwardRecoveryRefusesUnexplainedAuditFailure() throws Exception {
        Fixture fixture = changedAfterVerifiedPayload();
        fixture.device.changedLayerMessage = "Fake live layer changed: ";
        int writes = fixture.device.writes;
        PatchCoordinator coordinator = fixture.coordinator();
        try { coordinator.recover(fixture.journal.getId()); fail("Changed layer reported completion"); }
        catch (IllegalStateException expected) { }
        assertEquals(writes, fixture.device.writes);
        assertArrayEquals(bytes("external-update"), fixture.device.files.get("packages/1/1.db"));
        assertEquals(fixture.device.normal, fixture.device.installed);
        assertEquals("recovery_required", coordinator.pendingRecoveryResult().getString("status"));
        assertFalse(coordinator.pendingRecoveryResult().getBoolean("launch_allowed"));
        assertEquals(PatchPhase.RECOVERY_REQUIRED, SessionJournal.Companion.load(fixture.journal.getDirectory()).getPhase());
    }

    /** Free up space closes a clean unfinished run without an install and releases its bulk. */
    @Test public void testFreeSpaceClosesCleanRunWithoutInstall() throws Exception {
        Fixture fixture = changedAfterVerifiedPayload();
        int writes = fixture.device.writes, installs = fixture.device.installs;
        JSONObject result = fixture.coordinator().freeSpace();
        assertEquals("space_freed", result.getString("status"));
        assertEquals(1, result.getInt("closed_runs"));
        assertEquals(writes, fixture.device.writes);
        assertEquals(installs, fixture.device.installs);
        SessionJournal closed = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertEquals(PatchPhase.CANCELLED, closed.getPhase());
        assertTrue(closed.getLayerUnconfirmed());
        assertFalse(new File(fixture.journal.getDirectory(), "out/1/1.db").exists());
    }

    /** The opt-in removes the saved normal APK only once the installed game is verified as it. */
    @Test public void testFreeSpaceRemovesSavedApksOnlyOverInstalledNormal() throws Exception {
        Fixture fixture = changedAfterVerifiedPayload();
        File saved = new File(fixture.context.getFilesDir(), "recovery/" + fixture.journal.getRecoveryId());
        fixture.coordinator().freeSpace(false);
        assertTrue(saved.isDirectory());
        fixture.device.installed = fixture.device.access;
        JSONObject kept = fixture.coordinator().freeSpace(true);
        assertFalse(kept.getBoolean("removed_saved_apks"));
        assertTrue(saved.isDirectory());
        fixture.device.installed = fixture.device.normal;
        JSONObject removed = fixture.coordinator().freeSpace(true);
        assertTrue(removed.getBoolean("removed_saved_apks"));
        assertFalse(saved.exists());
    }

    /** Free up space refuses a run that stopped mid-change: its originals are the rollback. */
    @Test public void testFreeSpaceRefusesDirtyRun() throws Exception {
        Fixture fixture = new Fixture();
        fixture.device.failWriteAt = 1;
        try {
            new GameFileTransaction(fixture.journal, fixture.device).write("packages/1/1.db",
                new File(fixture.journal.getDirectory(), "out/1/1.db"), fixture.hashes.getString("1/1.db"), false);
            fail("Initial interruption missing");
        } catch (IllegalStateException expected) { }
        fixture.journal.recoveryRequired("Fake post-index failure");
        try { fixture.coordinator().freeSpace(); fail("Dirty run closed"); }
        catch (IllegalStateException expected) { }
        SessionJournal pending = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertEquals(PatchPhase.RECOVERY_REQUIRED, pending.getPhase());
        assertTrue(pending.getDirtyPackages());
        assertTrue(new File(fixture.journal.getDirectory(), "snapshot/packages/1/1.db").isFile());
    }

    private static Fixture changedAfterVerifiedPayload() throws Exception {
        Fixture fixture = new Fixture();
        GameFileTransaction transaction = new GameFileTransaction(fixture.journal, fixture.device);
        for (String name : new String[]{"1/1.db", "1/1_0.db"}) transaction.write("packages/" + name,
            new File(fixture.journal.getDirectory(), "out/" + name), fixture.hashes.getString(name), false);
        transaction.finishApply(fixture.hashes);
        fixture.journal.recoveryRequired("Fake restart after verified payload");
        fixture.device.installed = fixture.device.normal;
        fixture.device.files.put("packages/1/1.db", bytes("external-update"));
        return fixture;
    }
    // ---- Linked (schema 2) continuation sessions: ticket 10. Authored in pass 1; run in pass 2. ----

    /** Make the saved Start look claimed, as its dispatch left it; the digest is recomputed like the store's own. */
    private static RunStore.Run claimed(Context context, RunStore.Run run) throws Exception {
        File path = new File(context.getFilesDir(), "runs/" + run.getId() + ".json");
        JSONObject value = ArtifactReceipts.INSTANCE.parse(Files.readAllBytes(path.toPath()));
        value.put("lifecycle", "claimed"); value.remove("record_sha256");
        value.put("record_sha256", ArtifactReceipts.INSTANCE.identityKey(value));
        put(path, bytes(ArtifactReceipts.INSTANCE.canonical(value)));
        return new RunStore(context).load(run.getId());
    }

    /** A linked session whose build attempt is sealed and whose payload is written and verified. */
    private static Fixture linkedVerified(boolean restoreNormal) throws Exception {
        Fixture legacy = new Fixture();
        // The legacy journal is only scaffolding for the fixture APKs and files; the linked one replaces it.
        File access = new File(legacy.journal.getDirectory(), "access.apk").toPath().toRealPath().toFile();
        DurableFiles.INSTANCE.deleteTree(legacy.journal.getDirectory());
        RunStore.Run run = claimed(legacy.context, new RunStore(legacy.context).start("translate", "en",
            ShellProvider.SHIZUKU, RunStore.Target.Companion.local(legacy.context)));
        String id = legacy.journal.getRecoveryId();
        SessionJournal journal = SessionJournal.Companion.create(new File(legacy.context.getFilesDir(), "sessions"),
            id, id, null, run.getId(), run.getAuthorizationKey());
        Files.createSymbolicLink(new File(journal.getDirectory(), "access.apk").toPath(), access.toPath());
        return new Fixture(legacy, journal, restoreNormal);
    }

    @Test public void testEngineUnavailableRecoveryFinalizesWithoutRebuildOrWrite() throws Exception {
        boolean pythonStarted = Python.isStarted();
        Fixture fixture = linkedVerified(true);
        int writes = fixture.device.writes;
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        assertEquals("complete", result.getString("status"));
        assertEquals(writes, fixture.device.writes);
        assertEquals(fixture.device.normal, fixture.device.installed);
        assertEquals(pythonStarted, Python.isStarted());
        File kept = new File(PristineDelta.INSTANCE.directory(fixture.context), "delta.bin");
        assertArrayEquals(bytes("sealed-delta"), Files.readAllBytes(kept.toPath()));
        JSONObject record = new JSONObject(new String(Files.readAllBytes(
            new File(PristineDelta.INSTANCE.directory(fixture.context), "staged-hashes.json").toPath()), StandardCharsets.UTF_8));
        assertEquals(fixture.hashes.length(), record.getJSONArray("sha256").length());
        SessionJournal done = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertTrue(done.snapshot().getBoolean("finalized"));
        assertFalse(done.snapshot().getBoolean("finalization_pending"));
        assertEquals("complete", new RunStore(fixture.context).load(done.getRunId()).getLifecycle());
        // Promotion is idempotent: a repeat after the terminal record changes nothing.
        byte[] before = Files.readAllBytes(kept.toPath());
        PristineDelta.INSTANCE.finalize(fixture.context, done);
        assertArrayEquals(before, Files.readAllBytes(kept.toPath()));
    }

    @Test public void testChangedSealedMaterialRefusesFinalization() throws Exception {
        Fixture fixture = linkedVerified(true);
        put(new File(fixture.journal.getResultRoot(), PristineDelta.SESSION_DELTA), bytes("tampered"));
        try { fixture.coordinator().recover(fixture.journal.getId()); fail("Changed sealed delta finalized"); }
        catch (IllegalStateException expected) { }
        assertFalse(new File(PristineDelta.INSTANCE.directory(fixture.context), "delta.bin").exists());
        SessionJournal pending = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertNotEquals(PatchPhase.COMPLETE, pending.getPhase());
        assertTrue(new RunStore(fixture.context).load(pending.getRunId()).getMayContinue());
    }

    @Test public void testLinkedCorruptOriginalsKeepTheActionAndItsArtifacts() throws Exception {
        Fixture fixture = linkedVerified(false);
        // A later write of the same run is cut after its file landed; the payload is no longer verified.
        fixture.journal.outcome(PatchPhase.RESTORING, new JSONObject());
        fixture.device.failWriteAt = fixture.device.writes + 1;
        try {
            new GameFileTransaction(fixture.journal, fixture.device).write("packages/1/1.db",
                new File(fixture.journal.getResultRoot(), "out/1/1.db"), fixture.hashes.getString("1/1.db"), false);
            fail("Interruption missing");
        } catch (IllegalStateException expected) { }
        fixture.journal.recoveryRequired("Fake kill mid-apply");
        put(new File(fixture.journal.getDirectory(), "snapshot/packages/1/1.db"), bytes("corrupt-original"));
        int writes = fixture.device.writes;
        try { fixture.coordinator().recover(fixture.journal.getId()); fail("Corrupt originals accepted"); }
        catch (IllegalStateException expected) { }
        assertEquals(writes, fixture.device.writes);
        SessionJournal pending = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertTrue(pending.getDirtyPackages());
        assertTrue(new RunStore(fixture.context).load(pending.getRunId()).getMayContinue());
        assertTrue(new File(fixture.journal.getResultRoot(), "out/1/1.db").isFile());
        assertTrue(new File(fixture.journal.getDirectory(), "snapshot/manifest.json").isFile());
        try { fixture.coordinator().freeSpace(); fail("Free up space ran over an unresolved action"); }
        catch (IllegalStateException expected) { }
        assertTrue(new File(fixture.journal.getResultRoot(), "out/1/1.db").isFile());
    }

    /**
     * Ticket 12: a Re-download deletion cut after its first file rolls every deleted file and Watchdog back from
     * the verified snapshot, through the pinned plan's own staged list. The plan stays pinned and the action keeps
     * waiting under its automatic approval, so a later dispatch resumes the same plan without any dialog.
     */
    @Test public void testInterruptedRedownloadDeletionRollsBackThroughThePinnedPlan() throws Exception {
        Fixture legacy = new Fixture();
        File access = new File(legacy.journal.getDirectory(), "access.apk").toPath().toRealPath().toFile();
        DurableFiles.INSTANCE.deleteTree(legacy.journal.getDirectory());
        Context context = legacy.context;
        RunStore.Run run = claimed(context, new RunStore(context).start("translate", "en",
            ShellProvider.SHIZUKU, RunStore.Target.Companion.local(context)));
        String id = legacy.journal.getRecoveryId();
        SessionJournal journal = SessionJournal.Companion.create(new File(context.getFilesDir(), "sessions"),
            id, id, null, run.getId(), run.getAuthorizationKey());
        Files.createSymbolicLink(new File(journal.getDirectory(), "access.apk").toPath(), access.toPath());
        Device device = legacy.device;
        device.files.clear(); device.files.putAll(legacy.original);
        JSONObject manifest = new JSONObject();
        for (Map.Entry<String, byte[]> entry : legacy.original.entrySet()) {
            put(new File(journal.getDirectory(), "snapshot/" + entry.getKey()), entry.getValue());
            manifest.put(entry.getKey(), new JSONObject().put("bytes", entry.getValue().length).put("sha256", hash(entry.getValue())));
        }
        put(new File(journal.getDirectory(), "snapshot/manifest.json"), bytes(new JSONObject().put("schema", 1)
            .put("files", manifest).put("directories", new JSONArray()).toString()));
        journal.intent("install_access", new JSONObject()); device.installed = device.access;
        journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
        journal.outcome(PatchPhase.BUILDING, new JSONObject());
        // The plan's staged list holds every file of package 1 at its snapshot hash: what the deletion removes.
        String plan = UUID.randomUUID().toString();
        JSONObject staged = new JSONObject();
        for (String name : new String[]{"1/1.info", "1/1.db", "1/1_0.db"})
            staged.put(name, hash(legacy.original.get("packages/" + name)));
        File planRoot = new File(journal.getDirectory(), "redownload-plans/" + plan);
        put(new File(planRoot, "staged-hashes.json"), bytes(staged.toString()));
        String digest = hash(bytes("plan"));
        journal.record(new JSONObject().put("redownload_plan", plan).put("redownload_plan_sha256", digest)
            .put("build_attempt", "").put("waiting_reason", PatchCoordinator.REDOWNLOAD_CONSENT));
        assertEquals(planRoot.getCanonicalPath(), journal.getResultRoot().getCanonicalPath());
        // Approved automatically with the proposal (user decision 2026-11-13): no review, no dialog.
        RunStore.Companion.coordinator(context, () -> new RunStore(context).proposeRedownload(run.getId(), plan, digest, 3,
            java.util.Collections.singletonList("1"), 64, true));
        assertEquals(RedownloadConsent.APPROVAL_AUTOMATIC, new RunStore(context).load(run.getId()).getRedownload().getApprovalSource());
        RunStore.Companion.coordinator(context, () -> new RunStore(context).redownloadProgress(run.getId(), digest,
            RedownloadConsent.DELETING));
        journal.outcome(PatchPhase.STAGED, new JSONObject());
        journal.outcome(PatchPhase.APPLYING, new JSONObject());
        new GameFileTransaction(journal, device).delete("packages/1/1.db", staged.getString("1/1.db"));
        assertFalse(device.files.containsKey("packages/1/1.db"));
        journal.recoveryRequired("Fake kill mid-deletion");
        JSONObject result = new PatchCoordinator(context, device, message -> kotlin.Unit.INSTANCE,
            expected -> { if (!expected.equals(device.installed)) throw new IllegalStateException("Fake installed identity differs"); })
            .recover(journal.getId());
        assertEquals("recovered", result.getString("status"));
        assertEquals(device.normal, device.installed);
        assertEquals(legacy.original.keySet(), device.files.keySet());
        for (String name : legacy.original.keySet()) assertArrayEquals(legacy.original.get(name), device.files.get(name));
        SessionJournal recovered = SessionJournal.Companion.load(journal.getDirectory());
        assertEquals(PatchPhase.CANCELLED, recovered.getPhase()); assertFalse(recovered.getDirtyPackages());
        assertEquals(PatchCoordinator.REDOWNLOAD_CONSENT, recovered.getWaitingReason());
        assertEquals(plan, recovered.snapshot().getString("redownload_plan"));
        RunStore.Run saved = new RunStore(context).load(run.getId());
        assertTrue(saved.getMayContinue());
        assertTrue("The approval survives for the same plan", saved.getRedownload().getApproved());
        assertEquals(RedownloadConsent.APPROVAL_AUTOMATIC, saved.getRedownload().getApprovalSource());
        assertTrue("A rolled-back deletion re-downloaded nothing", saved.getRedownloadedPackages().isEmpty());
    }

    @Test public void testFreeSpaceReleasesEveryResolvedSessionsBulk() throws Exception {
        Fixture first = linkedVerified(true);
        first.coordinator().recover(first.journal.getId());
        File receipt = new File(first.journal.getResultRoot(), ArtifactReceipts.NAME);
        put(receipt, bytes("{}"));
        // A second resolved linked action on the same private root, newer than the first.
        RunStore.Run run = claimed(first.context, new RunStore(first.context).start("translate", "en",
            ShellProvider.SHIZUKU, RunStore.Target.Companion.local(first.context)));
        SessionJournal newer = SessionJournal.Companion.create(new File(first.context.getFilesDir(), "sessions"),
            first.journal.getRecoveryId(), first.journal.getRecoveryId(), null, run.getId(), run.getAuthorizationKey());
        put(new File(newer.getDirectory(), "snapshot/packages/1/1.db"), bytes("kept"));
        newer.outcome(PatchPhase.RESTORING, new JSONObject());
        // A cancelled resolved cache is sufficient for retention; saved COMPLETE alone is not
        // authority to finish a claimed run without the current live audit.
        new RunStore(first.context).stop(run.getId());
        newer.outcome(PatchPhase.CANCELLED, new JSONObject().put("normal_verified", true).put("stopped_consistent", true));
        new RunStore(first.context).resolve(run.getId());
        first.coordinator().freeSpace();
        assertFalse("A released receipt must go before its bytes", receipt.exists());
        assertFalse(new File(first.journal.getDirectory(), "build-attempts").exists());
        assertTrue(new File(first.journal.getDirectory(), "snapshot/manifest.json").isFile());
        assertTrue(new File(first.journal.getDirectory(), "journal.json").isFile());
        // Free up space releases every resolved session's bulk, the newest too; only a patch run's own
        // cleanup keeps the newest as the reusable cache (releaseResolvedSessions' policy).
        assertFalse("Free up space releases the newest resolved session's bulk too",
            new File(newer.getDirectory(), "snapshot/packages/1/1.db").exists());
        assertTrue(new File(newer.getDirectory(), "journal.json").isFile());
    }
    @Test public void testSavedFinalNormalProofNeverCompletesChangedLiveLayerAfterRestart() throws Exception {
        Fixture fixture = linkedVerified(true);
        assertTrue(fixture.journal.snapshot().getBoolean("final_normal_verified"));
        fixture.device.files.put("packages/1/1.db", bytes("new game update after normal verification"));
        int writes = fixture.device.writes;
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        assertEquals("recovered_unconfirmed", result.getString("status"));
        assertEquals(writes, fixture.device.writes);
        assertEquals(fixture.device.normal, fixture.device.installed);
        assertNotEquals(PatchPhase.COMPLETE, SessionJournal.Companion.load(fixture.journal.getDirectory()).getPhase());
    }

    @Test public void testStopQueuedAtFinalNormalAuditFinalizesButNeverReportsComplete() throws Exception {
        Fixture fixture = linkedVerified(true);
        String id = fixture.journal.getRunId();
        PatchCoordinator coordinator = new PatchCoordinator(fixture.context, fixture.device, message -> kotlin.Unit.INSTANCE,
            expected -> {
                if (!expected.equals(fixture.device.installed)) throw new IllegalStateException("Fake identity differs");
                if (expected.equals(fixture.device.normal)) new RunStore(fixture.context).stop(id);
            });
        JSONObject result = coordinator.recover(fixture.journal.getId());
        // A Stop that lands after the payload is verified and finalized reports the translation as added
        // (WorkerStatus.afterStop); the journal and the run stay stopped.
        assertEquals("complete", result.getString("status")); assertTrue(result.getBoolean("stopped_after_finish"));
        SessionJournal done = SessionJournal.Companion.load(fixture.journal.getDirectory());
        assertEquals(PatchPhase.CANCELLED, done.getPhase());
        assertTrue(done.snapshot().getBoolean("finalized"));
        assertEquals("stopped", new RunStore(fixture.context).load(id).getLifecycle());
        assertTrue(new File(done.getDirectory(), "snapshot/manifest.json").isFile());
    }

    @Test public void testUnknownInstalledUpdateIsNeverOverwrittenDuringRecovery() throws Exception {
        Fixture fixture = linkedVerified(true);
        fixture.device.installed = ApkIdentity.Companion.fromJson(fixture.device.normal.json()
            .put("sha256", "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"));
        int installs = fixture.device.installs, writes = fixture.device.writes;
        try { fixture.coordinator().recover(fixture.journal.getId()); fail("Unknown APK overwritten"); }
        catch (IllegalStateException expected) { }
        assertEquals(installs, fixture.device.installs); assertEquals(writes, fixture.device.writes);
        assertTrue(new File(fixture.journal.getDirectory(), "snapshot/manifest.json").isFile());
    }

    private static void splitTerminal(Fixture fixture) throws Exception {
        fixture.journal.outcome(PatchPhase.RESTORING, new JSONObject().put("normal_verified", true));
        PristineDelta.INSTANCE.finalize(fixture.context, fixture.journal);
        fixture.journal.outcome(PatchPhase.COMPLETE, new JSONObject().put("normal_verified", true));
        // Exact process cut: child terminal is durable; parent run-store terminal write never happened.
        assertEquals("claimed", new RunStore(fixture.context).load(fixture.journal.getRunId()).getLifecycle());
    }
    @Test public void testCutAfterJournalTerminalThenStopAuditsAndDowngrades() throws Exception {
        Fixture fixture = linkedVerified(true); splitTerminal(fixture);
        new RunStore(fixture.context).stop(fixture.journal.getRunId());
        try { new RunStore(fixture.context).resolve(fixture.journal.getRunId()); fail("Saved terminal bypassed live audit"); }
        catch (IllegalStateException expected) { }
        int installs = fixture.device.installs;
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        // Finalized before the Stop: reported as added (WorkerStatus.afterStop), resolved as stopped.
        assertEquals("complete", result.getString("status")); assertTrue(result.getBoolean("stopped_after_finish"));
        assertEquals(PatchPhase.CANCELLED, SessionJournal.Companion.load(fixture.journal.getDirectory()).getPhase());
        assertEquals("stopped", new RunStore(fixture.context).load(fixture.journal.getRunId()).getLifecycle());
        assertTrue("Required independent access/normal audit cycle missing", fixture.device.installs >= installs + 2);
        assertEquals(fixture.device.normal, fixture.device.installed);
    }
    @Test public void testCutAfterJournalTerminalCannotCompleteChangedActualLayer() throws Exception {
        Fixture fixture = linkedVerified(true); splitTerminal(fixture);
        fixture.device.files.put("packages/1/1.db", bytes("changed after split completion"));
        JSONObject result = fixture.coordinator().recover(fixture.journal.getId());
        assertEquals("recovered_unconfirmed", result.getString("status"));
        assertNotEquals(PatchPhase.COMPLETE, SessionJournal.Companion.load(fixture.journal.getDirectory()).getPhase());
        assertEquals("claimed", new RunStore(fixture.context).load(fixture.journal.getRunId()).getLifecycle());
    }
    @Test public void testStaleResolvedRecoverRefusesWithoutPoisoningHistory() throws Exception {
        for (boolean stopped : new boolean[]{false, true}) {
            Fixture fixture = linkedVerified(true);
            if (stopped) new RunStore(fixture.context).stop(fixture.journal.getRunId());
            fixture.coordinator().recover(fixture.journal.getId());
            byte[] before = Files.readAllBytes(new File(fixture.journal.getDirectory(), "journal.json").toPath());
            int installs = fixture.device.installs;
            try { fixture.coordinator().recover(fixture.journal.getId()); fail("Stale resolved recovery accepted"); }
            catch (IllegalStateException expected) { }
            assertArrayEquals(before, Files.readAllBytes(new File(fixture.journal.getDirectory(), "journal.json").toPath()));
            assertEquals(installs, fixture.device.installs);
        }
    }

}
