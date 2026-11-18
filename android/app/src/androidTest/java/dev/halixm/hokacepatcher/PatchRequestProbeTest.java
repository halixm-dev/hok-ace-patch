package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.After;
import org.junit.Test;
import static org.junit.Assert.*;

/** Durable claims on validated private APK fixtures. No live device operations. */
public final class PatchRequestProbeTest {
    private final java.util.List<File> roots = new java.util.ArrayList<>();
    /** Each authorized run copies both fixture APKs (about 4 GB); never leave them on the phone. */
    @After public void deleteRoots() { for (File root : roots) DurableFiles.INSTANCE.deleteTree(root); }
    private Context context() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "patch-request-probes/" + UUID.randomUUID()); assertTrue(root.mkdirs());
        roots.add(root);
        return new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
    }
    @Test public void legacyConfirmationCannotBecomeFreshPermission() throws Exception {
        Context context = context();
        String id = UUID.randomUUID().toString();
        File path = new File(context.getFilesDir(), "patch-requests/" + id + ".json"); assertTrue(path.getParentFile().mkdirs());
        Files.write(path.toPath(), new JSONObject().put("schema", 1).put("id", id).put("consumed", false)
            .put("update_finished_and_game_closed", true).toString().getBytes(StandardCharsets.UTF_8));
        try { new PatchRequestStore(context).claim(id); fail("Legacy checkbox became permission"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("durable Start")); }
        try { new RunStore(context).load(id); fail("Legacy request supplied run authority"); }
        catch (Exception expected) { }
    }
    @Test public void claimBeforeJournalIsRecoverableAndCannotRetarget() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PrivateProbeFixtures fixture = PrivateProbeFixtures.load(actual); // Missing = explicit fixture gate.
        Context context = context();
        String id = AuthorizedProbeRun.create(context, fixture, "translate");
        PatchRequestStore requests = new PatchRequestStore(context);
        RunStore.Run first = RunStore.Companion.coordinator(context, () -> requests.claimRun(id, "translate", ShellProvider.SHIZUKU));
        assertEquals(id, first.getSessionId()); assertFalse(new File(context.getFilesDir(), "sessions/" + id).exists());
        // Simulated service death here. No consumed flag can discard the unfinished authorization.
        RunStore.Run second = RunStore.Companion.coordinator(context, () -> new PatchRequestStore(context).claimRun(id, "translate", ShellProvider.SHIZUKU));
        assertEquals(first.getSessionId(), second.getSessionId()); assertEquals(first.getAuthorizationKey(), second.getAuthorizationKey());
        for (ShellProvider other : new ShellProvider[]{ShellProvider.ROOT, ShellProvider.WIRELESS}) {
            try { RunStore.Companion.coordinator(context, () -> requests.claimRun(id, "translate", other)); fail("Provider retarget accepted"); }
            catch (Exception expected) { }
        }
        try { RunStore.Companion.coordinator(context, () -> requests.claimRun(id, "remove", ShellProvider.SHIZUKU)); fail("Action retarget accepted"); }
        catch (Exception expected) { }
        File sessions = new File(context.getFilesDir(), "sessions");
        SessionJournal child = SessionJournal.Companion.create(sessions, fixture.normal.getSha256(),
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", null, id, first.getAuthorizationKey());
        assertEquals(id, child.getRunId()); assertEquals(first.getAuthorizationKey(), child.getAuthorizationKey());
        // Repeated dispatch attaches to the same child and continues it (ADR 0010); it never builds a second
        // child. With no device the continuation fails before any change and keeps the one child's authority.
        IPrivilegedDeviceService noDevice = (IPrivilegedDeviceService) java.lang.reflect.Proxy.newProxyInstance(
            getClass().getClassLoader(), new Class<?>[]{IPrivilegedDeviceService.class},
            (proxy, method, arguments) -> { throw new IllegalStateException("No device in this probe"); });
        try { new PatchCoordinator(context, noDevice, message -> kotlin.Unit.INSTANCE).dispatch(id, "translate", ShellProvider.SHIZUKU); fail("Continuation without a device succeeded"); }
        catch (IllegalStateException expected) { }
        assertEquals(1, SessionJournal.Companion.history(sessions).size());
        SessionJournal attached = SessionJournal.Companion.load(child.getDirectory());
        assertEquals(id, attached.getRunId()); assertEquals(first.getAuthorizationKey(), attached.getAuthorizationKey());
        File receipt = new File(context.getFilesDir(), "preparations/" + first.getPreparation().getString("id") + "/receipt.json");
        Files.write(receipt.toPath(), "{}".getBytes(StandardCharsets.UTF_8));
        try { RunStore.Companion.coordinator(context, () -> requests.claimRun(id, "translate", ShellProvider.SHIZUKU)); fail("Tampered preparation accepted"); }
        catch (Exception expected) { }
        assertEquals("claimed", new RunStore(context).load(id).getLifecycle());
    }
}
