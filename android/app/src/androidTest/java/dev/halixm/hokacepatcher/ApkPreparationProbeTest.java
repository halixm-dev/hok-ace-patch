package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import java.util.Enumeration;
import java.util.Iterator;
import java.security.MessageDigest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Generate both full game APKs from approved private bytes without binding or installation. */
@RunWith(AndroidJUnit4.class)
public final class ApkPreparationProbeTest {
    private static final String NORMAL = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
    private static JSONObject inventory(File apk) throws Exception {
        JSONObject result = new JSONObject();
        try (ZipFile zip = new ZipFile(apk)) {
            for (Enumeration<? extends ZipEntry> entries = zip.entries(); entries.hasMoreElements();) {
                ZipEntry entry = entries.nextElement(); assertFalse(result.has(entry.getName()));
                MessageDigest hash = MessageDigest.getInstance("SHA-256");
                try (java.io.InputStream stream = zip.getInputStream(entry)) {
                    byte[] buffer = new byte[1024 * 1024]; int count;
                    while ((count = stream.read(buffer)) >= 0) hash.update(buffer, 0, count);
                }
                StringBuilder digest = new StringBuilder();
                for (byte part : hash.digest()) digest.append(String.format("%02x", part & 255));
                result.put(entry.getName(), digest.toString());
            }
        }
        return result;
    }
    private static void put(File path, JSONObject value) throws Exception {
        assertTrue(path.getParentFile().isDirectory() || path.getParentFile().mkdirs());
        try (FileOutputStream output = new FileOutputStream(path)) {
            output.write(value.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
        }
    }
    private static final class Source extends IPrivilegedDeviceService.Stub {
        final File file;
        int copies;
        Source(File file) { this.file = file; }
        @Override public String gameApkInfo() { return "{\"bytes\":" + file.length() + "}"; }
        @Override public String copyGameApk(ParcelFileDescriptor destination) {
            try (FileInputStream input = new FileInputStream(file);
                 FileOutputStream output = new ParcelFileDescriptor.AutoCloseOutputStream(
                     ParcelFileDescriptor.dup(destination.getFileDescriptor()))) {
                byte[] buffer = new byte[1024 * 1024]; int count; long length = 0;
                while ((count = input.read(buffer)) >= 0) { output.write(buffer, 0, count); length += count; }
                output.getFD().sync(); copies++;
                return new JSONObject().put("bytes", length).put("sha256", ApkIdentity.Companion.digest(file)).toString();
            } catch (Exception error) { throw new IllegalStateException(error); }
        }
        private UnsupportedOperationException unsupported() { return new UnsupportedOperationException("No privileged operations in APK preparation fixture"); }
        @Override public String diagnostics() { throw unsupported(); }
        @Override public byte[] probeFixture(byte[] payload) { throw unsupported(); }
        @Override public String estimateGameSnapshot() { throw new UnsupportedOperationException("No snapshot measurement in this fixture"); }
        @Override public void forceStopGame() { throw unsupported(); }
        @Override public String reinstallFixture(boolean abandon) { throw unsupported(); }
        @Override public String replaceGameApk(ParcelFileDescriptor source, long length) { throw unsupported(); }
        @Override public String probeGame(byte[] payload) { throw unsupported(); }
        @Override public String snapshotGame(ParcelFileDescriptor destination, long maximum) { throw unsupported(); }
        @Override public String validateGameSnapshot(ParcelFileDescriptor manifest) { throw unsupported(); }
        @Override public String writeGameFile(String session, String relative, ParcelFileDescriptor source, long length, String sha) { throw unsupported(); }
        @Override public void clearGameWatchdog() { throw unsupported(); }
        @Override public void clearSessionTemp(String session, String relative) { throw unsupported(); }
        @Override public void restoreWatchdogDirectory(String relative) { throw unsupported(); }
        @Override public void validateFirstSetupSource(String sha) { throw new UnsupportedOperationException(); }
        @Override public boolean firstSetupGameAbsent() { throw unsupported(); }
        @Override public void removeGameForFirstSetup(String sha) { throw unsupported(); }
        @Override public String installFirstSetupGame(ParcelFileDescriptor source, long length) { throw unsupported(); }
        @Override public void destroy() { throw unsupported(); }
    }

    @Test public void testFullPreparedPairAndDurableReload() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File input = new File(actual.getFilesDir(), "recovery/" + NORMAL + "/normal.apk");
        ApkIdentity expectedNormal = ApkIdentity.Companion.read(actual, input); expectedNormal.requireRecovery();
        assertEquals(NORMAL, expectedNormal.getSha256());
        File root = new File(actual.getFilesDir(), "apk-preparation-probes/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        RecoveryStore store = new RecoveryStore(scoped);
        File retained = store.normal(NORMAL); assertTrue(retained.getParentFile().mkdirs());
        Files.createSymbolicLink(retained.toPath(), input.toPath());
        put(new File(retained.getParentFile(), "identity.json"), expectedNormal.json());
        Source device = new Source(input);
        RunMetrics metrics = new RunMetrics(scoped, new File(root, "resource-metrics.json"));
        try {
            ApkPreparation preparation = new ApkPreparation(scoped);
            ApkPreparation.Prepared prepared = preparation.prepare(device, message -> { android.util.Log.i("ApkPreparationProbe", message); return kotlin.Unit.INSTANCE; });
            assertEquals(1, device.copies);
            assertEquals(expectedNormal, prepared.getSource());
            assertEquals(expectedNormal, prepared.getNormal());
            assertTrue(prepared.getAccess().getDebuggable());
            assertFalse(prepared.getRequiresSignatureConversion());
            assertFalse(new File(prepared.getDirectory(), "apks/normal.apk").exists());
            assertFalse(new File(prepared.getDirectory(), "apks/unsigned.apk").exists());
            assertEquals(NORMAL, ApkIdentity.Companion.digest(new File(prepared.getDirectory(), "original.apk")));
            assertEquals(prepared.getAccess(), ApkIdentity.Companion.read(scoped, prepared.getAccessFile()));
            ApkPreparation.Prepared reload = new ApkPreparation(scoped).load(prepared.getDirectory().getName());
            assertEquals(prepared.getSource(), reload.getSource());
            assertEquals(prepared.getNormal(), reload.getNormal());
            assertEquals(prepared.getAccess(), reload.getAccess());
            assertEquals(expectedNormal, store.verify(NORMAL));
            JSONObject originalEntries = inventory(input), accessEntries = inventory(prepared.getAccessFile());
            assertEquals(1625, originalEntries.length()); assertEquals(originalEntries.length(), accessEntries.length());
            for (Iterator<String> names = originalEntries.keys(); names.hasNext();) {
                String name = names.next(); assertTrue(accessEntries.has(name));
                if (!name.equals("AndroidManifest.xml")) assertEquals(originalEntries.getString(name), accessEntries.getString(name));
            }
            try (ZipFile expectedAccess = new ZipFile(new File(actual.getFilesDir(), "scratch/game-access-1402/access.apk"));
                 java.io.InputStream manifest = expectedAccess.getInputStream(expectedAccess.getEntry("AndroidManifest.xml"))) {
                MessageDigest hash = MessageDigest.getInstance("SHA-256"); byte[] buffer = new byte[16384]; int count;
                while ((count = manifest.read(buffer)) >= 0) hash.update(buffer, 0, count);
                StringBuilder digest = new StringBuilder();
                for (byte part : hash.digest()) digest.append(String.format("%02x", part & 255));
                assertEquals(digest.toString(), accessEntries.getString("AndroidManifest.xml"));
            }
            put(new File(root, "source-entries.json"), originalEntries);
            put(new File(root, "access-entries.json"), accessEntries);
            put(new File(root, "accepted.json"), new JSONObject().put("schema", 1)
                .put("preparation", prepared.getDirectory().getName()).put("source", prepared.getSource().json())
                .put("normal", prepared.getNormal().json()).put("access", prepared.getAccess().json())
                .put("receipt_reload", true).put("live_operations", 0).put("entry_count", originalEntries.length())
                .put("only_changed_entry", "AndroidManifest.xml"));
            metrics.finish("complete");
            // Only this accepted fixture's generated large files are disposable. Retain receipts/cache link.
            File canonicalPreparation = prepared.getDirectory().getCanonicalFile();
            assertFalse(Files.isSymbolicLink(prepared.getDirectory().toPath()));
            assertEquals(new File(root, "preparations").getCanonicalFile(), canonicalPreparation.getParentFile());
            for (File generated : new File[]{new File(prepared.getDirectory(), "original.apk")}) {
                assertFalse(Files.isSymbolicLink(generated.toPath()));
                assertEquals(new File(canonicalPreparation, generated.getName()), generated.getCanonicalFile());
                assertTrue(generated.delete());
            }
            assertEquals(expectedNormal, ApkIdentity.Companion.read(actual, input));
            put(new File(root, "cleanup.json"), new JSONObject().put("generated_source_removed", true).put("access_retained_for_sdk_verification", true)
                .put("protected_normal_unchanged", true));
        } catch (Throwable error) {
            metrics.finish("failed"); throw error;
        }
    }
}
