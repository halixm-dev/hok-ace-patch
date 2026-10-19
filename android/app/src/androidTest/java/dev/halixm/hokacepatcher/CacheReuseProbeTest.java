package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.Intent;
import android.util.AtomicFile;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Only prepare/cache validation and one-use consent bookkeeping; never patches or installs the game. */
@RunWith(AndroidJUnit4.class)
public final class CacheReuseProbeTest {
    @Test public void existingNormalReusesCacheAndConfirmation() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertFalse(PatchWorkerService.Companion.isWorking());
        File folders = new File(context.getFilesDir(), "preparations");
        int before = folders.list().length;
        String flow = UUID.randomUUID().toString();
        context.startForegroundService(new Intent(context, PatchWorkerService.class).setAction("prepare").putExtra("flow", flow));
        JSONObject state = null;
        // Preparation reports steps 1 and 2 of six, even when it reuses saved APKs.
        Set<String> steps = new LinkedHashSet<>();
        long deadline = System.currentTimeMillis() + 360000;
        while (System.currentTimeMillis() < deadline) {
            Thread.sleep(1000);
            File file = new File(context.getFilesDir(), "worker-state.json");
            if (!file.exists()) continue;
            state = new JSONObject(new String(new AtomicFile(file).readFully(), StandardCharsets.UTF_8));
            if (flow.equals(state.optString("flow")) && state.has("step")) {
                assertEquals(state.toString(), 6, state.getInt("steps"));
                steps.add(state.getString("step"));
            }
            if (flow.equals(state.optString("flow")) && !state.optString("status").equals("running") &&
                    !PatchWorkerService.Companion.isWorking()) break;
        }
        assertNotNull(state);
        assertEquals(state.toString(), "prepared", state.optString("status"));
        assertEquals(flow, state.optString("flow"));
        assertEquals(before, folders.list().length);
        // Polled once a second, a quick reuse may pass step 1 unseen; it never reports a later step.
        assertTrue(steps.toString(), Arrays.asList("check_game", "prepare_files").containsAll(steps));
        assertEquals(steps.toString(), "prepare_files", new ArrayList<>(steps).get(steps.size() - 1));
        ApkPreparation.Prepared prepared = new ApkPreparation(context).load(state.getString("preparation"));
        assertEquals(prepared.getNormal(), prepared.getSource());
        assertFalse(prepared.getRequiresSignatureConversion());
        String request = new PatchRequestStore(context).confirm(prepared, true);
        assertEquals(prepared.getSource(), new PatchRequestStore(context).claim(request).getSource());
        assertTrue(new File(prepared.getDirectory(), "original.apk").isFile());
        assertTrue(prepared.getAccessFile().isFile());
    }
}
