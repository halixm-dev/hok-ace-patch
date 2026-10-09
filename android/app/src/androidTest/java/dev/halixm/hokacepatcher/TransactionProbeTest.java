package dev.halixm.hokacepatcher;

import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Deliberate post-commit interruption and repeat rollback using a private fake device, never the game. */
@RunWith(AndroidJUnit4.class)
public final class TransactionProbeTest {
    private static final String ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    private static String hash(byte[] value) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte part : MessageDigest.getInstance("SHA-256").digest(value)) result.append(String.format("%02x", part & 255));
        return result.toString();
    }
    private static void put(File file, byte[] value) throws Exception {
        assertTrue(file.getParentFile().isDirectory() || file.getParentFile().mkdirs());
        try (FileOutputStream output = new FileOutputStream(file)) { output.write(value); output.getFD().sync(); }
    }
    private static byte[] read(java.io.InputStream input) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096]; int count;
        while ((count = input.read(buffer)) >= 0) {
            output.write(buffer, 0, count);
            if (output.size() > 1024 * 1024) throw new IllegalStateException("Oversized private fixture");
        }
        return output.toByteArray();
    }
    private static final class Device extends IPrivilegedDeviceService.Stub {
        final Map<String, byte[]> files = new HashMap<>();
        int writes;
        int failAt;
        @Override public String writeGameFile(String session, String relative, ParcelFileDescriptor source,
                                              long length, String sha256) {
            try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
                ParcelFileDescriptor.dup(source.getFileDescriptor()))) {
                GameFilePolicy.INSTANCE.validate(relative, true);
                byte[] value = read(input);
                assertEquals(length, value.length); assertEquals(sha256, hash(value));
                files.put(relative, value); // Injection occurs after rename, before its acknowledgment.
                if (++writes == failAt) throw new IllegalStateException("Injected post-commit interruption");
                return "verified";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String validateGameSnapshot(ParcelFileDescriptor descriptor) {
            try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
                ParcelFileDescriptor.dup(descriptor.getFileDescriptor()))) {
                JSONObject expected = new JSONObject(new String(read(input), StandardCharsets.UTF_8)).getJSONObject("files");
                assertEquals(expected.length(), files.size());
                for (String name : files.keySet()) assertEquals(expected.getJSONObject(name).getString("sha256"), hash(files.get(name)));
                return "verified";
            } catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public void clearGameWatchdog() { files.keySet().removeIf(name -> name.startsWith("Watchdog/")); }
        @Override public void clearSessionTemp(String session, String relative) { GameFilePolicy.INSTANCE.session(session); }
        @Override public void restoreWatchdogDirectory(String relative) { GameFilePolicy.INSTANCE.watchdogDirectory(relative); }
        @Override public String diagnostics() { throw new UnsupportedOperationException(); }
        @Override public String gameApkInfo() { throw new UnsupportedOperationException(); }
        @Override public String copyGameApk(ParcelFileDescriptor destination) { throw new UnsupportedOperationException(); }
        @Override public byte[] probeFixture(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String estimateGameSnapshot() { throw new UnsupportedOperationException("No snapshot measurement in this fixture"); }
        @Override public void forceStopGame() { throw new UnsupportedOperationException(); }
        @Override public String reinstallFixture(boolean abandon) { throw new UnsupportedOperationException(); }
        @Override public String replaceGameApk(ParcelFileDescriptor source, long length) { throw new UnsupportedOperationException(); }
        @Override public String probeGame(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String snapshotGame(ParcelFileDescriptor destination, long budget) { throw new UnsupportedOperationException(); }
        @Override public void validateFirstSetupSource(String sha) { throw new UnsupportedOperationException(); }
        @Override public void checkGameProfiles() { throw new UnsupportedOperationException(); }
        @Override public boolean firstSetupGameAbsent() { throw new UnsupportedOperationException(); }
        @Override public void removeGameForFirstSetup(String sha) { throw new UnsupportedOperationException(); }
        @Override public String installFirstSetupGame(ParcelFileDescriptor source, long length) { throw new UnsupportedOperationException(); }
        @Override public void destroy() { throw new UnsupportedOperationException(); }
    }
    private static SessionJournal applying(File parent) throws Exception {
        SessionJournal journal = SessionJournal.Companion.create(parent, ID, ID);
        journal.intent("install_access", new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
        journal.intent("install_normal", new JSONObject());
        journal.outcome(PatchPhase.NORMAL_RESTORED_FOR_BUILD, new JSONObject().put("normal_verified", true));
        journal.outcome(PatchPhase.BUILDING, new JSONObject());
        journal.outcome(PatchPhase.STAGED, new JSONObject());
        journal.intent("install_access", new JSONObject());
        journal.outcome(PatchPhase.APPLY_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.APPLYING, new JSONObject());
        return journal;
    }

    @Test public void testMixedIndexShardAndInterruptedRollbackRecoverWholeSet() throws Exception {
        File parent = new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir(),
            "transaction-probes/" + UUID.randomUUID());
        SessionJournal journal = applying(parent);
        Device device = new Device();
        device.files.put("packages/1/1.info", bytes("{\"version\":\"1.4.0.2\"}"));
        device.files.put("packages/1/1.db", bytes("original-index"));
        device.files.put("packages/1/1_0.db", bytes("original-shard"));
        device.files.put("Watchdog/dst/PatchList.db", bytes("original-watchdog"));
        Map<String, byte[]> original = new HashMap<>(device.files);
        JSONObject files = new JSONObject();
        for (Map.Entry<String, byte[]> entry : original.entrySet()) {
            put(new File(journal.getDirectory(), "snapshot/" + entry.getKey()), entry.getValue());
            files.put(entry.getKey(), new JSONObject().put("bytes", entry.getValue().length).put("sha256", hash(entry.getValue())));
        }
        put(new File(journal.getDirectory(), "snapshot/manifest.json"), bytes(new JSONObject().put("schema", 1)
            .put("files", files).put("directories", new JSONArray()).toString()));
        JSONObject hashes = new JSONObject();
        for (String name : new String[]{"1/1.db", "1/1_0.db"}) {
            byte[] value = bytes("translated-" + name);
            put(new File(journal.getDirectory(), "out/" + name), value); hashes.put(name, hash(value));
        }
        put(new File(journal.getDirectory(), "staged-hashes.json"), bytes(hashes.toString()));
        GameFileTransaction transaction = new GameFileTransaction(journal, device);
        transaction.verifyOriginals();
        device.failAt = 1;
        try {
            transaction.write("packages/1/1.db", new File(journal.getDirectory(), "out/1/1.db"), hashes.getString("1/1.db"), false);
            fail("Post-commit interruption not injected");
        } catch (IllegalStateException expected) { }
        assertFalse(java.util.Arrays.equals(original.get("packages/1/1.db"), device.files.get("packages/1/1.db")));
        assertArrayEquals(original.get("packages/1/1_0.db"), device.files.get("packages/1/1_0.db"));
        journal = SessionJournal.Companion.load(journal.getDirectory());
        assertTrue(journal.getDirtyPackages()); assertTrue(journal.getHasMutationIntent());
        journal.recoveryRequired("post-commit fault"); journal.outcome(PatchPhase.RESTORING, new JSONObject());
        transaction = new GameFileTransaction(journal, device);
        device.failAt = device.writes + 2;
        try { transaction.rollback(); fail("Interrupted rollback not injected"); }
        catch (IllegalStateException expected) { }
        journal = SessionJournal.Companion.load(journal.getDirectory());
        assertTrue(journal.getDirtyPackages()); assertTrue(journal.getHasMutationIntent());
        journal.recoveryRequired("rollback fault"); journal.outcome(PatchPhase.RESTORING, new JSONObject());
        new GameFileTransaction(journal, device).rollback();
        assertFalse(journal.getDirtyPackages()); assertFalse(journal.getHasMutationIntent());
        assertEquals(original.keySet(), device.files.keySet());
        for (String name : original.keySet()) assertArrayEquals(original.get(name), device.files.get(name));
        assertTrue(new File(journal.getDirectory(), "snapshot/Watchdog/dst/PatchList.db").isFile());
        // Consistent files alone still do not satisfy completion without normal APK verification.
        try { journal.outcome(PatchPhase.COMPLETE, new JSONObject()); fail("Unverified normal APK accepted"); }
        catch (IllegalStateException expected) { }
        // An already-English run may stage no DB files but still clear Watchdog. Recovery
        // must restore it even when the stage manifest is empty.
        SessionJournal empty = applying(parent);
        for (Map.Entry<String, byte[]> entry : original.entrySet())
            put(new File(empty.getDirectory(), "snapshot/" + entry.getKey()), entry.getValue());
        put(new File(empty.getDirectory(), "snapshot/manifest.json"), bytes(new JSONObject().put("schema", 1)
            .put("files", files).put("directories", new JSONArray()).toString()));
        put(new File(empty.getDirectory(), "staged-hashes.json"), bytes("{}"));
        empty.intent("clear_watchdog", new JSONObject());
        device.clearGameWatchdog();
        empty.recoveryRequired("Interrupted Watchdog-only run");
        empty.outcome(PatchPhase.RESTORING, new JSONObject());
        new GameFileTransaction(empty, device).rollback();
        assertFalse(empty.getDirtyPackages());
        for (String name : original.keySet()) assertArrayEquals(original.get(name), device.files.get(name));
        assertEquals(PatchPhase.CANCELLED, empty.getRecoveryCompletionPhase());
        // Once the entire translated layer has been independently verified, a failed final
        // APK reinstall is forward recovery. It must not mislabel retained English data cancelled.
        new GameFileTransaction(empty, device).finishApply(new JSONObject());
        assertEquals(PatchPhase.COMPLETE, empty.getRecoveryCompletionPhase());
        empty.intent("install_normal", new JSONObject());
        empty.recoveryRequired("Interrupted final normal APK install");
        empty = SessionJournal.Companion.load(empty.getDirectory());
        assertEquals(PatchPhase.COMPLETE, empty.getRecoveryCompletionPhase());
        try { empty.outcome(PatchPhase.COMPLETE, new JSONObject()); fail("Unverified normal APK accepted after payload verification"); }
        catch (IllegalStateException expected) { }
        empty.outcome(PatchPhase.RESTORING, new JSONObject());
        empty.outcome(PatchPhase.COMPLETE, new JSONObject().put("normal_verified", true));
    }
}
