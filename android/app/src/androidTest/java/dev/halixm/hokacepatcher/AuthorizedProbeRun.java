package dev.halixm.hokacepatcher;

import android.content.Context;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import org.json.JSONObject;

/** Explicit validated fixture -> private copied preparation -> ordinary production Start/dispatch.
 * Never points production preparation loaders at links or at a real device transport.
 */
final class AuthorizedProbeRun {
    static String create(Context scoped, PrivateProbeFixtures fixture, String action) throws Exception {
        RunStore runs = new RunStore(scoped);
        RunStore.Run run = runs.start(action, "en", ShellProvider.SHIZUKU, RunStore.Target.Companion.local(scoped));
        File folder = new File(scoped.getFilesDir(), "preparations/" + UUID.randomUUID());
        File access = new File(folder, "apks/access.apk");
        Files.createDirectories(access.getParentFile().toPath());
        Files.copy(fixture.accessFile.toPath(), access.toPath());
        File normal = new RecoveryStore(scoped).normal(fixture.normal.getSha256());
        Files.createDirectories(normal.getParentFile().toPath());
        if (!normal.exists()) Files.copy(fixture.normalFile.toPath(), normal.toPath());
        Files.write(new File(normal.getParentFile(), "identity.json").toPath(), fixture.normal.json().toString().getBytes(StandardCharsets.UTF_8));
        JSONObject receipt = new JSONObject().put("schema", 1).put("source", fixture.normal.json())
            .put("normal", fixture.normal.json()).put("access", fixture.access.json())
            .put("engine_id", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        Files.write(new File(folder, "receipt.json").toPath(), receipt.toString().getBytes(StandardCharsets.UTF_8));
        ApkPreparation.Prepared prepared = new ApkPreparation(scoped).load(folder.getName());
        return new PatchRequestStore(scoped).authorize(run.getId(), prepared);
    }
}
