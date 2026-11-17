package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.os.Binder;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.util.UUID;
import org.junit.Test;
import static org.junit.Assert.*;

/** Source identity and missing Start refuse before any fake or real device call. */
public final class CoordinatorSourceGuardProbeTest {
    @Test public void testSourceRefusalBeforeAccess() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PrivateProbeFixtures fixture = PrivateProbeFixtures.load(actual);
        File root = new File(actual.getFilesDir(), "coordinator-source-guards/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        String run = AuthorizedProbeRun.create(scoped, fixture, "translate");
        RunStore.Run authority = new RunStore(scoped).load(run);
        String preparation = authority.getPreparation().getString("id");
        ApkPreparation.Prepared actualPrepared = new ApkPreparation(scoped).load(preparation);
        ApkIdentity normal = fixture.normal;
        ApkIdentity wrongVersion = new ApkIdentity(normal.getBytes(), normal.getSha256(), normal.getPackageName(),
            normal.getVersionCode() + 1, normal.getVersionName(), normal.getCertificateSha256(), false);
        try {
            new PatchRequestStore(scoped).authorize(run, new ApkPreparation.Prepared(actualPrepared.getDirectory(), wrongVersion, normal, fixture.access));
            fail("Wrong source version accepted");
        } catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("source identity")); }
        ApkIdentity official = new ApkIdentity(normal.getBytes(), normal.getSha256(), normal.getPackageName(),
            normal.getVersionCode(), normal.getVersionName(), "0000000000000000000000000000000000000000000000000000000000000000", false);
        try {
            new PatchRequestStore(scoped).authorize(run, new ApkPreparation.Prepared(actualPrepared.getDirectory(), official, normal, fixture.access));
            fail("Official source bypassed conversion");
        } catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("data-loss consent")); }
        PatchCoordinator coordinator = new PatchCoordinator(scoped,
            IPrivilegedDeviceService.Stub.asInterface(new Binder()), message -> kotlin.Unit.INSTANCE);
        try { coordinator.run(normal.getSha256(), actualPrepared.getAccessFile()); fail("Old mutation entry accepted no Start dispatch"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("durable Start")); }
        assertTrue(SessionJournal.Companion.history(new File(root, "sessions")).isEmpty());
        assertEquals(normal.getSha256(), ApkIdentity.Companion.digest(fixture.normalFile));
    }
}
