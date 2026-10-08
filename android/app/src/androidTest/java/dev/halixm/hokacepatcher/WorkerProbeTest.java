package dev.halixm.hokacepatcher;

import android.content.Intent;
import android.os.ParcelFileDescriptor;
import android.util.AtomicFile;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import static org.junit.Assert.*;

/** Read-only foreground worker verifies the normal game while its activity is recreated. */
@RunWith(AndroidJUnit4.class)
public final class WorkerProbeTest {
    @Test public void testReadOnlyVerificationSurvivesActivityRecreation() throws Exception {
        verify(false);
    }

    @Test public void testEmergencyIntentResolvesOnlyAfterInstalledVerification() throws Exception {
        verify(true);
    }

    private void verify(boolean emergency) throws Exception {
        String expected = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
        try (ParcelFileDescriptor.AutoCloseInputStream launch = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(
                "am start -W -n dev.halixm.hokacepatcher/.MainActivity"))) {
            byte[] buffer = new byte[4096]; while (launch.read(buffer) >= 0) { }
        }
        File state = new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir(),
            "worker-state.json");
        EmergencyRestoreStore restore = new EmergencyRestoreStore(
            InstrumentationRegistry.getInstrumentation().getTargetContext());
        File restoreFile = new File(state.getParentFile(), "emergency-restore.json");
        if (emergency) org.junit.Assume.assumeTrue("Existing emergency record must remain untouched", restore.snapshot() == null);
        JSONObject attempt = emergency ? restore.begin(expected) : null;
        String flow = java.util.UUID.randomUUID().toString();
        long started = System.currentTimeMillis();
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            activity.onActivity(current -> {
                Intent request = new Intent(current, PatchWorkerService.class).setAction("verify").putExtra("normal", expected).putExtra("flow", flow);
                if (attempt != null) request.putExtra("emergency", attempt.optString("id"));
                current.startForegroundService(request);
            });
            activity.recreate();
            JSONObject result = null;
            long deadline = System.currentTimeMillis() + 90000;
            while (System.currentTimeMillis() < deadline) {
                if (state.isFile()) {
                    result = new JSONObject(new String(new AtomicFile(state).readFully(), "UTF-8"));
                    if (result.optLong("updated_ms") >= started && !"running".equals(result.optString("status"))) break;
                }
                Thread.sleep(250);
            }
            assertNotNull("Worker result missing", result);
            assertTrue("Stale worker result", result.getLong("updated_ms") >= started);
            assertEquals(result.toString(), "verified", result.getString("status"));
            assertEquals("verify", result.getString("action"));
            assertEquals("Worker must return the exact request token", flow, result.getString("flow"));
            if (emergency) assertEquals("apk_verified", restore.snapshot().getString("status"));
            Thread.sleep(1200);
            assertFalse("Service must retire before automatic continuation", PatchWorkerService.Companion.isWorking());
            activity.onActivity(current -> {
                android.widget.TextView status = current.getWindow().getDecorView().findViewWithTag("worker-status");
                assertNotNull(status);
                assertTrue(status.getText().toString(), status.getText().toString().contains("Normal game app verified"));
                if (emergency) assertTrue(status.getText().toString().contains("Emergency APK restore verified"));
            });
        } finally {
            if (attempt != null && restore.snapshot() != null &&
                attempt.getString("id").equals(restore.snapshot().getString("id"))) {
                new AtomicFile(restoreFile).delete();
                DurableFiles.INSTANCE.syncDirectory(state.getParentFile());
            }
        }
    }
}
