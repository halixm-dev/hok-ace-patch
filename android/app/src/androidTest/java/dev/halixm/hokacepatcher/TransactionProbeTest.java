package dev.halixm.hokacepatcher;

import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.io.ByteArrayOutputStream;
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
        final java.util.List<String> written = new java.util.ArrayList<>();
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
                written.add(relative);
                if (++writes == failAt) throw new IllegalStateException("Injected post-commit interruption");
                return "verified";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String reconcileGameFiles(String session, String operation, String relative,
                ParcelFileDescriptor policy, ParcelFileDescriptor source, long length, String sha256) {
            return PrivateRecoveryPolicy.apply(this, files, session, operation, relative, policy, source, length, sha256);
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
        @Override public String releaseReplacedGameApks() { return "{\"released\":false,\"freed_bytes\":0}"; }
        @Override public void deleteGameFile(String session, String relative, String sha) { files.remove(relative); }
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
    /** Small independent control; no engine, APK fixture, Python or real provider required. */
    private static final class Control {
        final SessionJournal journal;
        final Device device = new Device();
        final JSONObject hashes = new JSONObject();
        final GameFileTransaction transaction;
        Control(boolean changed) throws Exception {
            File root = new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir(),
                "transaction-controls/" + UUID.randomUUID());
            journal = applying(root);
            device.files.put("packages/1/1.info", bytes("metadata"));
            device.files.put("packages/1/1.db", bytes("original-index"));
            device.files.put("packages/1/1_0.db", bytes("original-shard"));
            device.files.put("Watchdog/list.db", bytes("watchdog"));
            JSONObject originals = new JSONObject();
            for (String name : device.files.keySet()) {
                byte[] data = device.files.get(name);
                put(new File(journal.getDirectory(), "snapshot/" + name), data);
                originals.put(name, new JSONObject().put("sha256", hash(data)).put("bytes", data.length));
            }
            put(new File(journal.getDirectory(), "snapshot/manifest.json"), bytes(new JSONObject().put("schema", 1)
                .put("files", originals).put("directories", new JSONArray()).toString()));
            for (String name : new String[]{"1/1.db", "1/1_0.db"}) {
                byte[] data = changed && name.equals("1/1.db") ? bytes("translated-index") : device.files.get("packages/" + name);
                put(new File(journal.getDirectory(), "out/" + name), data); hashes.put(name, hash(data));
            }
            put(new File(journal.getDirectory(), "staged-hashes.json"), bytes(hashes.toString()));
            transaction = new GameFileTransaction(journal, device);
        }
        void applyOne() {
            transaction.write("packages/1/1.db", new File(journal.getDirectory(), "out/1/1.db"),
                hashes.optString("1/1.db"), false);
        }
        void restoring() { journal.recoveryRequired("private cut"); journal.outcome(PatchPhase.RESTORING, new JSONObject()); }
    }

    @Test public void testIdenticalAndChangedSubsetsKeepCompleteAppliedManifest() throws Exception {
        for (boolean changed : new boolean[]{false, true}) {
            Control c = new Control(changed);
            GameFileTransaction.VerifiedOriginals proof = c.transaction.verifyOriginals();
            java.util.List<String> writes = c.transaction.changedWrites(c.hashes, proof);
            assertEquals(changed ? java.util.Collections.singletonList("1/1.db") : java.util.Collections.emptyList(), writes);
            for (String name : writes) c.transaction.write("packages/" + name,
                new File(c.journal.getDirectory(), "out/" + name), c.hashes.getString(name), false);
            c.transaction.finishApply(c.hashes, proof);
            assertEquals(changed ? 1 : 0, c.device.writes);
            assertEquals(1, c.transaction.getOriginalHashPasses());
            JSONObject applied = new JSONObject(new String(Files.readAllBytes(
                new File(c.journal.getDirectory(), "applied-manifest.json").toPath()), StandardCharsets.UTF_8)).getJSONObject("files");
            assertEquals(3, applied.length()); // Full packages, including skipped shard and metadata.
            for (String name : new String[]{"1/1.db", "1/1_0.db"})
                assertEquals(c.hashes.getString(name), applied.getJSONObject("packages/" + name).getString("sha256"));
            assertTrue(c.journal.getPayloadVerified());
            try { c.journal.outcome(PatchPhase.COMPLETE, new JSONObject()); fail("APK audit omitted"); }
            catch (IllegalStateException expected) { }
        }
    }

    @Test public void testCorruptCurrentAndRetainedFilesNeverQualifyForSkip() throws Exception {
        Control c = new Control(false);
        GameFileTransaction.VerifiedOriginals proof = c.transaction.verifyOriginals();
        c.device.files.put("packages/1/1.db", bytes("external update"));
        try { c.transaction.changedWrites(c.hashes, proof); fail("Corrupt live source skipped"); }
        catch (IllegalStateException | AssertionError expected) { }
        c = new Control(false); proof = c.transaction.verifyOriginals();
        put(new File(c.journal.getDirectory(), "snapshot/packages/1/1.db"), bytes("damaged retained source"));
        try { c.transaction.changedWrites(c.hashes, proof); fail("Changed retained proof accepted"); }
        catch (IllegalStateException expected) { }
        assertEquals(0, c.device.writes);
    }

    @Test public void testProofIsTransactionScopedAndRecoveryHashesOnce() throws Exception {
        Control c = new Control(true); c.applyOne(); c.restoring();
        GameFileTransaction.VerifiedOriginals proof = c.transaction.verifyOriginals();
        GameFileTransaction other = new GameFileTransaction(c.journal, c.device);
        try { other.prepareRollback(proof); fail("Foreign transaction proof accepted"); }
        catch (IllegalStateException expected) { }
        c.transaction.prepareRollback(proof);
        c.transaction.rollback(proof, file -> kotlin.Unit.INSTANCE);
        assertEquals(1, c.transaction.getOriginalHashPasses());
        // One apply and one rollback of the touched index; unchanged shard/info never written. Rollback
        // always ends by restoring Watchdog from the snapshot, which the audit proved still original.
        assertEquals(java.util.Arrays.asList("packages/1/1.db", "packages/1/1.db", "Watchdog/list.db"), c.device.written);
        assertEquals(3, c.device.writes);
        try { c.transaction.prepareRollback(proof); fail("Consumed proof accepted"); }
        catch (IllegalStateException expected) { }
        // A fresh invocation must rehash; there is no durable verified-originals token.
        other = new GameFileTransaction(SessionJournal.Companion.load(c.journal.getDirectory()), c.device);
        other.verifyOriginals(); assertEquals(1, other.getOriginalHashPasses());
    }

    @Test public void testNewerMissingAndExtraLiveBytesPauseBeforeRollbackWrites() throws Exception {
        for (String fault : new String[]{"changed", "missing", "extra"}) {
            Control c = new Control(true); c.applyOne(); c.restoring();
            if (fault.equals("changed")) c.device.files.put("packages/1/1.db", bytes("new game update"));
            if (fault.equals("missing")) c.device.files.remove("packages/1/1_0.db");
            if (fault.equals("extra")) c.device.files.put("packages/1/1_2.db", bytes("new shard"));
            int before = c.device.writes;
            try { c.transaction.rollback(); fail("External change overwritten: " + fault); }
            catch (IllegalStateException expected) { }
            assertEquals(before, c.device.writes);
            assertTrue(c.journal.getDirtyPackages());
            assertTrue(new File(c.journal.getDirectory(), "snapshot/Watchdog/list.db").isFile());
        }
    }

    @Test public void testMutationAfterWholeAuditIsRefusedAtRollbackRenameBoundary() throws Exception {
        Control c = new Control(true); c.applyOne(); c.restoring();
        GameFileTransaction.VerifiedOriginals proof = c.transaction.verifyOriginals();
        c.transaction.prepareRollback(proof);
        try {
            c.transaction.rollback(proof, file -> {
                c.device.files.put("packages/1/1.db", bytes("update between audit and rename"));
                return kotlin.Unit.INSTANCE;
            });
            fail("Race at rename was overwritten");
        } catch (IllegalStateException expected) { }
        assertEquals(1, c.device.writes);
        assertArrayEquals(bytes("update between audit and rename"), c.device.files.get("packages/1/1.db"));
        assertTrue(c.journal.getHasMutationIntent());
    }

    @Test public void testFileMetricsCountTheFullPlanAndOnlyAcknowledgedWrites() throws Exception {
        Control c = new Control(true); GameFileTransaction.VerifiedOriginals proof = c.transaction.verifyOriginals();
        java.util.List<String> changed = c.transaction.changedWrites(c.hashes, proof);
        RunMetrics metrics = new RunMetrics(InstrumentationRegistry.getInstrumentation().getTargetContext(),
            new File(c.journal.getDirectory(), "resource-metrics.json"));
        metrics.filePlan(proof.files(), c.hashes, c.journal.getResultRoot(), changed);
        metrics.fileWritten(new File(c.journal.getDirectory(), "out/1/1.db").length());
        metrics.originalHashPasses(c.transaction.getOriginalHashPasses());
        JSONObject io = metrics.finish("control").getJSONObject("file_io");
        assertEquals(4, io.getInt("original_files")); assertEquals(2, io.getInt("planned_files"));
        assertEquals(1, io.getInt("written_files")); assertEquals(1, io.getInt("skipped_files"));
        assertEquals(io.getLong("planned_bytes"), io.getLong("written_bytes") + io.getLong("skipped_bytes"));
        assertEquals(1, io.getInt("original_hash_passes"));
    }

    @Test public void testExplicitlyCreatedStagedFileIsDeletedByRollback() throws Exception {
        Control c = new Control(false); String name = "1/1_2.db"; byte[] added = bytes("appended prime file");
        put(new File(c.journal.getDirectory(), "out/" + name), added); c.hashes.put(name, hash(added));
        put(new File(c.journal.getDirectory(), "staged-hashes.json"), bytes(c.hashes.toString()));
        c.transaction.write("packages/" + name, new File(c.journal.getDirectory(), "out/" + name), hash(added), false);
        c.restoring(); c.transaction.rollback();
        assertFalse(c.device.files.containsKey("packages/" + name));
        assertEquals(4, c.device.files.size());
        // The created file's apply, then rollback's Watchdog restoration; no untouched package is written.
        assertEquals(java.util.Arrays.asList("packages/" + name, "Watchdog/list.db"), c.device.written);
        assertEquals(2, c.device.writes);
        assertFalse(c.journal.getDirtyPackages());
    }

}
