package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Iterator;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Read metadata from approved full scratch inputs; forced refusal preserves recovery material. */
public final class BuildStorageProbeTest {
    private static void removeOwnedCopy(File root, File path) throws Exception {
        assertFalse(Files.isSymbolicLink(path.toPath()));
        assertTrue(path.getCanonicalPath().equals(root.getCanonicalPath()) ||
            path.getCanonicalPath().startsWith(root.getCanonicalPath() + File.separator));
        if (path.isDirectory()) for (File child : java.util.Objects.requireNonNull(path.listFiles())) removeOwnedCopy(root, child);
        assertTrue(path.delete());
    }
    @Test public void testFullControlEstimateAndLowSpaceRefusal() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File base = new File(context.getFilesDir(), "scratch/control-1402-verified");
        File manifest = new File(context.getFilesDir(),
            "coordinator-full-probes/564d754c-ba01-4677-86d5-51ed53b3fa67/receipts/snapshot/manifest.json");
        assertTrue(manifest.isFile());
        File engine = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python python = Python.getInstance();
        python.getModule("android_bridge").callAttr("engine_preflight", engine.getPath());
        JSONObject source = new JSONObject(new String(Files.readAllBytes(manifest.toPath()), StandardCharsets.UTF_8));
        JSONObject sourceFiles = source.getJSONObject("files"), packageFiles = new JSONObject();
        File session = new File(context.getFilesDir(), "build-storage-probes/" + UUID.randomUUID());
        File snapshot = new File(session, "snapshot");
        assertTrue(snapshot.mkdirs());
        try {
            long retainedBytes = 0;
            for (Iterator<String> names = sourceFiles.keys(); names.hasNext();) {
                String name = names.next();
                if (!name.startsWith("packages/")) continue;
                GameFilePolicy.INSTANCE.validate(name, false);
                File original = new File(base, "game/WXQ_Data/Package/builtin/" + name.substring("packages/".length()));
                File retained = new File(snapshot, name);
                assertTrue(retained.getParentFile().isDirectory() || retained.getParentFile().mkdirs());
                Files.copy(original.toPath(), retained.toPath());
                packageFiles.put(name, sourceFiles.getJSONObject(name));
                retainedBytes += original.length();
            }
            source.put("files", packageFiles).put("bytes", retainedBytes);
            Files.write(new File(snapshot, "manifest.json").toPath(), source.toString().getBytes(StandardCharsets.UTF_8));
            JSONObject result = new JSONObject(python.getModule("android_bridge").callAttr("estimate_snapshot_build",
                engine.getPath(), session.getPath(), new File(base, "normal.apk").getPath()).toString());
            assertTrue(result.getBoolean("estimate_only"));
            JSONObject parts = result.getJSONObject("components");
            // Desktop reading of the same control (pristine 2026-10-03 layer, same APK prime): only the seven
            // packages holding catalog content are reserved, and only the APK packages the append reads.
            assertEquals(2, result.getInt("schema"));
            assertEquals(2718497695L, result.getLong("package_bytes"));
            assertEquals(37732352L, parts.getLong("prime_index_bytes"));
            assertEquals(588660736L, parts.getLong("prime_extraction_bytes"));
            assertEquals(916603132L, parts.getLong("staged_package_bytes"));
            long sum = 0; for (java.util.Iterator<String> keys = parts.keys(); keys.hasNext();) sum += parts.getLong(keys.next());
            assertEquals(sum, result.getLong("additional_bytes"));
            long normalBytes = new File(base, "normal.apk").length();
            assertEquals(2026631918L, normalBytes);
            long required = StorageBudget.INSTANCE.required(new long[]{result.getLong("additional_bytes"), normalBytes});
            assertTrue(required > result.getLong("additional_bytes") + normalBytes);
            try {
                StorageBudget.INSTANCE.requireAvailable(context.getFilesDir(), "forced offline build refusal",
                    new long[]{context.getFilesDir().getUsableSpace(), result.getLong("additional_bytes"), normalBytes});
                fail("Low-space build accepted without normal recovery reserve");
            } catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("keep recovery material")); }
            assertTrue(new File(base, "normal.apk").isFile());
            assertFalse(new File(session, "work").exists());
            assertFalse(new File(session, "out").exists());
            Files.write(new File(session, "estimate.json").toPath(), result.toString().getBytes(StandardCharsets.UTF_8));
            android.util.Log.i("HokAceProbe", "Build storage estimate " + result + " with recovery and margin " + required);
        } finally { removeOwnedCopy(snapshot, snapshot); }
    }
}
