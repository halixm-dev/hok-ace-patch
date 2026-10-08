package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;

/** Device scratch-only checks. Logs the unavailable codecs rather than declaring full parity. */
@RunWith(AndroidJUnit4.class)
public final class EngineProbeTest {
    @Test
    public void testEmbeddedRuntimeAndCoreCodecs() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String root = EngineAssets.INSTANCE.prepare(context).getAbsolutePath();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        String report = Python.getInstance().getModule("android_bridge")
            .callAttr("diagnostics", root).toString();
        android.util.Log.i("HokAceProbe", report);
        JSONObject result = new JSONObject(report);
        assertTrue(result.getString("python").startsWith("3.12."));
        assertTrue(result.getBoolean("lz4_roundtrip"));
        assertTrue(result.getBoolean("zstd_roundtrip"));
        assertTrue(result.getInt("catalog_tables") > 0);
        assertEquals(398, result.getInt("catalog_textures"));
        // The complete-codec build is the gate for running scratch pipeline tests.
        if (InstrumentationRegistry.getArguments().getString("requireFullCodecs", "false").equals("true")) {
            assertTrue(result.getBoolean("full_codec_gate"));
        }
    }
}
