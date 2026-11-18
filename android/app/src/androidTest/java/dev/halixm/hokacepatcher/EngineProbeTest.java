package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Collections;
import java.util.UUID;
import org.json.JSONObject;

/** Device scratch-only checks. Logs the unavailable codecs rather than declaring full parity. */
@RunWith(AndroidJUnit4.class)
public final class EngineProbeTest {
    private static void deleteTree(File path) {
        if (!path.exists() && !Files.isSymbolicLink(path.toPath())) return;
        if (!Files.isSymbolicLink(path.toPath()) && path.isDirectory()) {
            File[] children = path.listFiles();
            if (children != null) for (File child : children) deleteTree(child);
        }
        assertTrue("Cannot delete probe dir: " + path, path.delete() || !path.exists());
    }

    @Test
    public void testEmbeddedRuntimeAndCoreCodecs() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String root = EngineAssets.INSTANCE.prepare(context).getAbsolutePath();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        String report = Python.getInstance().getModule("android_bridge")
            .callAttr("diagnostics", root).toString();
        android.util.Log.i("HokAceProbe", report);
        JSONObject result = new JSONObject(report);
        assertTrue(result.getString("python").startsWith("3.12."));
        assertTrue(result.getBoolean("lz4_roundtrip"));
        assertTrue(result.getBoolean("zstd_roundtrip"));
        assertTrue(result.getInt("catalog_tables") > 0);
        assertEquals(398, result.getInt("catalog_textures"));
        // The complete-codec build is the gate for running scratch pipeline tests.
        if (InstrumentationRegistry.getArguments().getString("requireFullCodecs", "false").equals("true")) {
            assertTrue(result.getBoolean("full_codec_gate"));
        }
    }

    @Test
    public void testEngineTreeStaysImmutableAcrossBuildImportsAndCleansStaleCaches() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File scopedRoot = new File(RunStore.Companion.privateRoot(actual), "engine-probes/" + UUID.randomUUID());
        assertTrue(scopedRoot.mkdirs());
        try {
            Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return scopedRoot; } };
            File engineRoot = EngineAssets.INSTANCE.prepare(scoped);
            String baselineKey = ArtifactReceipts.INSTANCE.identityKey(
                ArtifactReceipts.INSTANCE.treeManifest(engineRoot, Collections.emptySet()));
            if (!Python.isStarted()) Python.start(new AndroidPlatform(scoped));
            Python py = Python.getInstance();
            py.getModule("android_bridge").callAttr("engine_preflight", engineRoot.getAbsolutePath());
            assertTrue(py.getModule("sys").get("dont_write_bytecode").toBoolean());
            for (String module : new String[]{
                "build_storage", "extra_text", "lineup_codes", "config_bin", "pb_text",
                "mobile_graphics", "device_extensions", "mobile_snapshot", "build_device_patch"
            }) {
                py.getModule(module);
            }
            assertFalse("Bytecode cache written inside engine folder", new File(engineRoot, "tools/__pycache__").exists());
            assertEquals("Engine identity mutated by Python imports",
                baselineKey, ArtifactReceipts.INSTANCE.identityKey(
                    ArtifactReceipts.INSTANCE.treeManifest(engineRoot, Collections.emptySet())));

            File staleCache = new File(engineRoot, "tools/__pycache__/config_bin.cpython-312.pyc");
            assertTrue(staleCache.getParentFile().mkdirs());
            Files.write(staleCache.toPath(), "pyc".getBytes(StandardCharsets.UTF_8));
            File stalePartial = new File(engineRoot, "tools/extra_text.py.partial");
            Files.write(stalePartial.toPath(), "partial".getBytes(StandardCharsets.UTF_8));

            EngineAssets.INSTANCE.prepare(scoped);
            assertFalse(staleCache.getParentFile().exists());
            assertFalse(stalePartial.exists());
            assertEquals(baselineKey, ArtifactReceipts.INSTANCE.identityKey(
                ArtifactReceipts.INSTANCE.treeManifest(engineRoot, Collections.emptySet())));

            File unexpected = new File(engineRoot, "tools/__pycache__/unexpected.txt");
            assertTrue(unexpected.getParentFile().mkdirs());
            Files.write(unexpected.toPath(), "not-bytecode".getBytes(StandardCharsets.UTF_8));
            try {
                EngineAssets.INSTANCE.prepare(scoped);
                fail("Unexpected file inside __pycache__ was silently deleted or ignored");
            } catch (IllegalStateException expected) {
                assertTrue(expected.getMessage().contains("Unexpected item in bytecode cache"));
            }
        } finally {
            deleteTree(scopedRoot);
        }
    }
}
