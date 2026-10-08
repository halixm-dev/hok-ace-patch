package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import java.io.File;
import java.util.UUID;
import static org.junit.Assert.*;

/** Private saved-intent checks; installer and game are never invoked. */
public final class EmergencyRestoreProbeTest {
    private static final String NORMAL = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private EmergencyRestoreStore store() {
        return new EmergencyRestoreStore(scopedContext());
    }
    private Context scopedContext() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File directory = new File(context.getFilesDir(), "emergency-restore-probes/" + UUID.randomUUID());
        assertTrue(directory.mkdirs());
        return new ContextWrapper(context) {
            @Override public File getFilesDir() { return directory; }
        };
    }

    @Test public void pendingIntentSurvivesReloadAndRetry() throws Exception {
        EmergencyRestoreStore store = store();
        assertNull(store.snapshot());
        store.requireResolved();
        JSONObject first = store.begin(NORMAL);
        assertEquals("verification_pending", store.snapshot().getString("status"));
        assertEquals(first.getString("id"), store.begin(NORMAL).getString("id"));
        assertTrue(store.describe().contains("unverified"));
        assertTrue(store.describe().contains("unfinished game-data"));
        try { store.requireResolved(); fail("Pending emergency restore allowed new mutation"); }
        catch (IllegalStateException expected) { }
        try { store.begin(NORMAL.replace('a', 'b')); fail("Changed recovery APK accepted"); }
        catch (IllegalStateException expected) { }
        assertEquals(first.getString("id"), store.snapshot().getString("id"));
    }

    @Test public void failedVerificationCannotResolvePendingIntent() throws Exception {
        EmergencyRestoreStore store = store();
        JSONObject first = store.begin(NORMAL);
        try {
            store.verify(first.getString("id"), NORMAL, normal -> { throw new IllegalStateException("Wrong installed APK"); });
            fail("Failed installed check accepted");
        } catch (IllegalStateException expected) { }
        assertEquals("verification_pending", store.snapshot().getString("status"));
        assertFalse(store.snapshot().has("verified_ms"));
    }

    @Test public void staleRequestCannotVerifyAnotherAttempt() throws Exception {
        EmergencyRestoreStore store = store();
        JSONObject first = store.begin(NORMAL);
        int[] calls = {0};
        try {
            store.verify(UUID.randomUUID().toString(), NORMAL, normal -> { calls[0]++; return kotlin.Unit.INSTANCE; });
            fail("Stale request accepted");
        } catch (IllegalStateException expected) { }
        assertEquals(0, calls[0]);
        store.verify(first.getString("id"), NORMAL, normal -> { calls[0]++; assertEquals(NORMAL, normal); return kotlin.Unit.INSTANCE; });
        assertEquals(1, calls[0]);
        assertEquals("apk_verified", store.snapshot().getString("status"));
        store.requireResolved();
        assertTrue(store.describe().contains("still require recovery"));
        JSONObject second = store.begin(NORMAL);
        assertNotEquals(first.getString("id"), second.getString("id"));
        try {
            store.verify(first.getString("id"), NORMAL, normal -> { fail("Old request reached verifier"); return kotlin.Unit.INSTANCE; });
            fail("Old completion accepted");
        } catch (IllegalStateException expected) { }
        assertEquals("verification_pending", store.snapshot().getString("status"));
    }

    @Test public void pendingRestoreStopsBothCoordinatorsBeforeDeviceUse() throws Exception {
        Context context = scopedContext();
        new EmergencyRestoreStore(context).begin(NORMAL);
        IPrivilegedDeviceService device = (IPrivilegedDeviceService) java.lang.reflect.Proxy.newProxyInstance(
            getClass().getClassLoader(), new Class<?>[] { IPrivilegedDeviceService.class },
            (proxy, method, arguments) -> { throw new AssertionError("Device invoked before emergency verification"); });
        PatchCoordinator patch = new PatchCoordinator(context, device, message -> kotlin.Unit.INSTANCE);
        try { patch.run(NORMAL, new File(context.getFilesDir(), "absent-access.apk")); fail("Patch allowed"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("pending emergency")); }
        FirstSetupCoordinator.Transport transport = (FirstSetupCoordinator.Transport) java.lang.reflect.Proxy.newProxyInstance(
            getClass().getClassLoader(), new Class<?>[] { FirstSetupCoordinator.Transport.class },
            (proxy, method, arguments) -> { throw new AssertionError("Setup device invoked before emergency verification"); });
        FirstSetupCoordinator setup = new FirstSetupCoordinator(context, transport, message -> kotlin.Unit.INSTANCE);
        ApkIdentity identity = new ApkIdentity(1, NORMAL, "com.tencent.tmgp.osgame", 1,
            "private", GameSigner.CERTIFICATE_SHA256, false);
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(context.getFilesDir(), identity, identity, identity);
        try { setup.run(prepared, NORMAL, true, "unused-consent"); fail("Setup allowed"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("pending emergency")); }
        assertEquals("verification_pending", new EmergencyRestoreStore(context).snapshot().getString("status"));
    }

    @Test public void activeCoordinatorStopsInstallerIntentPublication() throws Exception {
        Context context = scopedContext();
        File sessions = new File(context.getFilesDir(), "sessions");
        assertTrue(sessions.mkdirs());
        EmergencyRestoreStore store = new EmergencyRestoreStore(context);
        try (java.io.RandomAccessFile file = new java.io.RandomAccessFile(new File(sessions, "coordinator.lock"), "rw");
             java.nio.channels.FileLock lock = file.getChannel().lock()) {
            try { store.begin(NORMAL); fail("Installer could race an active coordinator"); }
            catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("active patch or recovery")); }
            assertNull(store.snapshot());
        }
        assertEquals("verification_pending", store.begin(NORMAL).getString("status"));
    }
}
