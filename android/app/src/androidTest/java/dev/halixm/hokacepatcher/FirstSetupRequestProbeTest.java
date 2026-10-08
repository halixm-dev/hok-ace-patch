package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.util.AtomicFile;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Synthetic unconverted source metadata; real private normal/access APK validation, no device binding or first-install PKI proof. */
public final class FirstSetupRequestProbeTest {
    private static JSONObject read(File path) throws Exception {
        return new JSONObject(new String(new AtomicFile(path).readFully(), StandardCharsets.UTF_8));
    }
    private static void write(File path, JSONObject value) throws Exception {
        assertTrue(path.getParentFile().isDirectory() || path.getParentFile().mkdirs());
        try (FileOutputStream output = new FileOutputStream(path)) {
            output.write(value.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
        }
    }
    @Test public void testApprovalBindingExpiryAndReplay() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "setup-request-probes/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        File approved = new File(actual.getFilesDir(), "apk-preparation-probes/e35858b5-ffdf-4fe6-b308-2db85cde3658/preparations/5b6215d9-b501-49f8-b587-33a25c8afedf");
        JSONObject receipt = read(new File(approved, "receipt.json"));
        receipt.getJSONObject("source").put("certificate_sha256", "0000000000000000000000000000000000000000000000000000000000000000");
        File preparation = new File(root, "preparations/" + UUID.randomUUID()); assertTrue(new File(preparation, "apks").mkdirs());
        write(new File(preparation, "receipt.json"), receipt);
        Files.createSymbolicLink(new File(preparation, "apks/access.apk").toPath(), new File(approved, "apks/access.apk").toPath());
        ApkIdentity source = ApkIdentity.Companion.fromJson(receipt.getJSONObject("source"));
        ApkIdentity normal = ApkIdentity.Companion.fromJson(receipt.getJSONObject("normal"));
        ApkIdentity access = ApkIdentity.Companion.fromJson(receipt.getJSONObject("access"));
        File cached = new RecoveryStore(scoped).normal(normal.getSha256()); assertTrue(cached.getParentFile().mkdirs());
        Files.createSymbolicLink(cached.toPath(), new RecoveryStore(actual).normal(normal.getSha256()).toPath());
        write(new File(cached.getParentFile(), "identity.json"), normal.json());
        ApkPreparation.Prepared selected = new ApkPreparation.Prepared(preparation, source, normal, access);
        FirstSetupRequestStore requests = new FirstSetupRequestStore(scoped);
        try { requests.confirm(selected, false, true); fail("Missing update confirmation accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("local data loss")); }
        try { requests.confirm(selected, true, false); fail("Missing Scan-to-login consent accepted"); }
        catch (IllegalStateException expected) { }
        try { requests.confirm(new ApkPreparation.Prepared(preparation, normal, normal, access), true, true); fail("Converted game accepted for first setup"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("already converted")); }
        assertFalse(new File(root, "setup-requests").exists());
        String request = requests.confirm(selected, true, true);
        ApkPreparation.Prepared verified = requests.claim(request);
        assertEquals(normal, verified.getNormal()); assertEquals(access, verified.getAccess());
        requests.begin(request, verified);
        assertTrue(read(new File(root, "setup-requests/" + request + ".json")).getBoolean("started"));
        try { requests.begin(request, verified); fail("Consent started two attempts"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("already started")); }
        assertTrue(read(new File(root, "setup-requests/" + request + ".json")).getBoolean("consumed"));
        try { requests.claim(request); fail("Approval reused"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("already used")); }
        String expired = requests.confirm(selected, true, true);
        File expiredFile = new File(root, "setup-requests/" + expired + ".json");
        write(expiredFile, read(expiredFile).put("confirmed_ms", System.currentTimeMillis() - 16 * 60 * 1000L));
        try { requests.claim(expired); fail("Expired approval accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("expired")); }
        String changed = requests.confirm(selected, true, true);
        write(new File(preparation, "receipt.json"), receipt.put("label_warning", "changed after confirmation"));
        try { requests.claim(changed); fail("Changed receipt accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("Prepared files changed")); }
        assertFalse(read(new File(root, "setup-requests/" + changed + ".json")).getBoolean("consumed"));
        assertEquals(normal.getSha256(), ApkIdentity.Companion.digest(new RecoveryStore(actual).normal(normal.getSha256())));
    }
}
