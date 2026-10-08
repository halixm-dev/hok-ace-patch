package dev.halixm.hokacepatcher;

import android.content.Context;
import android.graphics.Bitmap;
import android.view.View;
import android.widget.Button;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import org.junit.Test;
import static org.junit.Assert.*;

/** Real navigation and consent cancellation, without starting any game operation. */
public final class GuidedHomeProbeTest {
    private void picture(MainActivity activity, String name) throws Exception {
        // Render only this application's view. System notifications/other windows are excluded.
        View view = activity.getWindow().getDecorView();
        Bitmap image = Bitmap.createBitmap(view.getWidth(), view.getHeight(), Bitmap.Config.ARGB_8888);
        view.draw(new android.graphics.Canvas(image));
        File folder = new File(activity.getCacheDir(), "guided-ui-preview");
        assertTrue(folder.isDirectory() || folder.mkdirs());
        try (FileOutputStream output = new FileOutputStream(new File(folder, name + ".png"))) {
            assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, output));
        } finally { image.recycle(); }
    }
    @Test public void testAutomaticHomeHasNoTutorialOrVoice() throws Exception {
        try (android.os.ParcelFileDescriptor.AutoCloseInputStream launch = new android.os.ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(
                "am start -W -n dev.halixm.hokacepatcher/.MainActivity"))) {
            byte[] buffer = new byte[4096]; while (launch.read(buffer) >= 0) { }
        }
        try (ActivityScenario<MainActivity> activity = ActivityScenario.launch(MainActivity.class)) {
            activity.onActivity(current -> {
                View root = current.getWindow().getDecorView();
                Button next = root.findViewWithTag("next-step");
                assertNotNull(next); assertTrue(next.isShown());
                assertTrue(next.getMinimumHeight() >= 60 * current.getResources().getDisplayMetrics().density - 1);
                assertFalse(root.findViewWithTag("worker-status").isShown());
                assertNotNull(root.findViewWithTag("show-recovery"));
            });
            activity.onActivity(current -> {
                try { picture(current, "home"); } catch (Exception error) { throw new AssertionError(error); }
            });
            activity.onActivity(current -> {
                View root = current.getWindow().getDecorView();
                assertNull(root.findViewWithTag("hear-step"));
                assertNull(root.findViewWithTag("show-checklist"));
                assertNull(root.findViewWithTag("show-help"));
                root.findViewWithTag("show-technical").performClick();
                assertTrue(root.findViewWithTag("worker-status").getVisibility() == View.VISIBLE);
                root.findViewWithTag("show-technical").performClick();
                assertFalse(root.findViewWithTag("worker-status").isShown());
            });
            activity.recreate();
            activity.onActivity(current -> assertFalse(current.getWindow().getDecorView().findViewWithTag("worker-status").isShown()));
        }
    }
}
