package dev.halixm.hokacepatcher;

import android.app.AlertDialog;
import android.content.Context;
import android.os.ParcelFileDescriptor;
import android.view.View;
import android.view.ViewGroup;
import android.widget.CheckBox;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;
import static org.junit.Assert.*;

/**
 * Ticket 13: no routine patch confirmation follows Start. The finish-updates instruction is on ③ before Start,
 * and the explicit Remove asks one plain question at the tap, with no checkbox; Cancel creates no approval.
 */
public final class UpdateCheckpointProbeTest {
    @Test public void testNoRoutinePatchDialogAndPlainRemoveConfirmation() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        try (ParcelFileDescriptor.AutoCloseInputStream launch = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(
                "am start -W -n dev.halixm.hokacepatcher/.MainActivity"))) {
            byte[] buffer = new byte[4096]; while (launch.read(buffer) >= 0) { }
        }
        // The post-Start checkbox dialog is gone for good, not hidden behind a flag.
        for (Method method : MainActivity.class.getDeclaredMethods())
            assertNotEquals("showPatchConfirmation", method.getName());
        File requests = new File(context.getFilesDir(), "patch-requests");
        int before = requests.isDirectory() ? requests.list().length : 0;
        int runsBefore = new RunStore(context).pending().size();
        Method show = MainActivity.class.getDeclaredMethod("showRemoveConfirmation");
        show.setAccessible(true);
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            AtomicReference<AlertDialog> shown = new AtomicReference<>();
            activity.onActivity(current -> {
                try {
                    AlertDialog dialog = (AlertDialog) show.invoke(current);
                    shown.set(dialog);
                    assertNull(dialog.getWindow().getDecorView().findViewWithTag("update-confirmation"));
                    assertFalse(containsCheckBox(dialog.getWindow().getDecorView()));
                    assertTrue(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    dialog.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();
                } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
            });
            InstrumentationRegistry.getInstrumentation().waitForIdleSync();
            activity.onActivity(current -> assertFalse(shown.get().isShowing()));
            activity.recreate();
        }
        assertEquals(before, requests.isDirectory() ? requests.list().length : 0);
        assertEquals(runsBefore, new RunStore(context).pending().size());
    }

    private static boolean containsCheckBox(View view) {
        if (view instanceof CheckBox) return true;
        if (!(view instanceof ViewGroup)) return false;
        ViewGroup group = (ViewGroup) view;
        for (int index = 0; index < group.getChildCount(); index++)
            if (containsCheckBox(group.getChildAt(index))) return true;
        return false;
    }
}
