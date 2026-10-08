package dev.halixm.hokacepatcher;

import android.content.ComponentName;
import android.content.Context;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import rikka.shizuku.Shizuku;
import static org.junit.Assert.*;

/** Real production run-as/tar/rename/fsync commands, directed only at the disposable debug fixture. */
@RunWith(AndroidJUnit4.class)
public final class FixtureFileProbeTest {
    private static String shell(String command) throws Exception {
        ParcelFileDescriptor[] pipe = InstrumentationRegistry.getInstrumentation().getUiAutomation()
            .executeShellCommandRw("/system/bin/sh");
        try (ParcelFileDescriptor.AutoCloseOutputStream input = new ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])) {
            input.write((command + "\n").getBytes(StandardCharsets.UTF_8));
        }
        try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
            pipe[0])) {
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) >= 0) {
                result.write(buffer, 0, count);
                if (result.size() > 16384) throw new IllegalStateException("Oversized fixture diagnostic");
            }
            return result.toString("UTF-8");
        }
    }
    private static String hash(byte[] bytes) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte part : MessageDigest.getInstance("SHA-256").digest(bytes)) result.append(String.format("%02x", part & 255));
        return result.toString();
    }
    private static ParcelFileDescriptor read(File file) throws Exception {
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }
    private static void write(IPrivilegedDeviceService device, String id, String relative, File file) throws Exception {
        JSONObject result = new JSONObject(device.writeGameFile(id, relative, read(file), file.length(), ApkIdentity.Companion.digest(file)));
        assertEquals(ApkIdentity.Companion.digest(file), result.getString("sha256"));
    }
    @Test public void testActualSnapshotWriteAndWatchdogRestore() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try {
            assertTrue(available.await(15, TimeUnit.SECONDS));
            assertEquals(PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        } finally { Shizuku.removeBinderReceivedListener(listener); }
        // Literal fixture package and literal private root: no game path or arbitrary shell endpoint.
        String setup = shell("run-as io.github.hokace.fixture sh -c '" +
            "[ ! -e files/QtsVFSCache ] || exit 1; " +
            "mkdir -p files/QtsVFSCache/packages/1 files/QtsVFSCache/Watchdog/src; " +
            "printf index > files/QtsVFSCache/packages/1/1.db; " +
            "printf shard > files/QtsVFSCache/packages/1/1_0.db; " +
            "printf \"{\\\"version\\\":\\\"1.4.0.2\\\"}\" > files/QtsVFSCache/packages/1/1.info; " +
            "printf watchdog > files/QtsVFSCache/Watchdog/PatchList.db; " +
            "printf pending > files/QtsVFSCache/Watchdog/.pending; printf fixture-ok'");
        assertEquals("fixture-ok", setup);
        Shizuku.UserServiceArgs args = new Shizuku.UserServiceArgs(new ComponentName(context, FixtureFileService.class))
            .daemon(false).processNameSuffix("filefixture").tag("hokace-file-fixture").version(2);
        CountDownLatch connected = new CountDownLatch(1);
        AtomicReference<IPrivilegedDeviceService> service = new AtomicReference<>();
        ServiceConnection connection = new ServiceConnection() {
            @Override public void onServiceConnected(ComponentName name, IBinder binder) {
                service.set(IPrivilegedDeviceService.Stub.asInterface(binder)); connected.countDown();
            }
            @Override public void onServiceDisconnected(ComponentName name) { service.set(null); }
        };
        Shizuku.bindUserService(args, connection);
        try {
            assertTrue(connected.await(20, TimeUnit.SECONDS));
            IPrivilegedDeviceService device = service.get();
            String id = UUID.randomUUID().toString();
            File root = new File(context.getFilesDir(), "file-fixture-probes/" + id);
            assertTrue(root.mkdirs());
            File archive = new File(root, "source.tar");
            JSONObject streamed = new JSONObject(device.snapshotGame(ParcelFileDescriptor.open(archive,
                ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE | ParcelFileDescriptor.MODE_WRITE_ONLY), 1024 * 1024));
            assertEquals(archive.length(), streamed.getLong("bytes"));
            assertEquals(ApkIdentity.Companion.digest(archive), streamed.getString("sha256"));
            File engine = EngineAssets.INSTANCE.prepare(context);
            if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
            File snapshot = new File(root, "snapshot");
            Python.getInstance().getModule("android_bridge").callAttr("unpack_snapshot",
                engine.getPath(), archive.getPath(), snapshot.getPath(), 1024 * 1024);
            File manifest = new File(snapshot, "manifest.json");
            assertEquals(5, new JSONObject(device.validateGameSnapshot(read(manifest))).getInt("verified_files"));
            byte[] payload = new byte[4096]; new java.security.SecureRandom().nextBytes(payload);
            File staged = new File(root, "staged.db");
            try (FileOutputStream output = new FileOutputStream(staged)) { output.write(payload); output.getFD().sync(); }
            write(device, id, "packages/1/1.db", staged);
            try { device.validateGameSnapshot(read(manifest)); fail("Changed layer accepted"); }
            catch (Exception expected) { }
            try { device.writeGameFile(id, "packages/1/1.db", read(staged), payload.length, hash("wrong".getBytes(StandardCharsets.UTF_8))); fail("Wrong hash accepted"); }
            catch (Exception expected) { }
            // A dangling temporary symlink must be refused before cat can follow it.
            assertEquals("fixture-ok", shell("run-as io.github.hokace.fixture sh -c 'ln -s missing " +
                "files/QtsVFSCache/packages/1/.1.db.hok-" + id + ".tmp; printf fixture-ok'"));
            try { write(device, id, "packages/1/1.db", staged); fail("Dangling temporary symlink accepted"); }
            catch (Exception expected) { }
            device.clearSessionTemp(id, "packages/1/1.db");
            write(device, id, "packages/1/1.db", new File(snapshot, "packages/1/1.db"));
            device.clearGameWatchdog();
            assertEquals("fixture-ok", shell("run-as io.github.hokace.fixture sh -c '" +
                "[ ! -e files/QtsVFSCache/Watchdog/.pending ] && printf fixture-ok'"));
            device.restoreWatchdogDirectory("Watchdog/src");
            write(device, id, "Watchdog/PatchList.db", new File(snapshot, "Watchdog/PatchList.db"));
            write(device, id, "Watchdog/.pending", new File(snapshot, "Watchdog/.pending"));
            assertEquals(5, new JSONObject(device.validateGameSnapshot(read(manifest))).getInt("verified_files"));
            // Kill the lock-owning shell while its child remains: a replacement writer must
            // stay blocked until the orphan exits, avoiding overlap after service/process loss.
            ParcelFileDescriptor[] holder = InstrumentationRegistry.getInstrumentation().getUiAutomation()
                .executeShellCommandRw("run-as io.github.hokace.fixture /system/bin/sh");
            java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newSingleThreadExecutor();
            String parent = null, child = null;
            try (ParcelFileDescriptor.AutoCloseInputStream held = new ParcelFileDescriptor.AutoCloseInputStream(holder[0])) {
                try (ParcelFileDescriptor.AutoCloseOutputStream input = new ParcelFileDescriptor.AutoCloseOutputStream(holder[1])) {
                    input.write((GameFileLock.INSTANCE.script("sleep 30 & child=$!; printf '%s %s\\n' \"$$\" \"$child\"; wait $child") + "\n")
                        .getBytes(StandardCharsets.UTF_8));
                }
                String line = new java.io.BufferedReader(new java.io.InputStreamReader(held, StandardCharsets.UTF_8)).readLine();
                assertNotNull("Lock holder did not start", line);
                String[] pids = line.split(" "); assertEquals(line, 2, pids.length);
                parent = pids[0]; child = pids[1];
                assertTrue(parent.matches("[0-9]{1,8}") && child.matches("[0-9]{1,8}"));
                java.util.concurrent.Future<?> pending = pool.submit(() -> {
                    try { write(device, id, "packages/1/1.db", new File(snapshot, "packages/1/1.db")); }
                    catch (Exception error) { throw new RuntimeException(error); }
                });
                try { pending.get(300, TimeUnit.MILLISECONDS); fail("Writer bypassed live lock"); }
                catch (java.util.concurrent.TimeoutException expected) { }
                shell("run-as io.github.hokace.fixture kill -9 " + parent);
                parent = null;
                try { pending.get(300, TimeUnit.MILLISECONDS); fail("Writer bypassed orphan child lock"); }
                catch (java.util.concurrent.TimeoutException expected) { }
                shell("run-as io.github.hokace.fixture kill -9 " + child);
                child = null;
                pending.get(30, TimeUnit.SECONDS);
            } finally {
                if (parent != null) shell("run-as io.github.hokace.fixture kill -9 " + parent);
                if (child != null) shell("run-as io.github.hokace.fixture kill -9 " + child);
                pool.shutdownNow();
            }
            assertEquals(5, new JSONObject(device.validateGameSnapshot(read(manifest))).getInt("verified_files"));
            android.util.Log.i("HokAceProbe", "PASS: actual fixture snapshot/hash refusal/atomic write/temp symlink refusal/Watchdog restore");
            android.util.Log.i("HokAceProbe", "PASS: actual lock survives shell death until orphan child exits");
        } finally {
            Shizuku.unbindUserService(args, connection, true);
            assertEquals("fixture-clean", shell("run-as io.github.hokace.fixture sh -c '" +
                "rm -rf files/QtsVFSCache; printf fixture-clean'"));
        }
    }
}
