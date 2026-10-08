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
import rikka.shizuku.Shizuku;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import static org.junit.Assert.*;

/** User disables only HOK ACE's permission first; dispatch must fail before verification. */
public final class WorkerPermissionProbeTest {
    private static final String APP = "dev.halixm.hokacepatcher";
    private static final String NORMAL = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
    private String shell(String command) throws Exception {
        try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(command))) {
            ByteArrayOutputStream output = new ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) >= 0) { output.write(buffer, 0, count); assertTrue(output.size() <= 64 * 1024); }
            return output.toString("UTF-8");
        }
    }
    private byte[] saved(File path) throws Exception {
        assertFalse(Files.isSymbolicLink(path.toPath()));
        if (!path.exists()) return null;
        assertTrue(path.isFile() && path.length() <= 16384);
        return Files.readAllBytes(path.toPath());
    }
    @Test public void testDeniedPermissionCannotClaimInstalledVerification() throws Exception {
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try { assertTrue("Keep Shizuku running for the permission-denial check", available.await(15, TimeUnit.SECONDS)); }
        finally { Shizuku.removeBinderReceivedListener(listener); }
        assertTrue(Shizuku.pingBinder());
        assertEquals("Disable only HOK ACE authorization in Shizuku before this probe", PackageManager.PERMISSION_DENIED,
            Shizuku.checkSelfPermission());
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertFalse("Another worker is active", shell("dumpsys activity services " + APP).contains(".PatchWorkerService"));
        File emergency = new File(context.getFilesDir(), "emergency-restore.json");
        File backup = new File(emergency.getPath() + ".bak");
        byte[] before = saved(emergency), beforeBackup = saved(backup);
        File resultPath = new File(context.getFilesDir(), "worker-state.json");
        shell("am start -W -n " + APP + "/.MainActivity");
        JSONObject result = null;
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            long started = System.currentTimeMillis();
            activity.onActivity(current -> current.startForegroundService(new Intent(current, PatchWorkerService.class)
                .setAction("verify").putExtra("normal", NORMAL)));
            long deadline = started + 60000;
            while (System.currentTimeMillis() < deadline) {
                if (resultPath.isFile()) {
                    result = new JSONObject(new String(new AtomicFile(resultPath).readFully(), StandardCharsets.UTF_8));
                    if (result.optLong("updated_ms") >= started && !"running".equals(result.optString("status"))) break;
                }
                Thread.sleep(100);
            }
            assertNotNull(result); assertTrue(result.getLong("updated_ms") >= started);
            assertEquals(result.toString(), "error", result.getString("status"));
            assertEquals("verify", result.getString("action"));
            assertTrue(result.getString("error").contains("Authorize HOK ACE"));
        }
        assertArrayEquals(before, saved(emergency)); assertArrayEquals(beforeBackup, saved(backup));
        File root = new File(context.getFilesDir(), "worker-permission-probes/" + UUID.randomUUID());
        DurableFiles.INSTANCE.createDirectories(root);
        JSONObject receipt = new JSONObject().put("permission", "denied").put("shizuku_running", true)
            .put("result", result).put("emergency_record_unchanged", true).put("game_mutated", false);
        try (FileOutputStream output = new FileOutputStream(new File(root, "receipt.json"))) {
            output.write(receipt.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
        }
        DurableFiles.INSTANCE.syncDirectory(root);
    }
}
