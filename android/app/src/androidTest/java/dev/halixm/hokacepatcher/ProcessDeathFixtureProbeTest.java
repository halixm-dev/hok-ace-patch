package dev.halixm.hokacepatcher;

import android.content.ComponentName;
import android.content.Context;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import android.util.AtomicFile;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import org.junit.Test;
import rikka.shizuku.Shizuku;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Two host-controlled phases: actual app death, real fixed-fixture transport, no APK installation. */
public final class ProcessDeathFixtureProbeTest {
    private static final String ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
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
                assertTrue("Oversized fixture diagnostic", output.size() <= 16384);
            }
            return output.toString("UTF-8");
        }
    }
    private static void save(File path, byte[] bytes) throws Exception {
        DurableFiles.INSTANCE.createDirectories(path.getParentFile());
        AtomicFile atomic = new AtomicFile(path);
        FileOutputStream output = atomic.startWrite();
        try {
            output.write(bytes); output.getFD().sync(); atomic.finishWrite(output);
            DurableFiles.INSTANCE.syncDirectory(path.getParentFile());
        } catch (Throwable error) { atomic.failWrite(output); throw error; }
    }
    private static void save(File path, JSONObject value) throws Exception {
        save(path, value.toString().getBytes(StandardCharsets.UTF_8));
    }
    private static JSONObject json(File path) throws Exception {
        return new JSONObject(new String(new AtomicFile(path).readFully(), StandardCharsets.UTF_8));
    }
    private static JSONObject validate(IPrivilegedDeviceService device, File manifest) throws Exception {
        try (ParcelFileDescriptor source = ParcelFileDescriptor.open(manifest, ParcelFileDescriptor.MODE_READ_ONLY)) {
            return new JSONObject(device.validateGameSnapshot(source));
        }
    }
    private static SessionJournal applying(File parent) throws Exception {
        SessionJournal journal = SessionJournal.Companion.create(parent, ID, ID);
        journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
        journal.outcome(PatchPhase.NORMAL_RESTORED_FOR_BUILD, new JSONObject());
        journal.outcome(PatchPhase.BUILDING, new JSONObject());
        journal.outcome(PatchPhase.STAGED, new JSONObject());
        journal.outcome(PatchPhase.APPLY_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.APPLYING, new JSONObject());
        return journal;
    }

    @Test public void testHostControlledProcessDeathAndRestore() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String phase = InstrumentationRegistry.getArguments().getString("probePhase", "");
        String caseId = InstrumentationRegistry.getArguments().getString("probeCase", "");
        org.junit.Assume.assumeFalse("Use the host harness for this two-phase process-death diagnostic",
            phase.isEmpty() && caseId.isEmpty());
        assertEquals(UUID.fromString(caseId).toString(), caseId);
        assertTrue(phase.equals("arm") || phase.equals("recover"));
        File root = new File(context.getFilesDir(), "process-death-fixture-probes/" + caseId);
        if (phase.equals("arm")) assertFalse("Probe already exists", root.exists());
        else assertTrue("Missing armed receipt", new File(root, "armed.json").isFile());

        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try {
            assertTrue("Shizuku stopped", available.await(15, TimeUnit.SECONDS));
            assertEquals(PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        } finally { Shizuku.removeBinderReceivedListener(listener); }
        CountDownLatch connected = new CountDownLatch(1);
        AtomicReference<IPrivilegedDeviceService> service = new AtomicReference<>();
        Shizuku.UserServiceArgs args = new Shizuku.UserServiceArgs(new ComponentName(context, FixtureFileService.class))
            .daemon(false).processNameSuffix("deathfixture").tag("hokace-death-fixture-" + UUID.randomUUID()).version(7);
        ServiceConnection connection = new ServiceConnection() {
            @Override public void onServiceConnected(ComponentName name, IBinder binder) {
                service.set(IPrivilegedDeviceService.Stub.asInterface(binder)); connected.countDown();
            }
            @Override public void onServiceDisconnected(ComponentName name) { service.set(null); }
        };
        Shizuku.bindUserService(args, connection);
        try {
            assertTrue("Fixture service not connected", connected.await(20, TimeUnit.SECONDS));
            IPrivilegedDeviceService device = service.get();
            assertEquals("io.github.hokace.fixture", new JSONObject(device.diagnostics()).getString("data_package"));
            if (phase.equals("arm")) {
                assertEquals("fixture-created", shell("run-as io.github.hokace.fixture sh -c '" +
                    "set -e; [ ! -e files/QtsVFSCache ] && [ ! -e files/hokace-process-probe-owner ] || exit 1; " +
                    "mkdir -p files; " +
                    "printf " + caseId + " > files/hokace-process-probe-owner; " +
                    "sync files/hokace-process-probe-owner; sync files; " +
                    "mkdir -p files/QtsVFSCache/packages/1 files/QtsVFSCache/Watchdog/src; " +
                    "printf original-index > files/QtsVFSCache/packages/1/1.db; " +
                    "printf original-shard > files/QtsVFSCache/packages/1/1_0.db; " +
                    "printf \"{\\\"version\\\":\\\"1.4.0.2\\\"}\" > files/QtsVFSCache/packages/1/1.info; " +
                    "printf original-watchdog > files/QtsVFSCache/Watchdog/PatchList.db; " +
                    "printf pending > files/QtsVFSCache/Watchdog/.pending; printf fixture-created'"));
                assertEquals(caseId, shell("run-as io.github.hokace.fixture cat files/hokace-process-probe-owner"));
                SessionJournal journal = applying(root);
                File archive = new File(root, "source.tar");
                try (ParcelFileDescriptor target = ParcelFileDescriptor.open(archive,
                    ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE | ParcelFileDescriptor.MODE_WRITE_ONLY)) {
                    JSONObject result = new JSONObject(device.snapshotGame(target, 1024 * 1024));
                    assertEquals(archive.length(), result.getLong("bytes"));
                    assertEquals(ApkIdentity.Companion.digest(archive), result.getString("sha256"));
                }
                File engine = EngineAssets.INSTANCE.prepare(context);
                if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
                Python.getInstance().getModule("android_bridge").callAttr("unpack_snapshot", engine.getPath(),
                    archive.getPath(), new File(journal.getDirectory(), "snapshot").getPath(), 1024 * 1024);
                assertEquals(5, validate(device, new File(journal.getDirectory(), "snapshot/manifest.json")).getInt("verified_files"));
                JSONObject hashes = new JSONObject();
                for (String name : new String[] {"1/1.db", "1/1_0.db"}) {
                    File out = new File(journal.getDirectory(), "out/" + name);
                    save(out, ("translated-" + name).getBytes(StandardCharsets.UTF_8));
                    hashes.put(name, ApkIdentity.Companion.digest(out));
                }
                save(new File(journal.getDirectory(), "staged-hashes.json"), hashes);
                JSONObject mixed = json(new File(journal.getDirectory(), "snapshot/manifest.json"));
                File translated = new File(journal.getDirectory(), "out/1/1.db");
                mixed.getJSONObject("files").put("packages/1/1.db", new JSONObject()
                    .put("bytes", translated.length()).put("sha256", ApkIdentity.Companion.digest(translated)));
                save(new File(root, "mixed-manifest.json"), mixed);
                IPrivilegedDeviceService delayed = (IPrivilegedDeviceService) java.lang.reflect.Proxy.newProxyInstance(
                    getClass().getClassLoader(), new Class<?>[] { IPrivilegedDeviceService.class }, (proxy, method, arguments) -> {
                        Object result;
                        try { result = method.invoke(device, arguments); }
                        catch (InvocationTargetException error) { throw error.getCause(); }
                        if (method.getName().equals("writeGameFile")) {
                            assertEquals("packages/1/1.db", arguments[1]);
                            assertEquals(5, validate(device, new File(root, "mixed-manifest.json")).getInt("verified_files"));
                            assertTrue(journal.getDirtyPackages()); assertTrue(journal.getHasMutationIntent());
                            save(new File(root, "armed.json"), new JSONObject().put("schema", 1).put("case", caseId)
                                .put("pid", android.os.Process.myPid()).put("session", journal.getId())
                                .put("boundary", "index-renamed-before-acknowledgement").put("journal", journal.snapshot()));
                            long deadline = android.os.SystemClock.elapsedRealtime() + 120000;
                            while (android.os.SystemClock.elapsedRealtime() < deadline) Thread.sleep(250);
                            throw new IllegalStateException("Host did not kill the armed app within 120 seconds; use recovery phase");
                        }
                        return result;
                    });
                new GameFileTransaction(journal, delayed).write("packages/1/1.db", translated, hashes.getString("1/1.db"), false);
                fail("Armed process should have been killed");
            } else {
                JSONObject armed = json(new File(root, "armed.json"));
                assertEquals(caseId, armed.getString("case"));
                assertNotEquals("Process was not restarted", armed.getInt("pid"), android.os.Process.myPid());
                assertEquals(caseId, shell("run-as io.github.hokace.fixture cat files/hokace-process-probe-owner"));
                assertEquals(5, validate(device, new File(root, "mixed-manifest.json")).getInt("verified_files"));
                SessionJournal journal = SessionJournal.Companion.load(new File(root, armed.getString("session")));
                assertTrue(journal.getDirtyPackages()); assertTrue(journal.getHasMutationIntent());
                assertFalse(journal.snapshot().getBoolean("normal_verified"));
                assertEquals("write_file", journal.snapshot().getJSONObject("mutation_intent").getString("operation"));
                new GameFileTransaction(journal, device).verifyOriginals();
                journal.recoveryRequired("Host killed the app after index rename before acknowledgement");
                journal.outcome(PatchPhase.RESTORING, new JSONObject());
                new GameFileTransaction(journal, device).rollback();
                assertEquals(5, validate(device, new File(journal.getDirectory(), "snapshot/manifest.json")).getInt("verified_files"));
                assertEquals("fixture-directory", shell("run-as io.github.hokace.fixture sh -c '" +
                    "[ -d files/QtsVFSCache/Watchdog/src ] && [ ! -L files/QtsVFSCache/Watchdog/src ] && printf fixture-directory'"));
                assertFalse(journal.getDirtyPackages()); assertFalse(journal.getHasMutationIntent());
                try { journal.outcome(PatchPhase.COMPLETE, new JSONObject()); fail("APK verification was bypassed"); }
                catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("normal game APK")); }
                save(new File(root, "recovered.json"), new JSONObject().put("schema", 1).put("case", caseId)
                    .put("pid", android.os.Process.myPid()).put("original_pid", armed.getInt("pid"))
                    .put("verified_files", 5).put("apk_install_tested", false).put("journal", journal.snapshot()));
                assertEquals("fixture-clean", shell("run-as io.github.hokace.fixture sh -c '" +
                    "[ \"$(cat files/hokace-process-probe-owner)\" = \"" + caseId + "\" ] || exit 1; " +
                    "rm -rf files/QtsVFSCache; rm files/hokace-process-probe-owner; printf fixture-clean'"));
            }
        } finally { Shizuku.unbindUserService(args, connection, true); }
    }
}
