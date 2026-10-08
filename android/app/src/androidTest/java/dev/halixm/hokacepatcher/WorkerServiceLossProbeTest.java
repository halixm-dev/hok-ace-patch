package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.ParcelFileDescriptor;
import android.util.AtomicFile;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import rikka.shizuku.Shizuku;
import static org.junit.Assert.*;

/** Kill only the foreground worker's shell UserService during a read-only normal-APK check. */
public final class WorkerServiceLossProbeTest {
    private static final String APP = "dev.halixm.hokacepatcher";
    private static final String NORMAL = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
    private void ready() throws Exception {
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try { assertTrue("Start Shizuku before this read-only probe", available.await(15, TimeUnit.SECONDS)); }
        finally { Shizuku.removeBinderReceivedListener(listener); }
        assertTrue(Shizuku.pingBinder());
        assertEquals("Authorize HOK ACE before this probe", PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
    }
    private String shell(String command) throws Exception {
        try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(command))) {
            ByteArrayOutputStream output = new ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) >= 0) {
                output.write(buffer, 0, count); assertTrue("Diagnostic output too large", output.size() <= 64 * 1024);
            }
            return output.toString("UTF-8");
        }
    }
    private int workerPid() throws Exception {
        int found = 0;
        for (String line : shell("ps -A -o PID,UID,NAME").split("\n")) {
            String[] fields = line.trim().split("\\s+");
            if (fields.length == 3 && fields[2].equals(APP + ":worker")) {
                assertEquals("Refuse to stop a non-shell process", "2000", fields[1]);
                assertEquals("Multiple worker services; refuse ambiguous target", 0, found);
                found = Integer.parseInt(fields[0]); assertTrue(found > 1);
            }
        }
        return found;
    }
    private JSONObject state(File path) throws Exception {
        return path.isFile() ? new JSONObject(new String(new AtomicFile(path).readFully(), StandardCharsets.UTF_8)) : null;
    }
    private JSONObject terminal(File path, long started) throws Exception {
        long deadline = System.currentTimeMillis() + 90000;
        while (System.currentTimeMillis() < deadline) {
            JSONObject value = state(path);
            if (value != null && value.optLong("updated_ms") >= started && !"running".equals(value.optString("status"))) return value;
            Thread.sleep(100);
        }
        throw new AssertionError("Foreground result missing or still running");
    }
    private void start(ActivityScenario<MainActivity> activity, JSONObject attempt) {
        activity.onActivity(current -> current.startForegroundService(new Intent(current, PatchWorkerService.class)
            .setAction("verify").putExtra("normal", NORMAL).putExtra("emergency", attempt.optString("id"))));
    }
    @Test public void testActualForegroundServiceLossKeepsIntentThenFreshVerificationResolves() throws Exception {
        ready();
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertFalse("Do not interrupt an existing foreground worker", shell("dumpsys activity services " + APP).contains(".PatchWorkerService"));
        assertEquals("Do not stop another owner", 0, workerPid());
        EmergencyRestoreStore restore = new EmergencyRestoreStore(context);
        assertNull("Existing emergency intent must remain untouched", restore.snapshot());
        JSONObject attempt = restore.begin(NORMAL);
        File resultPath = new File(context.getFilesDir(), "worker-state.json");
        File root = new File(context.getFilesDir(), "worker-service-loss-probes/" + UUID.randomUUID());
        DurableFiles.INSTANCE.createDirectories(root);
        JSONObject receipt = new JSONObject().put("scope", "read-only foreground verification and own UserService death")
            .put("normal", NORMAL).put("emergency_request", attempt.getString("id")).put("game_mutated", false);
        boolean resolved = false;
        shell("am start -W -n " + APP + "/.MainActivity");
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            long started = System.currentTimeMillis(); start(activity, attempt);
            int pid = 0; long deadline = started + 20000;
            while (System.currentTimeMillis() < deadline && (pid = workerPid()) == 0) Thread.sleep(20);
            assertTrue("Worker shell service missing; no process was killed", pid > 1);
            JSONObject running = state(resultPath);
            deadline = System.currentTimeMillis() + 10000;
            while (System.currentTimeMillis() < deadline && (running == null ||
                !"Checking the installed normal game app".equals(running.optString("progress")))) {
                if (running != null && running.optLong("updated_ms") >= started)
                    assertEquals("Worker stopped before its connected verification stage; no process killed", "running", running.optString("status"));
                Thread.sleep(20); running = state(resultPath);
            }
            assertNotNull(running); assertEquals("running", running.getString("status"));
            assertEquals("No connected verification stage observed; do not kill", "Checking the installed normal game app", running.getString("progress"));
            assertEquals("verify", running.getString("action")); assertTrue(running.getLong("updated_ms") >= started);
            assertEquals("Process identity changed; refuse kill", pid, workerPid());
            shell("kill -9 " + pid);
            receipt.put("killed_worker_pid", pid).put("connection_phase", "connected_verification").put("prekill_worker_result", running);
            JSONObject failed = terminal(resultPath, started);
            assertEquals(failed.toString(), "error", failed.getString("status"));
            assertEquals("verify", failed.getString("action"));
            assertFalse("Connection-loss explanation is blank", failed.getString("error").trim().isEmpty());
            assertEquals("verification_pending", restore.snapshot().getString("status"));
            assertEquals(attempt.getString("id"), restore.snapshot().getString("id"));
            receipt.put("lost_service_result", failed).put("intent_pending_after_loss", true);
            deadline = System.currentTimeMillis() + 15000;
            while (System.currentTimeMillis() < deadline && shell("dumpsys activity services " + APP).contains(".PatchWorkerService")) Thread.sleep(100);
            assertFalse("Failed foreground worker did not stop", shell("dumpsys activity services " + APP).contains(".PatchWorkerService"));
            started = System.currentTimeMillis(); start(activity, attempt);
            JSONObject verified = terminal(resultPath, started);
            assertEquals(verified.toString(), "verified", verified.getString("status"));
            assertEquals("apk_verified", restore.snapshot().getString("status"));
            resolved = true;
            receipt.put("retry_result", verified).put("independent_normal_verified", true);
        } finally {
            receipt.put("resolved", resolved);
            File path = new File(root, "receipt.json");
            try (FileOutputStream output = new FileOutputStream(path)) {
                output.write(receipt.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
            }
            DurableFiles.INSTANCE.syncDirectory(root);
            // Unresolved test-owned intent is retained for the ordinary verification/recovery UI.
            if (resolved && attempt.getString("id").equals(restore.snapshot().getString("id"))) {
                new AtomicFile(new File(context.getFilesDir(), "emergency-restore.json")).delete();
                DurableFiles.INSTANCE.syncDirectory(context.getFilesDir());
            }
        }
    }

    @Test public void testRecoverOnlyOwnedReadOnlyVerificationIntent() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        EmergencyRestoreStore restore = new EmergencyRestoreStore(context);
        JSONObject attempt = restore.snapshot();
        org.junit.Assume.assumeTrue("No test-owned read-only verification intent to recover", attempt != null &&
            "verification_pending".equals(attempt.optString("status")));
        assertEquals(NORMAL, attempt.getString("normal"));
        File parent = new File(context.getFilesDir(), "worker-service-loss-probes");
        File[] folders = parent.listFiles(); assertNotNull(folders); assertTrue(folders.length <= 64);
        File owner = null;
        for (File folder : folders) {
            assertEquals(UUID.fromString(folder.getName()).toString(), folder.getName());
            File path = new File(folder, "receipt.json");
            if (!path.isFile()) continue;
            assertTrue(path.length() <= 16384);
            JSONObject receipt = new JSONObject(new String(java.nio.file.Files.readAllBytes(path.toPath()), StandardCharsets.UTF_8));
            if (attempt.getString("id").equals(receipt.optString("emergency_request"))) {
                assertNull("Ambiguous test owner", owner);
                assertEquals("read-only foreground verification and own UserService death", receipt.getString("scope"));
                assertEquals(NORMAL, receipt.getString("normal")); assertFalse(receipt.getBoolean("game_mutated"));
                owner = folder;
            }
        }
        assertNotNull("Do not resolve another action's emergency intent", owner);
        ready();
        assertFalse("Another foreground action is active", shell("dumpsys activity services " + APP).contains(".PatchWorkerService"));
        shell("am start -W -n " + APP + "/.MainActivity");
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            long started = System.currentTimeMillis(); start(activity, attempt);
            JSONObject result = terminal(new File(context.getFilesDir(), "worker-state.json"), started);
            assertEquals(result.toString(), "verified", result.getString("status"));
            assertEquals("apk_verified", restore.snapshot().getString("status"));
            JSONObject recovered = new JSONObject().put("emergency_request", attempt.getString("id"))
                .put("result", result).put("game_mutated", false).put("normal", NORMAL);
            try (FileOutputStream output = new FileOutputStream(new File(owner, "recovered.json"))) {
                output.write(recovered.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
            }
            DurableFiles.INSTANCE.syncDirectory(owner);
            new AtomicFile(new File(context.getFilesDir(), "emergency-restore.json")).delete();
            DurableFiles.INSTANCE.syncDirectory(context.getFilesDir());
        }
    }
}
