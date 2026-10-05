package dev.halixm.hokacepatcher;

import android.content.ComponentName;
import android.content.Context;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.content.pm.PackageInfo;
import android.content.pm.ApplicationInfo;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import rikka.shizuku.Shizuku;
import java.security.SecureRandom;
import java.security.MessageDigest;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Fixed-target shell and scratch-fixture checks; does not write the live game's data. */
@RunWith(AndroidJUnit4.class)
public final class ShizukuProbeTest {
    @Test public void testShellAndFixtureBoundary() throws Exception {
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try {
            assertTrue("Start Shizuku first", available.await(15, TimeUnit.SECONDS));
            assertEquals("Authorize HOK ACE feasibility in Shizuku first",
                PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        } finally { Shizuku.removeBinderReceivedListener(listener); }
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        Shizuku.UserServiceArgs args = new Shizuku.UserServiceArgs(
            new ComponentName(context, PrivilegedDeviceService.class))
            .daemon(false).processNameSuffix("probe").tag("hokace-instrumentation").version(PrivilegedDeviceService.PROTOCOL_VERSION);
        CountDownLatch connected = new CountDownLatch(1);
        CountDownLatch disconnected = new CountDownLatch(1);
        AtomicReference<IPrivilegedDeviceService> service = new AtomicReference<>();
        ServiceConnection connection = new ServiceConnection() {
            @Override public void onServiceConnected(ComponentName name, IBinder binder) {
                service.set(IPrivilegedDeviceService.Stub.asInterface(binder));
                connected.countDown();
            }
            @Override public void onServiceDisconnected(ComponentName name) {
                service.set(null);
                disconnected.countDown();
            }
        };
        Shizuku.bindUserService(args, connection);
        try {
            assertTrue("UserService did not connect", connected.await(20, TimeUnit.SECONDS));
            String diagnostics = service.get().diagnostics();
            assertEquals(2000, new JSONObject(diagnostics).getInt("uid"));
            android.util.Log.i("HokAceProbe", diagnostics);
            android.util.Log.i("HokAceProbe", service.get().gameApkInfo());
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeFirstSetupReadOnly"))) {
                assertFalse("Installed game incorrectly reported absent", service.get().firstSetupGameAbsent());
                String sourceHash = InstrumentationRegistry.getArguments().getString("expectedApkSha256");
                assertNotNull(sourceHash);
                service.get().validateFirstSetupSource(sourceHash);
                try { service.get().validateFirstSetupSource("0000000000000000000000000000000000000000000000000000000000000000");
                    fail("Changed source identity accepted"); }
                catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("changed before first setup")); }
                File recovery = new RecoveryStore(context).normal(sourceHash);
                try (ParcelFileDescriptor descriptor = ParcelFileDescriptor.open(recovery, ParcelFileDescriptor.MODE_READ_ONLY)) {
                    try { service.get().installFirstSetupGame(descriptor, recovery.length()); fail("First setup replaced an installed game"); }
                    catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("cannot replace an installed game")); }
                }
                try { service.get().removeGameForFirstSetup("invalid"); fail("Invalid removal identity accepted"); }
                catch (IllegalArgumentException expected) { }
                android.util.Log.i("HokAceProbe", "PASS: source/profile preflight, stale source and invalid removal refusal, existing-game install refusal; no game mutation");
            }
            byte[] data = new byte[4096];
            new SecureRandom().nextBytes(data);
            assertArrayEquals(data, service.get().probeFixture(data));
            android.util.Log.i("HokAceProbe", "PASS: fixture binary round-trip");
            android.util.Log.i("HokAceProbe", NormalRunAsProbe.INSTANCE.run());
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeRecoveryPipe"))) {
                String expected = InstrumentationRegistry.getArguments().getString("expectedApkSha256");
                assertNotNull(expected);
                new PatchCoordinator(context, service.get(), message -> {
                    android.util.Log.i("HokAceProbe", message);
                    return kotlin.Unit.INSTANCE;
                }).verifyRecoveryInstalled(expected);
                android.util.Log.i("HokAceProbe", "PASS: bounded recovery pipe hash and installed signer/manifest identity");
            }
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeApkStream"))) {
                File target = new File(context.getFilesDir(), "probe-stream.apk.partial");
                JSONObject info = new JSONObject(service.get().gameApkInfo());
                assertTrue("Not enough APK scratch space", context.getFilesDir().getUsableSpace()
                    > info.getLong("bytes") + 256L * 1024 * 1024);
                try {
                    JSONObject result;
                    try (ParcelFileDescriptor fd = ParcelFileDescriptor.open(target,
                        ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE |
                        ParcelFileDescriptor.MODE_WRITE_ONLY)) {
                        result = new JSONObject(service.get().copyGameApk(fd));
                    }
                    MessageDigest hash = MessageDigest.getInstance("SHA-256");
                    try (FileInputStream input = new FileInputStream(target)) {
                        byte[] buffer = new byte[1024 * 1024];
                        int count;
                        while ((count = input.read(buffer)) >= 0) hash.update(buffer, 0, count);
                    }
                    StringBuilder hex = new StringBuilder();
                    for (byte value : hash.digest()) hex.append(String.format("%02x", value & 255));
                    assertEquals(info.getLong("bytes"), target.length());
                    assertEquals(result.getLong("bytes"), target.length());
                    assertEquals(result.getString("sha256"), hex.toString());
                    String expected = InstrumentationRegistry.getArguments().getString("expectedApkSha256");
                    if (expected != null) assertEquals(expected, hex.toString());
                    android.util.Log.i("HokAceProbe", "PASS: APK descriptor stream " + result);
                } finally { assertTrue("Could not remove probe APK", !target.exists() || target.delete()); }
            }
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeFixtureInstall"))) {
                android.util.Log.i("HokAceProbe", "PASS: fixture install session " + service.get().reinstallFixture(false));
                assertArrayEquals(data, service.get().probeFixture(data));
            }
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeFixtureAbort"))) {
                JSONObject result = new JSONObject(service.get().reinstallFixture(true));
                assertTrue(result.getBoolean("abandoned"));
                assertTrue(result.getBoolean("commit_rejected"));
                assertArrayEquals(data, service.get().probeFixture(data));
                android.util.Log.i("HokAceProbe", "PASS: fixture abandon preserves installed APK " + result);
            }
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeForceStop"))) {
                service.get().forceStopGame();
                android.util.Log.i("HokAceProbe", "PASS: fixed game force-stop command");
            }
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeGameCycle"))) {
                probeGameCycle(context, service.get());
            }
            if ("true".equals(InstrumentationRegistry.getArguments().getString("probeBinderLoss"))) {
                IPrivilegedDeviceService retained = service.get();
                try { retained.destroy(); } catch (android.os.RemoteException expected) { }
                assertTrue("UserService death was not delivered", disconnected.await(15, TimeUnit.SECONDS));
                assertNull("Dead service remained connected", service.get());
                try {
                    retained.diagnostics();
                    fail("Dead UserService accepted an operation");
                } catch (android.os.RemoteException expected) { }
                android.util.Log.i("HokAceProbe", "PASS: UserService binder loss, stale operation rejected");
            }
        } finally { Shizuku.unbindUserService(args, connection, true); }
    }

    private static String digest(byte[] data) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(data))
            result.append(String.format("%02x", value & 255));
        return result.toString();
    }

    private static String fileDigest(File file) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) hash.update(buffer, 0, count);
        }
        StringBuilder result = new StringBuilder();
        for (byte value : hash.digest()) result.append(String.format("%02x", value & 255));
        return result.toString();
    }

    private static void verifyApk(Context context, File file, boolean debug, String hash,
                                   String certificate) throws Exception {
        assertEquals("APK input hash differs", hash, fileDigest(file));
        PackageInfo info = context.getPackageManager().getPackageArchiveInfo(file.getPath(),
            PackageManager.GET_SIGNING_CERTIFICATES);
        assertNotNull("APK manifest could not be parsed", info);
        assertEquals(PrivilegedDeviceService.GAME, info.packageName);
        assertEquals(debug, (info.applicationInfo.flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0);
        assertNotNull(info.signingInfo);
        assertEquals(1, info.signingInfo.getApkContentsSigners().length);
        assertEquals(certificate, digest(info.signingInfo.getApkContentsSigners()[0].toByteArray()));
    }

    private static void install(IPrivilegedDeviceService service, File source) throws Exception {
        try (ParcelFileDescriptor fd = ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY)) {
            android.util.Log.i("HokAceProbe", service.replaceGameApk(fd, source.length()));
        }
    }

    /** Opt-in development cycle only. Never enables a live data/package patch. */
    private static void probeGameCycle(Context context, IPrivilegedDeviceService service) throws Exception {
        android.os.Bundle arguments = InstrumentationRegistry.getArguments();
        String name = arguments.getString("gameCycleSession");
        assertNotNull("Explicit game-cycle scratch session required", name);
        assertTrue(name.matches("[a-zA-Z0-9-]{1,64}"));
        File root = new File(context.getFilesDir(), "scratch/" + name);
        File normal = new File(root, "normal.apk"), access = new File(root, "access.apk");
        String normalHash = arguments.getString("expectedApkSha256");
        String accessHash = arguments.getString("expectedAccessSha256");
        String certificate = arguments.getString("expectedCertSha256");
        assertNotNull(normalHash); assertNotNull(accessHash); assertNotNull(certificate);
        assertTrue(normalHash.matches("[0-9a-f]{64}"));
        assertTrue(accessHash.matches("[0-9a-f]{64}"));
        assertTrue(certificate.matches("[0-9a-f]{64}"));
        verifyApk(context, normal, false, normalHash, certificate);
        verifyApk(context, access, true, accessHash, certificate);
        PackageInfo normalInfo = context.getPackageManager().getPackageArchiveInfo(normal.getPath(), 0);
        PackageInfo accessInfo = context.getPackageManager().getPackageArchiveInfo(access.getPath(), 0);
        assertEquals(normalInfo.getLongVersionCode(), accessInfo.getLongVersionCode());
        assertTrue("Need APK installer and read-back headroom",
            context.getFilesDir().getUsableSpace() > normal.length() * 2 + 512L * 1024 * 1024);
        PackageInfo current = context.getPackageManager().getPackageInfo(PrivilegedDeviceService.GAME,
            PackageManager.GET_SIGNING_CERTIFICATES);
        assertEquals(certificate, digest(current.signingInfo.getApkContentsSigners()[0].toByteArray()));
        assertEquals("Start with a normal installed game", 0,
            current.applicationInfo.flags & ApplicationInfo.FLAG_DEBUGGABLE);
        File before = new File(root, "current.apk.partial");
        try {
            try (ParcelFileDescriptor fd = ParcelFileDescriptor.open(before, ParcelFileDescriptor.MODE_CREATE |
                ParcelFileDescriptor.MODE_TRUNCATE | ParcelFileDescriptor.MODE_WRITE_ONLY)) {
                assertEquals("Current game differs from retained recovery APK", normalHash,
                    new JSONObject(service.copyGameApk(fd)).getString("sha256"));
            }
            assertEquals(normalHash, fileDigest(before));
        } finally { assertTrue(!before.exists() || before.delete()); }
        File info = new File(root, "game/WXQ_Data/Package/builtin/1/1.info");
        String expectedInfo = new String(java.nio.file.Files.readAllBytes(info.toPath()), StandardCharsets.UTF_8);
        byte[] payload = new byte[4096];
        new SecureRandom().nextBytes(payload);
        service.forceStopGame();
        File journal = new File(root, "game-cycle.log");
        java.nio.file.Files.write(journal.toPath(),
            "Validated both APKs; normal recovery retained\n".getBytes(StandardCharsets.UTF_8));
        try {
            install(service, access);
            java.nio.file.Files.write(journal.toPath(), "Access APK installed\n".getBytes(StandardCharsets.UTF_8),
                java.nio.file.StandardOpenOption.APPEND);
            JSONObject result = new JSONObject(service.probeGame(payload));
            assertEquals(expectedInfo, result.getString("data_info"));
            assertEquals(payload.length, result.getInt("roundtrip_bytes"));
            android.util.Log.i("HokAceProbe", "PASS: game UID scratch probe " + result);
        } finally {
            // This diagnostic has no durable recovery coordinator: retain the verified PC recovery
            // APK and USB connection. Binder/process loss requires the documented PC restore.
            install(service, normal);
            java.nio.file.Files.write(journal.toPath(), "Normal APK restored\n".getBytes(StandardCharsets.UTF_8),
                java.nio.file.StandardOpenOption.APPEND);
            PackageInfo restored = context.getPackageManager().getPackageInfo(PrivilegedDeviceService.GAME,
                PackageManager.GET_SIGNING_CERTIFICATES);
            assertEquals(0, restored.applicationInfo.flags & ApplicationInfo.FLAG_DEBUGGABLE);
            assertEquals(certificate, digest(restored.signingInfo.getApkContentsSigners()[0].toByteArray()));
            File readback = new File(root, "restored.apk.partial");
            try {
                try (ParcelFileDescriptor fd = ParcelFileDescriptor.open(readback, ParcelFileDescriptor.MODE_CREATE |
                    ParcelFileDescriptor.MODE_TRUNCATE | ParcelFileDescriptor.MODE_WRITE_ONLY)) {
                    JSONObject result = new JSONObject(service.copyGameApk(fd));
                    assertEquals(normalHash, result.getString("sha256"));
                }
                assertEquals(normalHash, fileDigest(readback));
            } finally { assertTrue(!readback.exists() || readback.delete()); }
            android.util.Log.i("HokAceProbe", "PASS: normal APK restored, hash/signature/debug flag verified");
        }
    }
}
