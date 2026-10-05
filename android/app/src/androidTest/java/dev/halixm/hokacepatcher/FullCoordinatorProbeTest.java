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
        int installs, writes, failAfter;
        Device(File root, ApkIdentity normal, ApkIdentity access) {
            this.root = root; this.normal = normal; this.access = access; installed = normal;
        }
        void parents(String name) {
            while (name.contains("/")) { name = name.substring(0, name.lastIndexOf('/')); directories.add(name); }
        }
        @Override public String estimateGameSnapshot() { return "{\"archive_budget\":1048576}"; }
        @Override public void forceStopGame() { /* Simulation only: no shell/process API. */ }
        @Override public String replaceGameApk(ParcelFileDescriptor descriptor, long bytes) {
            try (FileInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()))) {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] buffer = new byte[1024 * 1024]; long length = 0; int count;
                while ((count = input.read(buffer)) >= 0) { length += count; assertTrue(length <= bytes); digest.update(buffer, 0, count); }
                assertEquals(bytes, length); String hash = hex(digest.digest());
                assertTrue(hash.equals(normal.getSha256()) || hash.equals(access.getSha256()));
                installed = hash.equals(normal.getSha256()) ? normal : access; installs++;
                return "fake installed and hashed";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
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
    private void runFull(boolean fault) throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "coordinator-full-probes/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        File base = new File(actual.getFilesDir(), "scratch/control-1402-verified");
        JSONObject control = json(new File(base, "control.json"));
        String normalHash = control.getJSONObject("apk").getString("sha256");
        File normalFile = new File(actual.getFilesDir(), "recovery/" + normalHash + "/normal.apk");
        File accessFile = new File(actual.getFilesDir(), "scratch/game-access-1402/access.apk");
        ApkIdentity normal = ApkIdentity.Companion.read(actual, normalFile); normal.requireRecovery();
        ApkIdentity access = ApkIdentity.Companion.read(actual, accessFile);
        File cached = new RecoveryStore(scoped).normal(normalHash); assertTrue(cached.getParentFile().mkdirs());
        Files.createSymbolicLink(cached.toPath(), normalFile.toPath()); put(new File(cached.getParentFile(), "identity.json"), normal.json().toString().getBytes(StandardCharsets.UTF_8));
        Device device = new Device(new File(root, "backend"), normal, access); device.failAfter = fault ? 1 : 0;
        JSONObject originals = control.getJSONObject("verified_source_files");
        for (Iterator<String> names = originals.keys(); names.hasNext();) {
            String name = names.next(); File source = new File(base, "game/WXQ_Data/Package/builtin/" + name);
            assertEquals(originals.getString(name), ApkIdentity.Companion.digest(source));
            device.files.put("packages/" + name, source); device.parents("packages/" + name);
        }
        assertEquals(653, originals.length());
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
            try { coordinator.run(normalHash, accessFile); fail("Full-data post-commit fault was not injected"); }
            catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("Fake full-data write")); }
        } else coordinator.run(normalHash, accessFile);
        File[] sessions = new File(root, "sessions").listFiles(File::isDirectory); assertNotNull(sessions); assertEquals(1, sessions.length);
        SessionJournal journal = SessionJournal.Companion.load(sessions[0]);
        assertEquals(fault ? PatchPhase.CANCELLED : PatchPhase.COMPLETE, journal.getPhase());
        assertFalse(journal.getDirtyPackages()); assertFalse(journal.getHasMutationIntent()); assertEquals(normal, device.installed);
        JSONObject counts = journal.snapshot().getJSONObject("counts");
        assertEquals(391, counts.getInt("text_tables")); assertEquals(395, counts.getInt("applied_textures"));
        assertEquals(1, counts.getInt("skipped_tables")); assertEquals(0, counts.getInt("skipped_textures"));
        JSONObject terminal = journal.terminalResult(); assertEquals(fault ? "recovered" : "complete", terminal.getString("status"));
        assertEquals(!fault, terminal.has("counts"));
        JSONObject stage = json(new File(sessions[0], "staged-hashes.json"));
        JSONObject firstStage = json(new File(base, "staged-hashes.json")); assertEquals(12, stage.length());
        for (Iterator<String> names = stage.keys(); names.hasNext();) { String name = names.next(); assertEquals(firstStage.getString(name), stage.getString(name)); }
        if (fault) {
            assertEquals(before.keySet(), device.files.keySet());
            for (String name : before.keySet()) assertEquals(ApkIdentity.Companion.digest(before.get(name)), ApkIdentity.Companion.digest(device.files.get(name)));
            assertTrue(device.directories.contains("Watchdog/src")); assertTrue(device.directories.contains("Watchdog/dst"));
        } else {
            assertFalse(device.files.keySet().stream().anyMatch(name -> name.startsWith("Watchdog/")));
            for (Iterator<String> names = stage.keys(); names.hasNext();) { String name = names.next(); assertEquals(stage.getString(name), ApkIdentity.Companion.digest(device.files.get("packages/" + name))); }
        }
        for (Iterator<String> names = originals.keys(); names.hasNext();) { String name = names.next(); assertEquals(originals.getString(name), ApkIdentity.Companion.digest(before.get("packages/" + name))); }
        // Keep durable receipts before removing only this resolved private fixture's duplicates.
        for (String name : new String[]{"journal.json", "snapshot/manifest.json", "staged-hashes.json", "resource-metrics.json", "out/device_patch_summary.json", "build.log"}) {
            File source = new File(sessions[0], name); if (source.isFile()) put(new File(root, "receipts/" + name), Files.readAllBytes(source.toPath()));
        }
        JSONObject receipt = new JSONObject().put("fault_after_file", fault ? 1 : 0).put("terminal", terminal)
            .put("source_files", originals.length()).put("staged_files", stage.length()).put("fake_installs", device.installs)
            .put("fake_writes", device.writes).put("production_snapshot_cap_bytes", 8L * 1024 * 1024 * 1024);
        put(new File(root, "receipts/result.json"), receipt.toString().getBytes(StandardCharsets.UTF_8));
        for (String name : new String[]{"work", "out", "snapshot", "access.apk", "game", "normal.apk"}) prune(new File(sessions[0], name));
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
    @Test public void testFullSnapshotBuildApplyAndNormalRestore() throws Exception { runFull(false); }
    @Test public void testFullPostCommitFailureRollsBackAllFiles() throws Exception { runFull(true); }
}
