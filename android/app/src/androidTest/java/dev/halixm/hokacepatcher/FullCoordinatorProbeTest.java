package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Complete production coordinator runs over all approved private inputs; installation is fake. */
@RunWith(AndroidJUnit4.class)
public final class FullCoordinatorProbeTest {
    private static JSONObject json(File path) throws Exception {
        return new JSONObject(new String(Files.readAllBytes(path.toPath()), StandardCharsets.UTF_8));
    }
    private static void put(File path, byte[] value) throws Exception {
        assertTrue(path.getParentFile().isDirectory() || path.getParentFile().mkdirs());
        try (FileOutputStream output = new FileOutputStream(path)) { output.write(value); output.getFD().sync(); }
    }
    private static String hex(byte[] value) {
        StringBuilder result = new StringBuilder();
        for (byte part : value) result.append(String.format("%02x", part & 255));
        return result.toString();
    }
    private static final class Device extends IPrivilegedDeviceService.Stub {
        final Map<String, File> files = new LinkedHashMap<>();
        final Set<String> directories = new TreeSet<>();
        final File root;
        final ApkIdentity normal, access;
        ApkIdentity installed;
        int installs, writes, failAfter, snapshots, estimates;
        boolean failSnapshot, failNormalRestore;
        Device(File root, ApkIdentity normal, ApkIdentity access) {
            this.root = root; this.normal = normal; this.access = access; installed = normal;
        }
        void parents(String name) {
            while (name.contains("/")) { name = name.substring(0, name.lastIndexOf('/')); directories.add(name); }
        }
        @Override public String estimateGameSnapshot() { estimates++; return "{\"archive_budget\":1048576}"; }
        @Override public void forceStopGame() { /* Simulation only: no shell/process API. */ }
        @Override public String replaceGameApk(ParcelFileDescriptor descriptor, long bytes) {
            try (FileInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()))) {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] buffer = new byte[1024 * 1024]; long length = 0; int count;
                while ((count = input.read(buffer)) >= 0) { length += count; assertTrue(length <= bytes); digest.update(buffer, 0, count); }
                assertEquals(bytes, length); String hash = hex(digest.digest());
                assertTrue(hash.equals(normal.getSha256()) || hash.equals(access.getSha256()));
                if (failNormalRestore && hash.equals(normal.getSha256())) {
                    throw new IllegalStateException("Fake normal APK restore failed");
                }
                installed = hash.equals(normal.getSha256()) ? normal : access; installs++;
                return "fake installed and hashed";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String reconcileGameFiles(String session, String operation, String relative,
                ParcelFileDescriptor policy, ParcelFileDescriptor source, long length, String sha256) {
            return PrivateRecoveryPolicy.apply(this, files, session, operation, relative, policy, source, length, sha256);
        }
        @Override public String validateGameSnapshot(ParcelFileDescriptor descriptor) {
            try (FileInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()))) {
                byte[] data = new byte[1024 * 1024]; int size = 0, count;
                while ((count = input.read(data, size, data.length - size)) > 0) { size += count; assertTrue(size < data.length); }
                JSONObject expected = new JSONObject(new String(data, 0, size, StandardCharsets.UTF_8)).getJSONObject("files");
                assertEquals(files.size(), expected.length());
                for (Map.Entry<String, File> entry : files.entrySet()) {
                    JSONObject identity = expected.getJSONObject(entry.getKey());
                    assertEquals(identity.getLong("bytes"), entry.getValue().length());
                    assertEquals(identity.getString("sha256"), ApkIdentity.Companion.digest(entry.getValue()));
                }
                return "fake complete layer verified";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String writeGameFile(String session, String relative, ParcelFileDescriptor descriptor, long bytes, String sha) {
            try {
                GameFilePolicy.INSTANCE.session(session); GameFilePolicy.INSTANCE.validate(relative, true);
                File target = new File(root, "overrides/" + relative);
                assertTrue(target.getParentFile().isDirectory() || target.getParentFile().mkdirs());
                File temporary = new File(target.getParentFile(), target.getName() + ".partial");
                MessageDigest digest = MessageDigest.getInstance("SHA-256"); long length = 0;
                try (FileInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()));
                     FileOutputStream output = new FileOutputStream(temporary)) {
                    byte[] buffer = new byte[1024 * 1024]; int count;
                    while ((count = input.read(buffer)) >= 0) { length += count; assertTrue(length <= bytes); digest.update(buffer, 0, count); output.write(buffer, 0, count); }
                    output.getFD().sync();
                }
                assertEquals(bytes, length); assertEquals(sha, hex(digest.digest()));
                Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                assertEquals(sha, ApkIdentity.Companion.digest(target)); files.put(relative, target); parents(relative);
                if (++writes == failAfter) throw new IllegalStateException("Fake full-data write committed before acknowledgment loss");
                return "fake committed and rehashed";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public void clearGameWatchdog() {
            files.keySet().removeIf(name -> name.startsWith("Watchdog/"));
            directories.removeIf(name -> name.startsWith("Watchdog/")); directories.add("Watchdog");
        }
        @Override public void restoreWatchdogDirectory(String relative) { GameFilePolicy.INSTANCE.watchdogDirectory(relative); directories.add(relative); }
        @Override public void clearSessionTemp(String session, String relative) { GameFilePolicy.INSTANCE.session(session); }
        @Override public String snapshotGame(ParcelFileDescriptor descriptor, long maximum) {
            if (failSnapshot) throw new IllegalStateException("Fake snapshot transfer interrupted");
            snapshots++;
            try (OutputStream output = new ParcelFileDescriptor.AutoCloseOutputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()))) {
                Tar tar = new Tar(output, maximum);
                for (String directory : directories) tar.header(directory, 0, true);
                byte[] buffer = new byte[1024 * 1024];
                for (Map.Entry<String, File> entry : files.entrySet()) {
                    GameFilePolicy.INSTANCE.validate(entry.getKey(), false);
                    tar.header(entry.getKey(), entry.getValue().length(), false);
                    try (FileInputStream input = new FileInputStream(entry.getValue())) {
                        int count; while ((count = input.read(buffer)) >= 0) tar.write(buffer, count);
                    }
                    int remainder = (int)(entry.getValue().length() % 512);
                    if (remainder != 0) tar.write(new byte[512 - remainder], 512 - remainder);
                }
                tar.write(new byte[1024], 1024); output.flush();
                return new JSONObject().put("bytes", tar.bytes).put("sha256", hex(tar.digest.digest())).toString();
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String diagnostics() { throw new UnsupportedOperationException(); }
        @Override public String gameApkInfo() { throw new UnsupportedOperationException(); }
        @Override public String copyGameApk(ParcelFileDescriptor destination) { throw new UnsupportedOperationException(); }
        @Override public byte[] probeFixture(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String reinstallFixture(boolean abandon) { throw new UnsupportedOperationException(); }
        @Override public String probeGame(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public void validateFirstSetupSource(String sha) { throw new UnsupportedOperationException(); }
        @Override public void checkGameProfiles() { throw new UnsupportedOperationException(); }
        @Override public String releaseReplacedGameApks() { return "{\"released\":false,\"freed_bytes\":0}"; }
        @Override public void deleteGameFile(String session, String relative, String sha) { files.remove(relative); }
        @Override public boolean firstSetupGameAbsent() { throw new UnsupportedOperationException(); }
        @Override public void removeGameForFirstSetup(String sha) { throw new UnsupportedOperationException(); }
        @Override public String installFirstSetupGame(ParcelFileDescriptor source, long length) { throw new UnsupportedOperationException(); }
        @Override public void destroy() { throw new UnsupportedOperationException(); }
    }
    private static final class Tar {
        final OutputStream output; final long maximum; final MessageDigest digest;
        long bytes;
        Tar(OutputStream output, long maximum) throws Exception { this.output = output; this.maximum = maximum; digest = MessageDigest.getInstance("SHA-256"); }
        void write(byte[] value, int length) throws Exception { bytes += length; assertTrue(bytes <= maximum); output.write(value, 0, length); digest.update(value, 0, length); }
        void text(byte[] header, int offset, int size, String value) {
            byte[] encoded = value.getBytes(StandardCharsets.US_ASCII); assertTrue(encoded.length < size);
            System.arraycopy(encoded, 0, header, offset, encoded.length);
        }
        void octal(byte[] header, int offset, int size, long value) { text(header, offset, size, String.format("%0" + (size - 1) + "o", value)); }
        void header(String name, long size, boolean directory) throws Exception {
            byte[] header = new byte[512]; text(header, 0, 100, name);
            octal(header, 100, 8, directory ? 0700 : 0600); octal(header, 108, 8, 0); octal(header, 116, 8, 0);
            octal(header, 124, 12, size); octal(header, 136, 12, 1600000000);
            for (int index = 148; index < 156; index++) header[index] = 32;
            header[156] = (byte)(directory ? '5' : '0'); text(header, 257, 6, "ustar");
            header[263] = '0'; header[264] = '0'; int sum = 0; for (byte part : header) sum += part & 255;
            text(header, 148, 7, String.format("%06o", sum)); header[155] = 32; write(header, 512);
        }
    }
    /**
     * <fault> cuts the apply after its first committed file. <resume> then dispatches the same saved Start
     * again: the device's snapshot/estimate counters and the run's persisted per-stage attempt counters prove
     * the published snapshot and STAGED build are reused and only the apply runs again.
     */
    private void runFull(boolean fault, boolean resume) throws Exception {
        runFull(fault, resume, false);
    }
    private void runFull(boolean fault, boolean resume, boolean repeat) throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir().getCanonicalFile(), "coordinator-full-probes/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        PrivateProbeFixtures fixture = PrivateProbeFixtures.load(actual);
        File sourceRoot = fixture.sourceRoot();
        JSONObject control = fixture.descriptor;
        String normalHash = fixture.normal.getSha256();
        File normalFile = fixture.normalFile, accessFile = fixture.accessFile;
        ApkIdentity normal = fixture.normal, access = fixture.access;
        File cached = new RecoveryStore(scoped).normal(normalHash); assertTrue(cached.getParentFile().mkdirs());
        Files.copy(normalFile.toPath(), cached.toPath()); put(new File(cached.getParentFile(), "identity.json"), normal.json().toString().getBytes(StandardCharsets.UTF_8));
        String runId = AuthorizedProbeRun.create(scoped, fixture, "translate");
        Device device = new Device(new File(root, "backend"), normal, access); device.failAfter = fault ? 1 : 0;
        JSONObject originals = control.getJSONObject("source_files");
        for (Iterator<String> names = originals.keys(); names.hasNext();) {
            String name = names.next(); File source = new File(sourceRoot, name);
            assertEquals(originals.getString(name), ApkIdentity.Companion.digest(source));
            device.files.put("packages/" + name, source); device.parents("packages/" + name);
        }
        assertTrue(originals.length() > 0);
        for (String name : new String[]{"BrokenList.db", "PatchList.db", "StorageStatus.db", "History.db"}) {
            File source = new File(root, "backend/original-watchdog/" + name); put(source, ("fixture-" + name).getBytes(StandardCharsets.UTF_8));
            device.files.put("Watchdog/" + name, source);
        }
        device.directories.add("Watchdog"); device.directories.add("Watchdog/src"); device.directories.add("Watchdog/dst");
        Map<String, File> before = new LinkedHashMap<>(device.files);
        PatchCoordinator coordinator = new PatchCoordinator(scoped, device, message -> {
            android.util.Log.i("HokAceFullCoordinator", (fault ? "fault: " : "success: ") + message); return kotlin.Unit.INSTANCE;
        }, expected -> { if (!expected.equals(device.installed)) throw new IllegalStateException("Fake installed APK identity differs"); });
        if (fault) {
            try { coordinator.dispatch(runId, "translate", ShellProvider.SHIZUKU); fail("Full-data post-commit fault was not injected"); }
            catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("Fake full-data write")); }
        } else coordinator.dispatch(runId, "translate", ShellProvider.SHIZUKU);
        if (resume) {
            File[] cut = new File(root, "sessions").listFiles(File::isDirectory); assertNotNull(cut); assertEquals(1, cut.length);
            SessionJournal interrupted = SessionJournal.Companion.load(cut[0]);
            assertEquals(PatchPhase.CANCELLED, interrupted.getPhase());
            // An unexpected interruption recovers consistency; it never revokes the saved action.
            assertTrue(new RunStore(scoped).load(runId).getMayContinue());
            String attempt = interrupted.snapshot().getString("build_attempt");
            int snapshots = device.snapshots, estimates = device.estimates;
            device.failAfter = 0;
            JSONObject resumed = new PatchCoordinator(scoped, device, message -> kotlin.Unit.INSTANCE,
                expected -> { if (!expected.equals(device.installed)) throw new IllegalStateException("Fake installed APK identity differs"); })
                .dispatch(runId, "translate", ShellProvider.SHIZUKU);
            assertEquals("complete", resumed.getString("status"));
            assertEquals("Published snapshot was taken again", snapshots, device.snapshots);
            assertEquals(estimates, device.estimates);
            SessionJournal done = SessionJournal.Companion.load(cut[0]);
            assertEquals(attempt, done.snapshot().getString("build_attempt"));
            File[] attempts = new File(cut[0], "build-attempts").listFiles(File::isDirectory);
            assertNotNull(attempts); assertEquals("STAGED build was rebuilt", 1, attempts.length);
            RunStore.Run finished = new RunStore(scoped).load(runId);
            assertEquals("complete", finished.getLifecycle());
            assertEquals(1, finished.getAttempts().getInt("snapshot"));
            assertEquals(1, finished.getAttempts().getInt("build"));
            assertEquals(2, finished.getAttempts().getInt("apply"));
            assertEquals(1, done.snapshot().getInt("continuations"));
        }
        boolean ended = fault && !resume;
        File[] sessions = new File(root, "sessions").listFiles(File::isDirectory); assertNotNull(sessions); assertEquals(1, sessions.length);
        SessionJournal journal = SessionJournal.Companion.load(sessions[0]);
        assertEquals(ended ? PatchPhase.CANCELLED : PatchPhase.COMPLETE, journal.getPhase());
        assertFalse(journal.getDirtyPackages()); assertFalse(journal.getHasMutationIntent()); assertEquals(normal, device.installed);
        JSONObject counts = journal.snapshot().getJSONObject("counts");
        JSONObject expectedCounts = control.getJSONObject("expected_counts");
        for (Iterator<String> names = expectedCounts.keys(); names.hasNext();) {
            String name = names.next(); assertEquals(expectedCounts.getInt(name), counts.getInt(name));
        }
        JSONObject terminal = journal.terminalResult(); assertEquals(ended ? "recovered" : "complete", terminal.getString("status"));
        assertEquals(!ended, terminal.has("counts"));
        JSONObject stage = json(new File(journal.getResultRoot(), "staged-hashes.json"));
        JSONObject firstStage = control.getJSONObject("staged_hashes"); assertEquals(firstStage.length(), stage.length());
        JSONObject io = json(new File(journal.getDirectory(), "resource-metrics.json")).getJSONObject("file_io");
        assertEquals(stage.length(), io.getInt("planned_files"));
        if (!ended) assertEquals(stage.length(), io.getInt("skipped_files") + io.getInt("written_files"));
        if (!ended) assertEquals(io.getLong("planned_bytes"), io.getLong("skipped_bytes") + io.getLong("written_bytes"));
        assertEquals(1, io.getInt("original_hash_passes"));
        for (Iterator<String> names = stage.keys(); names.hasNext();) { String name = names.next(); assertEquals(firstStage.getString(name), stage.getString(name)); }
        if (ended) {
            assertEquals(before.keySet(), device.files.keySet());
            for (String name : before.keySet()) assertEquals(ApkIdentity.Companion.digest(before.get(name)), ApkIdentity.Companion.digest(device.files.get(name)));
            assertTrue(device.directories.contains("Watchdog/src")); assertTrue(device.directories.contains("Watchdog/dst"));
        } else {
            assertFalse(device.files.keySet().stream().anyMatch(name -> name.startsWith("Watchdog/")));
            for (Iterator<String> names = stage.keys(); names.hasNext();) { String name = names.next(); assertEquals(stage.getString(name), ApkIdentity.Companion.digest(device.files.get("packages/" + name))); }
        }
        for (Iterator<String> names = originals.keys(); names.hasNext();) { String name = names.next(); assertEquals(originals.getString(name), ApkIdentity.Companion.digest(before.get("packages/" + name))); }
        if (repeat) {
            int writesBefore = device.writes, installsBefore = device.installs, snapshotsBefore = device.snapshots;
            JSONObject prior = json(new File(journal.getDirectory(), "completion-receipt.json"));
            assertEquals("verified_complete", prior.getString("outcome"));
            String next = AuthorizedProbeRun.create(scoped, fixture, "translate");
            JSONObject result = new PatchCoordinator(scoped, device, message -> kotlin.Unit.INSTANCE,
                expected -> { if (!expected.equals(device.installed)) throw new IllegalStateException("Actual fake APK differs"); })
                .dispatch(next, "translate", ShellProvider.SHIZUKU);
            assertEquals("complete", result.getString("status"));
            SessionJournal repeated = SessionJournal.Companion.load(new File(root, "sessions/" + next));
            assertTrue("Completion shortcut missing", repeated.snapshot().has("completion_reuse"));
            assertFalse("Translation build repeated", new RunStore(scoped).load(next).getAttempts().has("build"));
            assertEquals("Identical payload was rewritten", writesBefore, device.writes);
            assertEquals("Fresh actual snapshot audit retained", snapshotsBefore + 1, device.snapshots);
            assertEquals("Mandatory shell access/normal installs", installsBefore + 2, device.installs);
            assertEquals(normal, device.installed);
            assertEquals(ArtifactReceipts.INSTANCE.canonical(prior.get("counts")),
                ArtifactReceipts.INSTANCE.canonical(json(new File(repeated.getDirectory(), "completion-receipt.json")).get("counts")));
            JSONObject lineage = json(new File(repeated.getResultRoot(), "reuse-provenance.json"));
            assertEquals(runId, lineage.getString("run_id"));
        }
        // Keep durable receipts before removing only this resolved private fixture's duplicates.
        for (String name : new String[]{"journal.json", "snapshot/manifest.json", "staged-hashes.json", "resource-metrics.json", "out/device_patch_summary.json", "build.log"}) {
            File source = new File(name.startsWith("journal") || name.startsWith("snapshot") || name.startsWith("resource")
                ? sessions[0] : journal.getResultRoot(), name); if (source.isFile()) put(new File(root, "receipts/" + name), Files.readAllBytes(source.toPath()));
        }
        JSONObject receipt = new JSONObject().put("fault_after_file", ended ? 1 : 0).put("terminal", terminal)
            .put("source_files", originals.length()).put("staged_files", stage.length()).put("fake_installs", device.installs)
            .put("fake_writes", device.writes).put("production_snapshot_cap_bytes", 8L * 1024 * 1024 * 1024);
        put(new File(root, "receipts/result.json"), receipt.toString().getBytes(StandardCharsets.UTF_8));
        for (String name : new String[]{"work", "out", "snapshot", "access.apk", "game", "normal.apk", "build-attempts", "snapshot-attempts"}) prune(new File(sessions[0], name));
        prune(new File(root, "backend/overrides"));
        android.util.Log.i("HokAceFullCoordinator", "PASS " + root.getName() + " " + receipt);
    }
    private static void prune(File path) throws Exception {
        if (!path.exists() && !Files.isSymbolicLink(path.toPath())) return;
        if (!Files.isSymbolicLink(path.toPath()) && path.isDirectory()) {
            File[] children = path.listFiles(); assertNotNull(children); for (File child : children) prune(child);
        }
        assertTrue("Cannot prune resolved private fixture: " + path, path.delete());
    }
    @Test public void testFullSnapshotBuildApplyAndNormalRestore() throws Exception { runFull(false, false); }
    @Test public void testFullPostCommitFailureRollsBackAllFiles() throws Exception { runFull(true, false); }
    @Test public void testContinuationReusesSnapshotAndBuildAfterApplyFault() throws Exception { runFull(true, true); }
    @Test public void testFreshStartReusesCompletionAfterActualFullAudit() throws Exception { runFull(false, false, true); }

    @Test public void testStageFailureWithCleanRecoveryChargesFailingStageAndRecoveryFailureChargesSafety() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PrivateProbeFixtures fixture = PrivateProbeFixtures.load(actual);
        for (boolean breakNormalRestore : new boolean[]{false, true}) {
            File root = new File(actual.getFilesDir().getCanonicalFile(), "coordinator-full-probes/" + UUID.randomUUID());
            assertTrue(root.mkdirs());
            Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
            try {
                File cached = new RecoveryStore(scoped).normal(fixture.normal.getSha256());
                assertTrue(cached.getParentFile().mkdirs());
                Files.copy(fixture.normalFile.toPath(), cached.toPath());
                put(new File(cached.getParentFile(), "identity.json"),
                    fixture.normal.json().toString().getBytes(StandardCharsets.UTF_8));
                String runId = AuthorizedProbeRun.create(scoped, fixture, "translate");
                Device device = new Device(new File(root, "backend"), fixture.normal, fixture.access);
                device.failSnapshot = true;
                device.failNormalRestore = breakNormalRestore;
                File firstSource = new File(fixture.sourceRoot(), fixture.descriptor.getJSONObject("source_files").keys().next());
                String firstName = fixture.descriptor.getJSONObject("source_files").keys().next();
                device.files.put("packages/" + firstName, firstSource); device.parents("packages/" + firstName);
                PatchCoordinator coordinator = new PatchCoordinator(scoped, device, message -> kotlin.Unit.INSTANCE,
                    expected -> { if (!expected.equals(device.installed)) throw new IllegalStateException("Actual fake APK differs"); });
                try {
                    coordinator.dispatch(runId, "translate", ShellProvider.SHIZUKU);
                    fail("Snapshot fault was not thrown");
                } catch (IllegalStateException expected) {
                    assertTrue(expected.getMessage().contains("Fake snapshot transfer interrupted"));
                }
                RunStore runs = new RunStore(scoped);
                runs.recordFailure(runId, breakNormalRestore ? "recovery_required" : "error");
                RunStore.Run saved = runs.load(runId);
                if (!breakNormalRestore) {
                    assertEquals(fixture.normal, device.installed);
                    assertEquals("snapshot", saved.getFailedOperation());
                    assertEquals(1, saved.getAttempts().getInt("recovery_normal_restore"));
                } else {
                    assertEquals(fixture.access, device.installed);
                    assertTrue("Failed normal restore should charge safety op, got " + saved.getFailedOperation(),
                        "recovery_normal_restore".equals(saved.getFailedOperation()) ||
                        "recovery_emergency_normal".equals(saved.getFailedOperation()));
                }
            } finally {
                prune(root);
            }
        }
    }
}
