package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.nio.file.Files;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Fresh offline build and resource observations using immutable already-approved scratch inputs. */
@RunWith(AndroidJUnit4.class)
public final class PerformanceProbeTest {
    @Test public void testMeasuredBothLayerBuild() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File base = new File(context.getFilesDir(), "scratch/control-1402-verified");
        assertTrue(new File(base, "game").isDirectory());
        File session = new File(context.getFilesDir(), "scratch/performance-" + UUID.randomUUID());
        assertTrue(session.mkdirs());
        // Read-only source links avoid duplicating the 4.7 GB approved inputs for measurement.
        Files.createSymbolicLink(new File(session, "game").toPath(), new File(base, "game").toPath());
        Files.createSymbolicLink(new File(session, "normal.apk").toPath(), new File(base, "normal.apk").toPath());
        Files.copy(new File(base, "control.json").toPath(), new File(session, "control.json").toPath());
        RunMetrics metrics = new RunMetrics(context, new File(session, "resource-metrics.json"));
        String status = "failed";
        try {
            File root = EngineAssets.INSTANCE.prepare(context);
            if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
            String summary = Python.getInstance().getModule("android_bridge")
                .callAttr("build_scratch", root.getPath(), session.getPath()).toString();
            JSONObject counts = new JSONObject(Python.getInstance().getModule("android_bridge")
                .callAttr("result_counts", root.getPath(), summary).toString());
            assertEquals(391, counts.getInt("text_tables"));
            assertEquals(395, counts.getInt("applied_textures"));
            assertEquals(1, counts.getInt("skipped_tables"));
            assertEquals(0, counts.getInt("skipped_textures"));
            status = "complete";
        } finally {
            JSONObject result = metrics.finish(status);
            assertTrue(result.getInt("samples") >= 2);
            assertTrue(result.getLong("maximum_sampled_rss_kib") > 0);
            android.util.Log.i("HokAceProbe", "Resource metrics " + session.getName() + ": " + result);
        }
    }
}
