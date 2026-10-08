package dev.halixm.hokacepatcher;

import android.app.AlertDialog;
import android.content.Context;
import android.os.ParcelFileDescriptor;
import android.widget.CheckBox;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.lang.reflect.Method;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;
import static org.junit.Assert.*;

/** Toggle real consent controls and Cancel only; never press the setup or update action. */
public final class FirstSetupConsentProbeTest {
    @Test public void testSeparateDataLossAndLoginConsentAndFreshUpdateCheckpoint() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        try (ParcelFileDescriptor.AutoCloseInputStream launch = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(
                "am start -W -n dev.halixm.hokacepatcher/.MainActivity"))) {
            byte[] buffer = new byte[4096]; while (launch.read(buffer) >= 0) { }
        }
        File requests = new File(context.getFilesDir(), "setup-requests");
        int before = requests.isDirectory() ? requests.list().length : 0;
        String sha = "0000000000000000000000000000000000000000000000000000000000000000";
        ApkIdentity normal = new ApkIdentity(1, sha, "com.tencent.tmgp.osgame", 1, "fixture", GameSigner.CERTIFICATE_SHA256, false);
        ApkIdentity source = new ApkIdentity(1, sha, normal.getPackageName(), 1, "fixture", sha, false);
        ApkIdentity access = new ApkIdentity(1, sha, normal.getPackageName(), 1, "fixture", GameSigner.CERTIFICATE_SHA256, true);
        ApkPreparation.Prepared fixture = new ApkPreparation.Prepared(new File(context.getFilesDir(),
            "preparations/" + UUID.randomUUID()), source, normal, access);
        Method show = MainActivity.class.getDeclaredMethod("showFirstSetupConfirmation", ApkPreparation.Prepared.class);
        Method update = MainActivity.class.getDeclaredMethod("showSetupUpdateConfirmation", String.class);
        show.setAccessible(true); update.setAccessible(true);
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            AtomicReference<AlertDialog> shown = new AtomicReference<>();
            activity.onActivity(current -> {
                try {
                    AlertDialog dialog = (AlertDialog) show.invoke(current, fixture); shown.set(dialog);
                    CheckBox loss = dialog.getWindow().getDecorView().findViewWithTag("setup-data-loss");
                    CheckBox login = dialog.getWindow().getDecorView().findViewWithTag("setup-scan-login");
                    assertNotNull(loss); assertNotNull(login); assertFalse(loss.isChecked()); assertFalse(login.isChecked());
                    assertFalse(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    loss.setChecked(true); assertFalse(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    loss.setChecked(false); login.setChecked(true); assertFalse(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    loss.setChecked(true); assertTrue(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    login.setChecked(false); assertFalse(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    dialog.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();
                } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
            });
            InstrumentationRegistry.getInstrumentation().waitForIdleSync();
            activity.onActivity(current -> assertFalse(shown.get().isShowing()));
            activity.recreate();
            activity.onActivity(current -> {
                try {
                    AlertDialog dialog = (AlertDialog) update.invoke(current, UUID.randomUUID().toString()); shown.set(dialog);
                    CheckBox checkbox = dialog.getWindow().getDecorView().findViewWithTag("setup-update-confirmation");
                    assertNotNull(checkbox); assertFalse(checkbox.isChecked());
                    assertFalse(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    checkbox.setChecked(true); assertTrue(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    checkbox.setChecked(false); assertFalse(dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled());
                    dialog.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();
                } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
            });
            InstrumentationRegistry.getInstrumentation().waitForIdleSync();
            activity.onActivity(current -> assertFalse(shown.get().isShowing()));
        }
        assertEquals(before, requests.isDirectory() ? requests.list().length : 0);
    }
}
