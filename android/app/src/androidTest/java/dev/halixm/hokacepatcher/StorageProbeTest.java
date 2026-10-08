package dev.halixm.hokacepatcher;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Space refusal cannot bypass recovery reserve or wrap arithmetic into an accepted small budget. */
@RunWith(AndroidJUnit4.class)
public final class StorageProbeTest {
    @Test public void testRecoveryReserveAndOverflowRefusal() {
        long apk = 2026631918L;
        long largestWrite = 500L * 1024 * 1024;
        long required = StorageBudget.INSTANCE.required(new long[]{apk, largestWrite});
        assertTrue(required > apk + largestWrite);
        File directory = InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir();
        try {
            StorageBudget.INSTANCE.requireAvailable(directory, "forced low-space probe", new long[]{directory.getUsableSpace(), apk});
            fail("Normal APK reserve was not enforced");
        } catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("required")); }
        try { StorageBudget.INSTANCE.required(new long[]{Long.MAX_VALUE, 1}); fail("Overflow accepted"); }
        catch (ArithmeticException expected) { }
        try { StorageBudget.INSTANCE.required(new long[]{-1}); fail("Negative allocation accepted"); }
        catch (IllegalArgumentException expected) { }
    }
}
