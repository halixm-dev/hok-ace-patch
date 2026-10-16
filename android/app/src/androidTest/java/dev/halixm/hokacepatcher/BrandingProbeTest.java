package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.drawable.AdaptiveIconDrawable;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import org.junit.Test;
import static org.junit.Assert.*;

/** Inspect installed launcher resources without opening the activity or requesting game access. */
public final class BrandingProbeTest {
    @Test public void testInstalledIdentityAndAdaptiveIcon() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertEquals("dev.halixm.hokacepatcher", context.getPackageName());
        ApplicationInfo app = context.getApplicationInfo();
        assertEquals("HOK ACE Language Patcher", context.getPackageManager().getApplicationLabel(app).toString());
        Drawable icon = context.getPackageManager().getApplicationIcon(app);
        assertTrue("Launcher icon must be adaptive", icon instanceof AdaptiveIconDrawable);
        AdaptiveIconDrawable adaptive = (AdaptiveIconDrawable) icon;
        assertTrue(adaptive.getBackground() instanceof ColorDrawable);
        assertEquals(Color.parseColor("#9EBEF7"), ((ColorDrawable) adaptive.getBackground()).getColor());
        assertNotNull(adaptive.getForeground());
        Bitmap image = Bitmap.createBitmap(512, 512, Bitmap.Config.ARGB_8888);
        adaptive.setBounds(0, 0, 512, 512);
        adaptive.draw(new Canvas(image));
        File folder = new File(context.getCacheDir(), "branding-preview");
        assertTrue(folder.isDirectory() || folder.mkdirs());
        try (FileOutputStream output = new FileOutputStream(new File(folder, "adaptive-icon.png"))) {
            assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, output));
        } finally { image.recycle(); }
    }
}
