package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.os.Binder;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.util.UUID;
import org.junit.Test;
import static org.junit.Assert.*;

/** Cancellation and unresolved recovery must refuse preparation before touching the device. */
public final class PreparationGuardProbeTest {
    private Context isolated() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "preparation-guard-probes/" + UUID.randomUUID());
        assertTrue(root.mkdirs());
        return new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
    }
    @Test public void testCancelledBeforeDeviceAccess() {
        Context context = isolated();
        IPrivilegedDeviceService unavailable = IPrivilegedDeviceService.Stub.asInterface(new Binder());
        try {
            new ApkPreparation(context).prepare(unavailable, message -> kotlin.Unit.INSTANCE,
                () -> { throw new IllegalStateException("cancel guard"); });
            fail("Cancelled preparation proceeded");
        } catch (IllegalStateException expected) { assertEquals("cancel guard", expected.getMessage()); }
        assertFalse(new File(context.getFilesDir(), "preparations").exists());
    }
    @Test public void testUnfinishedRecoveryBeforeDeviceAccess() {
        Context context = isolated();
        String identity = "0000000000000000000000000000000000000000000000000000000000000000";
        SessionJournal pending = SessionJournal.Companion.create(new File(context.getFilesDir(), "sessions"), identity, identity);
        IPrivilegedDeviceService unavailable = IPrivilegedDeviceService.Stub.asInterface(new Binder());
        try {
            new ApkPreparation(context).prepare(unavailable, message -> kotlin.Unit.INSTANCE);
            fail("Preparation bypassed unfinished recovery");
        } catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("Recover the interrupted patch")); }
        assertEquals(PatchPhase.PREPARED, SessionJournal.Companion.load(pending.getDirectory()).getPhase());
        assertFalse(new File(context.getFilesDir(), "preparations").exists());
    }
}
