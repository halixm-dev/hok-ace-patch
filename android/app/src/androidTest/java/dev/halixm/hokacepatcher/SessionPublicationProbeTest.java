package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.util.AtomicFile;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import static org.junit.Assert.*;

/** Private initial-write interruption and published corruption checks; no device operations. */
public final class SessionPublicationProbeTest {
    private static final String HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private Context context() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "session-publication-probes/" + UUID.randomUUID());
        return new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
    }
    private static void write(File path, String value) throws Exception {
        DurableFiles.INSTANCE.createDirectories(path.getParentFile());
        AtomicFile atomic = new AtomicFile(path);
        FileOutputStream output = atomic.startWrite();
        try {
            output.write(value.getBytes(StandardCharsets.UTF_8)); output.getFD().sync();
            atomic.finishWrite(output); DurableFiles.INSTANCE.syncDirectory(path.getParentFile());
        } catch (Throwable error) { atomic.failWrite(output); throw error; }
    }
    private interface Action { void run() throws Exception; }
    private static void reject(Action action) throws Exception {
        try { action.run(); fail("Damaged or unpublished journal accepted"); }
        catch (Exception expected) { }
    }
    private IPrivilegedDeviceService noDevice() {
        return (IPrivilegedDeviceService) java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(),
            new Class<?>[] { IPrivilegedDeviceService.class },
            (proxy, method, arguments) -> { throw new AssertionError("A journal refusal invoked the device"); });
    }
    private FirstSetupCoordinator.Transport noSetupDevice() {
        return (FirstSetupCoordinator.Transport) java.lang.reflect.Proxy.newProxyInstance(getClass().getClassLoader(),
            new Class<?>[] { FirstSetupCoordinator.Transport.class },
            (proxy, method, arguments) -> { throw new AssertionError("A journal refusal invoked setup transport"); });
    }

    @Test public void initializedJournalIsPublishedAndReloaded() throws Exception {
        File parent = new File(context().getFilesDir(), "sessions");
        SessionJournal journal = SessionJournal.Companion.create(parent, HASH, HASH);
        assertEquals(journal.getId(), journal.getDirectory().getName());
        assertEquals(1, parent.listFiles().length);
        assertEquals(1, SessionJournal.Companion.history(parent).size());
        assertEquals(1, SessionJournal.Companion.pending(parent).size());
        assertEquals(journal.snapshot().toString(), SessionJournal.Companion.load(journal.getDirectory()).snapshot().toString());
        assertFalse(journal.getHasMutationIntent());
        assertFalse(journal.getDirtyPackages());
    }

    @Test public void incompleteAndCompleteUnpublishedDraftsCannotAuthorizeMutation() throws Exception {
        Context context = context();
        File parent = new File(context.getFilesDir(), "sessions");
        File empty = new File(parent, ".creating-" + UUID.randomUUID());
        assertTrue(empty.mkdirs());
        File partial = new File(parent, ".creating-" + UUID.randomUUID());
        write(new File(partial, "journal.json"), "{partial");
        SessionJournal journal = SessionJournal.Companion.create(parent, HASH, HASH);
        File complete = new File(parent, ".creating-" + journal.getId());
        assertTrue(journal.getDirectory().renameTo(complete));
        DurableFiles.INSTANCE.syncDirectory(parent);
        assertTrue(SessionJournal.Companion.history(parent).isEmpty());
        assertTrue(SessionJournal.Companion.pending(parent).isEmpty());
        reject(() -> SessionJournal.Companion.load(empty));
        reject(() -> SessionJournal.Companion.load(partial));
        reject(() -> SessionJournal.Companion.load(complete));
        ApkIdentity identity = new ApkIdentity(1, HASH, PrivilegedDeviceService.GAME, 1,
            "private", GameSigner.CERTIFICATE_SHA256, false);
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(context.getFilesDir(), UUID.randomUUID().toString()),
            identity, identity, identity);
        try {
            new FirstSetupCoordinator(context, noSetupDevice(), message -> kotlin.Unit.INSTANCE).run(prepared, HASH, false);
            fail("Missing consent accepted");
        } catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("data-loss consent")); }
        SessionJournal fresh = SessionJournal.Companion.create(parent, HASH, HASH);
        assertEquals(1, SessionJournal.Companion.history(parent).size());
        assertEquals(fresh.getId(), SessionJournal.Companion.pending(parent).get(0).getId());
    }

    @Test public void brokenPublishedJournalBlocksEveryMutationEntryPoint() throws Exception {
        Context context = context();
        File parent = new File(context.getFilesDir(), "sessions");
        File broken = new File(parent, UUID.randomUUID().toString());
        assertTrue(broken.mkdirs()); // A final UUID is published, so a missing journal must not be hidden.
        reject(() -> SessionJournal.Companion.history(parent));
        reject(() -> SessionJournal.Companion.pending(parent));
        reject(() -> new ApkPreparation(context).prepare(noDevice(), message -> kotlin.Unit.INSTANCE));
        reject(() -> new PatchCoordinator(context, noDevice(), message -> kotlin.Unit.INSTANCE)
            .run(HASH, new File(context.getFilesDir(), "absent.apk")));
        ApkIdentity identity = new ApkIdentity(1, HASH, PrivilegedDeviceService.GAME, 1,
            "private", GameSigner.CERTIFICATE_SHA256, false);
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(context.getFilesDir(), UUID.randomUUID().toString()),
            identity, identity, identity);
        reject(() -> new FirstSetupCoordinator(context, noSetupDevice(), message -> kotlin.Unit.INSTANCE)
            .run(prepared, HASH, true, "unused-consent"));
        reject(() -> new PatchRequestStore(context).confirm(prepared, true));
        reject(() -> new FirstSetupRequestStore(context).confirm(prepared, true, true));
    }

    @Test public void missingStateOrFalseCompletionIsNeverSilentlySkipped() throws Exception {
        for (int fault = 0; fault < 7; fault++) {
            File parent = new File(context().getFilesDir(), "sessions");
            SessionJournal journal = SessionJournal.Companion.create(parent, HASH, HASH);
            JSONObject value = journal.snapshot();
            switch (fault) {
                case 0: value.remove("mutation_intent"); break;
                case 1: value.remove("packages_dirty"); break;
                case 2: value.remove("normal_verified"); break;
                case 3: value.put("engine_id", "invalid"); break;
                case 4: value.put("phase", "UNKNOWN"); break;
                case 5: value.put("phase", "COMPLETE").put("normal_verified", true).put("packages_dirty", true); break;
                case 6: value.put("mutation_intent", new JSONObject().put("operation", "unknown").put("detail", new JSONObject())); break;
            }
            write(new File(journal.getDirectory(), "journal.json"), value.toString());
            reject(() -> SessionJournal.Companion.load(journal.getDirectory()));
            reject(() -> SessionJournal.Companion.pending(parent));
        }
        File parent = new File(context().getFilesDir(), "sessions");
        SessionJournal oversized = SessionJournal.Companion.create(parent, HASH, HASH);
        try (RandomAccessFile file = new RandomAccessFile(new File(oversized.getDirectory(), "journal.json"), "rw")) {
            file.setLength(1024 * 1024 + 1);
        }
        reject(() -> SessionJournal.Companion.load(oversized.getDirectory()));
    }

    @Test public void linkedPublishedDirectoriesCannotDisappearFromRecovery() throws Exception {
        File parent = new File(context().getFilesDir(), "sessions");
        DurableFiles.INSTANCE.createDirectories(parent);
        File dangling = new File(parent, UUID.randomUUID().toString());
        java.nio.file.Files.createSymbolicLink(dangling.toPath(), new File(parent, "missing-target").toPath());
        reject(() -> SessionJournal.Companion.history(parent));
        assertTrue(dangling.delete());
        File sourceParent = new File(context().getFilesDir(), "sessions");
        SessionJournal source = SessionJournal.Companion.create(sourceParent, HASH, HASH);
        File linked = new File(parent, source.getId());
        java.nio.file.Files.createSymbolicLink(linked.toPath(), source.getDirectory().toPath());
        reject(() -> SessionJournal.Companion.load(linked));
        reject(() -> SessionJournal.Companion.pending(parent));
    }
}
