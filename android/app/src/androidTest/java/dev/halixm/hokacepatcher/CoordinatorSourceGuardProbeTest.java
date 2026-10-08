package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.os.Binder;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import org.junit.Test;
import static org.junit.Assert.*;

/** Reject mismatched or official source identity before any access APK or device call. */
public final class CoordinatorSourceGuardProbeTest {
    @Test public void testSourceRefusalBeforeAccess() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String hash = "b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a";
        File protectedNormal = new RecoveryStore(actual).normal(hash);
        ApkIdentity normal = ApkIdentity.Companion.read(actual, protectedNormal);
        File root = new File(actual.getFilesDir(), "coordinator-source-guards/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        File cached = new RecoveryStore(scoped).normal(hash); assertTrue(cached.getParentFile().mkdirs());
        Files.createSymbolicLink(cached.toPath(), protectedNormal.toPath());
        try (FileOutputStream output = new FileOutputStream(new File(cached.getParentFile(), "identity.json"))) {
            output.write(normal.json().toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
        }
        PatchCoordinator coordinator = new PatchCoordinator(scoped,
            IPrivilegedDeviceService.Stub.asInterface(new Binder()), message -> kotlin.Unit.INSTANCE);
        ApkIdentity wrongVersion = new ApkIdentity(normal.getBytes(), hash, normal.getPackageName(),
            normal.getVersionCode() + 1, normal.getVersionName(), normal.getCertificateSha256(), false);
        try { coordinator.run(hash, new File(root, "missing-access.apk"), wrongVersion); fail("Wrong source version accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("source and recovery versions")); }
        ApkIdentity official = new ApkIdentity(normal.getBytes(), hash, normal.getPackageName(),
            normal.getVersionCode(), normal.getVersionName(), "0000000000000000000000000000000000000000000000000000000000000000", false);
        try { coordinator.run(hash, new File(root, "missing-access.apk"), official); fail("Official source bypassed conversion"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("verified normal")); }
        assertEquals(1, new File(root, "sessions").listFiles().length); // Lock only; no mutation journal.
        assertEquals(hash, ApkIdentity.Companion.digest(protectedNormal));
    }
}
