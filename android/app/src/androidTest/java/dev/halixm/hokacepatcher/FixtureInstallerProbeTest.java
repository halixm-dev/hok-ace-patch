package dev.halixm.hokacepatcher;

import android.content.ComponentName;
import android.content.Context;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;
import org.junit.Test;
import rikka.shizuku.Shizuku;
import static org.junit.Assert.*;

/** Real fixture-only uninstall, service death, invalid install and exact-source restoration. */
public final class FixtureInstallerProbeTest {
    private static String shell(String command) throws Exception {
        ParcelFileDescriptor[] pipe = InstrumentationRegistry.getInstrumentation().getUiAutomation()
            .executeShellCommandRw("/system/bin/sh");
        try (ParcelFileDescriptor.AutoCloseOutputStream input = new ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])) {
            input.write((command + "\n").getBytes(StandardCharsets.UTF_8));
        }
        try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(pipe[0])) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) >= 0) {
                output.write(buffer, 0, count);
                assertTrue(output.size() <= 16384);
            }
            return output.toString("UTF-8");
        }
    }

    @Test public void testFixtureReplacementRetainsDataAndExactApk() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try {
            assertTrue("Start Shizuku", available.await(15, TimeUnit.SECONDS));
            assertEquals(PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        } finally { Shizuku.removeBinderReceivedListener(listener); }
        String id = UUID.randomUUID().toString();
        File root = new File(context.getFilesDir(), "fixture-replacement-probes/" + id);
        assertTrue(root.mkdirs());
        File source = new File(root, "original-fixture.apk");
        String marker = "files/installer-retain-" + id;
        String payload = "retained-" + id;
        JSONObject receipt = new JSONObject().put("fixture", PrivilegedDeviceService.FIXTURE)
            .put("uninstall_performed", false).put("game_mutated", false).put("replacement_acknowledged", false);
        try (Binding binding = new Binding(context)) {
            IPrivilegedDeviceService device = binding.device();
            JSONObject target = new JSONObject(device.diagnostics());
            assertEquals(PrivilegedDeviceService.FIXTURE, target.getString("apk_package"));
            assertEquals(PrivilegedDeviceService.FIXTURE, target.getString("data_package"));
            String expected = copy(device, source).getString("sha256");
            receipt.put("source_sha256", expected).put("source_bytes", source.length());
            assertEquals(PrivilegedDeviceService.FIXTURE, java.util.Objects.requireNonNull(context.getPackageManager()
                .getPackageArchiveInfo(source.getPath(), PackageManager.GET_SIGNING_CERTIFICATES)).packageName);
            assertTrue(source.setReadOnly());
            assertEquals("fixture-marker", shell("run-as io.github.hokace.fixture sh -c 'set -e; " +
                "mkdir -p files; [ ! -e " + marker + " ] && [ ! -L " + marker + " ]; " +
                "printf " + payload + " > " + marker + "; sync " + marker + "; sync files; printf fixture-marker'"));
            Throwable failure = null;
            try {
                device.forceStopGame(); // This binding fixes the target to the disposable fixture.
                try (ParcelFileDescriptor input = ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY)) {
                    receipt.put("installer", new JSONObject(device.replaceGameApk(input, source.length())));
                }
                receipt.put("replacement_acknowledged", true);
            } catch (Exception | AssertionError error) {
                failure = error;
                receipt.put("error", error.toString());
                throw error;
            } finally {
                try {
                    JSONObject actual = copy(device, new File(root, "after-fixture.apk"));
                    assertEquals(expected, actual.getString("sha256"));
                    assertEquals(payload, shell("run-as io.github.hokace.fixture cat " + marker));
                    receipt.put("installed_sha256", actual.getString("sha256")).put("data_retained", true);
                    assertEquals("fixture-marker-clean", shell("run-as io.github.hokace.fixture sh -c 'set -e; " +
                        "[ \"$(cat " + marker + ")\" = \"" + payload + "\" ]; rm " + marker + "; sync files; printf fixture-marker-clean'"));
                    receipt.put("marker_cleaned", true);
                } catch (Exception | AssertionError verification) {
                    receipt.put("verification_error", verification.toString());
                    if (failure != null) failure.addSuppressed(verification); else throw verification;
                } finally {
                    try (FileOutputStream output = new FileOutputStream(new File(root, "receipt.json"))) {
                        output.write(receipt.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
                    }
                    DurableFiles.INSTANCE.syncDirectory(root);
                    android.util.Log.i("HokAceProbe", "Fixture replacement " + id + " " + receipt);
                }
            }
        }
    }

    @Test public void testFixedFixtureTargetReadOnly() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try { assertTrue(available.await(15, TimeUnit.SECONDS)); }
        finally { Shizuku.removeBinderReceivedListener(listener); }
        assertEquals(PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        try (Binding binding = new Binding(context)) {
            JSONObject result = new JSONObject(binding.device().diagnostics());
            assertEquals(2000, result.getInt("uid"));
            assertEquals(PrivilegedDeviceService.FIXTURE, result.getString("apk_package"));
            assertEquals(PrivilegedDeviceService.FIXTURE, result.getString("data_package"));
        }
    }
    private static final class Binding implements AutoCloseable {
        final Shizuku.UserServiceArgs args;
        final CountDownLatch connected = new CountDownLatch(1), disconnected = new CountDownLatch(1);
        final AtomicReference<IPrivilegedDeviceService> current = new AtomicReference<>();
        final ServiceConnection connection = new ServiceConnection() {
            public void onServiceConnected(ComponentName name, IBinder binder) {
                current.set(IPrivilegedDeviceService.Stub.asInterface(binder)); connected.countDown();
            }
            public void onServiceDisconnected(ComponentName name) { current.set(null); disconnected.countDown(); }
        };
        Binding(Context context) throws Exception {
            args = new Shizuku.UserServiceArgs(new ComponentName(context, FixtureInstallerService.class))
                .daemon(false).processNameSuffix("installerfixture")
                .tag("hokace-installer-fixture-" + UUID.randomUUID()).version(1);
            Shizuku.bindUserService(args, connection);
            assertTrue("Fixture installer service unavailable", connected.await(20, TimeUnit.SECONDS));
        }
        IPrivilegedDeviceService device() { return java.util.Objects.requireNonNull(current.get()); }
        public void close() { try { Shizuku.unbindUserService(args, connection, true); } catch (Exception ignored) { } }
    }
    private static JSONObject copy(IPrivilegedDeviceService device, File target) throws Exception {
        try (ParcelFileDescriptor output = ParcelFileDescriptor.open(target, ParcelFileDescriptor.MODE_CREATE |
                ParcelFileDescriptor.MODE_WRITE_ONLY | ParcelFileDescriptor.MODE_TRUNCATE)) {
            JSONObject result = new JSONObject(device.copyGameApk(output));
            assertEquals(target.length(), result.getLong("bytes"));
            assertEquals(ApkIdentity.Companion.digest(target), result.getString("sha256"));
            return result;
        }
    }
    private static String install(IPrivilegedDeviceService device, File source) throws Exception {
        try (ParcelFileDescriptor input = ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY)) {
            return device.installFirstSetupGame(input, source.length());
        }
    }
    @Test public void testFixtureServiceDeathAndFailedInstallRestoreExactSource() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try {
            assertTrue(available.await(15, TimeUnit.SECONDS));
            assertEquals(PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        } finally { Shizuku.removeBinderReceivedListener(listener); }
        File root = new File(context.getFilesDir(), "installer-fixture-probes/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        File source = new File(root, "original-fixture.apk");
        Binding first = null, recovery = null;
        boolean sourceVerified = false;
        String expected = null;
        Throwable failure = null;
        try {
            first = new Binding(context);
            IPrivilegedDeviceService device = first.device();
            JSONObject info = new JSONObject(device.gameApkInfo());
            assertEquals(PrivilegedDeviceService.FIXTURE, info.getString("package"));
            assertTrue(info.getLong("bytes") > 0 && info.getLong("bytes") < 16 * 1024 * 1024);
            expected = copy(device, source).getString("sha256");
            assertEquals(PrivilegedDeviceService.FIXTURE, java.util.Objects.requireNonNull(context.getPackageManager()
                .getPackageArchiveInfo(source.getPath(), PackageManager.GET_SIGNING_CERTIFICATES)).packageName);
            assertTrue(source.setReadOnly()); sourceVerified = true;
            device.validateFirstSetupSource(expected);
            device.forceStopGame();
            device.removeGameForFirstSetup(expected);
            assertTrue(device.firstSetupGameAbsent());
            IPrivilegedDeviceService stale = device;
            try { stale.destroy(); } catch (Exception expectedDeath) { }
            assertTrue("UserService death callback missing", first.disconnected.await(10, TimeUnit.SECONDS));
            try { stale.diagnostics(); fail("Dead service accepted work"); } catch (Exception expectedDeath) { }
            first.close(); first = null;
            recovery = new Binding(context); device = recovery.device();
            assertTrue(device.firstSetupGameAbsent());
            File truncated = new File(root, "truncated.apk");
            try (FileOutputStream output = new FileOutputStream(truncated)) {
                output.write(new byte[512]); output.getFD().sync();
            }
            try (ParcelFileDescriptor input = ParcelFileDescriptor.open(truncated, ParcelFileDescriptor.MODE_READ_ONLY)) {
                try { device.installFirstSetupGame(input, source.length()); fail("Invalid APK stream installed"); }
                catch (Exception expectedFailure) { }
            }
            assertTrue("Failed installation left a package", device.firstSetupGameAbsent());
            JSONObject installed = new JSONObject(install(device, source));
            assertEquals(source.length(), installed.getLong("bytes"));
            assertFalse(device.firstSetupGameAbsent());
            JSONObject restored = copy(device, new File(root, "restored-fixture.apk"));
            assertEquals(expected, restored.getString("sha256"));
            assertEquals(PrivilegedDeviceService.FIXTURE, new JSONObject(device.gameApkInfo()).getString("package"));
            byte[] payload = new byte[] {0, 26, -1, 42}; assertArrayEquals(payload, device.probeFixture(payload));
            JSONObject receipt = new JSONObject().put("fixture", PrivilegedDeviceService.FIXTURE)
                .put("source_sha256", expected).put("restored_sha256", restored.getString("sha256"))
                .put("source_bytes", source.length()).put("service_death", true).put("invalid_install_refused", true)
                .put("install", installed).put("game_mutated", false);
            try (FileOutputStream output = new FileOutputStream(new File(root, "receipt.json"))) {
                output.write(receipt.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
            }
            android.util.Log.i("HokAceProbe", "PASS: fixture installer recovery " + root.getName() + " " + receipt);
        } catch (Exception | AssertionError error) {
            failure = error; throw error;
        } finally {
            // Best-effort fixture restoration even when an earlier assertion/installer step failed.
            try {
                if (sourceVerified) {
                    if (recovery == null || recovery.current.get() == null) recovery = new Binding(context);
                    IPrivilegedDeviceService device = recovery.device();
                    if (device.firstSetupGameAbsent()) install(device, source);
                    assertEquals(expected, copy(device, new File(root, "final-fixture.apk")).getString("sha256"));
                }
            } catch (Exception | AssertionError restoreError) {
                if (failure != null) failure.addSuppressed(restoreError); else throw restoreError;
            } finally {
                if (first != null) first.close();
                if (recovery != null) recovery.close();
            }
        }
    }
}
