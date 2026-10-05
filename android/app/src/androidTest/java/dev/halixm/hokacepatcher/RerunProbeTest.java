package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.nio.file.AccessDeniedException;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Full already-English rerun in private scratch; denied hard links fall back to ordinary copies. */
@RunWith(AndroidJUnit4.class)
public final class RerunProbeTest {
    private static JSONObject json(File file) throws Exception {
        return new JSONObject(new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
    }
    @Test public void testAlreadyEnglishHasNoDuplicateAppendOrFileDrift() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertTrue("Not enough rerun staging space", context.getFilesDir().getUsableSpace() > 2L * 1024 * 1024 * 1024);
        File base = new File(context.getFilesDir(), "scratch/control-1402-verified");
        File session = new File(context.getFilesDir(), "scratch/rerun-english-" + UUID.randomUUID());
        assertTrue(session.mkdirs());
        JSONObject control = json(new File(base, "control.json"));
        JSONObject originals = json(new File(base, "control.json")).getJSONObject("verified_source_files");
        JSONObject existingStage = json(new File(base, "staged-hashes.json"));
        JSONObject inputs = control.getJSONObject("verified_source_files");
        File builtin = new File(base, "game/WXQ_Data/Package/builtin");
        Files.createSymbolicLink(new File(session, "normal.apk").toPath(), new File(base, "normal.apk").toPath());
        long sourceBytes = 0, stageBytes = 0;
        for (Iterator<String> names = inputs.keys(); names.hasNext();) {
            String name = names.next();
            sourceBytes += (existingStage.has(name) ? new File(base, "out/" + name) : new File(builtin, name)).length();
        }
        for (Iterator<String> names = existingStage.keys(); names.hasNext();) stageBytes += new File(base, "out/" + names.next()).length();
        assertTrue("Not enough composite source/staging/prime extraction space",
            context.getFilesDir().getUsableSpace() > sourceBytes + stageBytes + new File(base, "normal.apk").length() + 256L * 1024 * 1024);
        boolean linksDenied = false;
        for (Iterator<String> names = inputs.keys(); names.hasNext();) {
            String name = names.next();
            GameFilePolicy.INSTANCE.validate("packages/" + name, false);
            File source = existingStage.has(name) ? new File(base, "out/" + name) : new File(builtin, name);
            String expected = existingStage.has(name) ? existingStage.getString(name) : inputs.getString(name);
            assertEquals("Rerun source changed: " + name, expected, ApkIdentity.Companion.digest(source));
            File target = new File(session, "game/WXQ_Data/Package/builtin/" + name);
            assertTrue(target.getParentFile().isDirectory() || target.getParentFile().mkdirs());
            if (!linksDenied) {
                try { Files.createLink(target.toPath(), source.toPath()); }
                catch (AccessDeniedException denied) { linksDenied = true; Files.copy(source.toPath(), target.toPath()); }
            } else Files.copy(source.toPath(), target.toPath());
            inputs.put(name, expected);
        }
        try (FileOutputStream output = new FileOutputStream(new File(session, "control.json"))) {
            output.write(control.toString().getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
        }
        File root = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python.getInstance().getModule("android_bridge").callAttr("build_scratch", root.getPath(), session.getPath());
        JSONObject rerun = json(new File(session, "staged-hashes.json"));
        for (Iterator<String> names = rerun.keys(); names.hasNext();) {
            String name = names.next();
            assertTrue("Unexpected appended/staged file: " + name, inputs.has(name));
            assertEquals("Already-English output drift: " + name, inputs.getString(name), rerun.getString(name));
        }
        for (Iterator<String> names = originals.keys(); names.hasNext();) {
            String name = names.next();
            assertEquals("Pristine input mutated: " + name, originals.getString(name), ApkIdentity.Companion.digest(new File(builtin, name)));
        }
        for (Iterator<String> names = existingStage.keys(); names.hasNext();) {
            String name = names.next();
            assertEquals("Retained first stage mutated: " + name, existingStage.getString(name),
                ApkIdentity.Companion.digest(new File(base, "out/" + name)));
        }
        android.util.Log.i("HokAceProbe", "PASS: already-English rerun has no file drift; " + session.getName());
    }
}
