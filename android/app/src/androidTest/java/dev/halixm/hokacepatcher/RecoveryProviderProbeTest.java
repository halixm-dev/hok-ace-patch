package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ResultReceiver;
import android.os.ParcelFileDescriptor;
import android.os.Parcel;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.core.app.ActivityScenario;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Verify recovery URI consumption in another UID; no installer/game mutation. */
@RunWith(AndroidJUnit4.class)
public final class RecoveryProviderProbeTest {
    @Test public void testGrantedRecoveryReadAndWriteRefusal() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String hash = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
        Uri uri = Uri.parse("content://dev.halixm.hokacepatcher.recovery/" + hash + "/normal.apk");
        try {
            context.getContentResolver().openFileDescriptor(uri, "w");
            fail("Writable recovery URI accepted");
        } catch (IllegalArgumentException expected) { }
        CountDownLatch finished = new CountDownLatch(1);
        AtomicReference<Bundle> outcome = new AtomicReference<>();
        ResultReceiver receiver = new ResultReceiver(new Handler(Looper.getMainLooper())) {
            @Override protected void onReceiveResult(int code, Bundle data) {
                data.putInt("code", code); outcome.set(data); finished.countDown();
            }
        };
        Parcel parcel = Parcel.obtain();
        ResultReceiver remoteReceiver;
        try {
            receiver.writeToParcel(parcel, 0);
            parcel.setDataPosition(0);
            remoteReceiver = ResultReceiver.CREATOR.createFromParcel(parcel);
        } finally { parcel.recycle(); }
        context.grantUriPermission("io.github.hokace.fixture", uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        // MIUI blocks an instrumentation background activity start. Put only the owned
        // diagnostic activity in foreground through the test's shell before the cross-UID read.
        try (ParcelFileDescriptor.AutoCloseInputStream launch = new ParcelFileDescriptor.AutoCloseInputStream(
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(
                "am start -W -n dev.halixm.hokacepatcher/.MainActivity"))) {
            byte[] buffer = new byte[4096];
            while (launch.read(buffer) >= 0) { }
        }
        try (ActivityScenario<MainActivity> foreground = ActivityScenario.launch(MainActivity.class)) {
            Intent request = new Intent().setClassName("io.github.hokace.fixture",
                "io.github.hokace.fixture.FixtureActivity").setData(uri)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION)
                .putExtra("result", remoteReceiver);
            foreground.onActivity(activity -> activity.startActivity(request));
            assertTrue("Recovery consumer timed out", finished.await(120, TimeUnit.SECONDS));
            assertEquals(outcome.get().toString(), 0, outcome.get().getInt("code"));
            assertEquals(hash, outcome.get().getString("sha256"));
            assertEquals(2026631918L, outcome.get().getLong("bytes"));
        } finally { context.revokeUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION); }
    }
}
