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
        @Override public String validateGameSnapshot(ParcelFileDescriptor descriptor) {
            try {
                JSONObject expected = new JSONObject(new String(small(descriptor), StandardCharsets.UTF_8)).getJSONObject("files");
                assertEquals(expected.length(), files.size());
                for (String name : files.keySet()) if (!expected.getJSONObject(name).getString("sha256").equals(hash(files.get(name))))
                    throw new IllegalStateException("Fake live layer changed: " + name);
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
            File root = new File(actual.getFilesDir(), "coordinator-probes/" + UUID.randomUUID());
            assertTrue(root.mkdirs());
            context = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
            String id = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
            File actualNormal = new File(actual.getFilesDir(), "recovery/" + id + "/normal.apk");
            File actualAccess = new File(actual.getFilesDir(), "scratch/game-access-1402/access.apk");
            ApkIdentity normal = ApkIdentity.Companion.read(actual, actualNormal);
            normal.requireRecovery();
            ApkIdentity access = ApkIdentity.Companion.read(actual, actualAccess);
            assertTrue(access.getDebuggable()); assertEquals(normal.getCertificateSha256(), access.getCertificateSha256());
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

    @Test public void testForwardRecoveryRefusesChangedLiveLayer() throws Exception {
        Fixture fixture = new Fixture();
        GameFileTransaction transaction = new GameFileTransaction(fixture.journal, fixture.device);
        for (String name : new String[]{"1/1.db", "1/1_0.db"}) transaction.write("packages/" + name,
            new File(fixture.journal.getDirectory(), "out/" + name), fixture.hashes.getString(name), false);
        transaction.finishApply(fixture.hashes);
        fixture.journal.recoveryRequired("Fake restart after verified payload");
        fixture.device.installed = fixture.device.normal;
        fixture.device.files.put("packages/1/1.db", bytes("external-update"));
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
}
