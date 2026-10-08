package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.Intent;
import android.os.ParcelFileDescriptor;
import android.util.AtomicFile;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Real foreground dispatch with a nonexistent consent UUID; no valid setup request is submitted. */
public final class FirstSetupWorkerGuardProbeTest {
    @Test public void testMissingConsentStopsBeforeSetupJournal() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String request = UUID.randomUUID().toString();
        assertFalse(new File(context.getFilesDir(), "setup-requests/" + request + ".json").exists());
        File setups = new File(context.getFilesDir(), "first-setups");
        int before = setups.isDirectory() ? setups.list().length : 0;
        try (ParcelFileDescriptor.AutoCloseInputStream launch = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(
                "am start -W -n dev.halixm.hokacepatcher/.MainActivity"))) {
            byte[] buffer = new byte[4096]; while (launch.read(buffer) >= 0) { }
        }
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            long started = System.currentTimeMillis();
            activity.onActivity(current -> current.startForegroundService(new Intent(current, PatchWorkerService.class)
                .setAction("first_setup").putExtra("request", request)));
            File state = new File(context.getFilesDir(), "worker-state.json");
            JSONObject result = null;
            long deadline = started + 60000;
            while (System.currentTimeMillis() < deadline) {
                if (state.isFile()) {
                    result = new JSONObject(new String(new AtomicFile(state).readFully(), StandardCharsets.UTF_8));
                    if (result.optLong("updated_ms") >= started && "error".equals(result.optString("status"))) break;
                }
                Thread.sleep(100);
            }
            assertNotNull(result); assertTrue(result.toString(), result.getLong("updated_ms") >= started);
            assertEquals(result.toString(), "first_setup", result.getString("action"));
            assertEquals(result.toString(), "error", result.getString("status"));
            assertTrue(result.toString(), result.getString("error").contains(request));
        }
        assertEquals(before, setups.isDirectory() ? setups.list().length : 0);
    }
}
