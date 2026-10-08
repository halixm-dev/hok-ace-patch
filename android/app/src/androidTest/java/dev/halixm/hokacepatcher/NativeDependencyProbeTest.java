package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Exercise libraries not necessarily reached by a successful package-build result. */
@RunWith(AndroidJUnit4.class)
public final class NativeDependencyProbeTest {
    @Test public void testFrameCodecAndFreeTypeRender() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python python = Python.getInstance();
        byte[] raw = new byte[]{0, 1, 2, 3, 4, 5, (byte)255};
        PyObject frame = python.getModule("lz4.frame");
        PyObject encoded = frame.callAttr("compress", raw);
        assertArrayEquals(raw, frame.callAttr("decompress", encoded).toJava(byte[].class));
        assertTrue(python.getModule("lz4").callAttr("library_version_number").toInt() >= 10900);
        assertEquals("cext", python.getModule("zstandard").get("backend").toString());
        PyObject font = python.getModule("PIL.ImageFont").callAttr("load_default", 12);
        assertNotEquals("None", font.callAttr("getmask", "HOK ACE").callAttr("getbbox").toString());
        assertEquals("2.9.1", python.getModule("PIL._imagingft").get("freetype2_version").toString());
    }
}
