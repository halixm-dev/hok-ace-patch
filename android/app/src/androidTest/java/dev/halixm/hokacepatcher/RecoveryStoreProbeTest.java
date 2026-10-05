package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Verify retained normal identity and reject access APK adoption using approved private scratch copies. */
@RunWith(AndroidJUnit4.class)
public final class RecoveryStoreProbeTest {
    @Test public void testNormalRetentionAndAccessRejection() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File normal = new File(context.getFilesDir(), "scratch/control-1402-verified/normal.apk");
        File access = new File(context.getFilesDir(), "scratch/game-access-1402/access.apk");
        assertTrue(normal.isFile()); assertTrue(access.isFile());
        assertTrue(context.getFilesDir().getUsableSpace() > normal.length() + 256L * 1024 * 1024);
        RecoveryStore store = new RecoveryStore(context);
        ApkIdentity identity = store.adopt(normal);
        assertEquals("b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a", identity.getSha256());
        assertFalse(identity.getDebuggable());
        assertEquals(identity, store.verify(identity.getSha256()));
        assertEquals(identity, store.adopt(normal));
        try {
            store.adopt(access);
            fail("Access APK adopted as recovery");
        } catch (IllegalStateException expected) {
            assertTrue(expected.getMessage().contains("verified normal"));
        }
        assertEquals(identity, store.verify(identity.getSha256()));
    }
}
