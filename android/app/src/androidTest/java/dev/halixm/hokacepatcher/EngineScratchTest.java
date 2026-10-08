package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import static org.junit.Assert.*;

/** Developer-supplied matching game/APK data in this app's private storage only. */
@RunWith(AndroidJUnit4.class)
public final class EngineScratchTest {
    private String[] paths() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String sessionName = InstrumentationRegistry.getArguments().getString("session");
        assertNotNull("Supply -e session <name> after streaming the scratch inputs", sessionName);
        assertTrue(sessionName.matches("[a-zA-Z0-9-]{1,64}"));
        String root = EngineAssets.INSTANCE.prepare(context).getAbsolutePath();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        return new String[] {root, new File(context.getFilesDir(), "scratch/" + sessionName).getAbsolutePath()};
    }
    @Test public void testBuildBothLayers() throws Exception {
        String[] paths = paths();
        String summary = Python.getInstance().getModule("android_bridge")
            .callAttr("build_scratch", paths[0], paths[1]).toString();
        assertTrue(summary.contains("added-from-apk"));
        android.util.Log.i("HokAceProbe", "PASS: full scratch build; " + paths[1]);
    }
    @Test public void testGraphicsOracle() throws Exception {
        String[] paths = paths();
        String result = Python.getInstance().getModule("android_bridge")
            .callAttr("graphics_oracle", paths[0], paths[1]).toString();
        android.util.Log.i("HokAceProbe", result);
    }
}
