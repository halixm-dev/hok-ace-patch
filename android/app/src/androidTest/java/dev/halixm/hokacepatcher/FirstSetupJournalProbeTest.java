package dev.halixm.hokacepatcher;

import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.util.UUID;
import android.content.Context;
import android.content.ContextWrapper;
import android.os.Binder;
import org.junit.Test;
import static org.junit.Assert.*;

/** First setup cannot masquerade as translated/recovered data while a fresh download is pending. */
public final class FirstSetupJournalProbeTest {
    @Test public void testUnpublishedInitializationCannotBlockOrAuthorizeSetup() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-init-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        File parent = new File(root, "first-setups");
        File unfinished = new File(parent, ".creating-" + UUID.randomUUID()); assertTrue(unfinished.mkdirs());
        assertTrue(FirstSetupJournal.Companion.pending(scoped).isEmpty());
        assertTrue(FirstSetupJournal.Companion.history(scoped).isEmpty());
        try { FirstSetupJournal.Companion.load(unfinished); fail("Unpublished directory accepted as a mutation journal"); }
        catch (IllegalArgumentException expected) { }
        String sha = "0000000000000000000000000000000000000000000000000000000000000000";
        ApkIdentity normal = new ApkIdentity(1, sha, "com.tencent.tmgp.osgame", 1, "fixture", GameSigner.CERTIFICATE_SHA256, false);
        ApkIdentity source = new ApkIdentity(1, sha, normal.getPackageName(), 1, "fixture", sha, false);
        ApkIdentity access = new ApkIdentity(1, sha, normal.getPackageName(), 1, "fixture", GameSigner.CERTIFICATE_SHA256, true);
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), source, normal, access);
        FirstSetupJournal published = FirstSetupJournal.Companion.create(parent, prepared, sha, true);
        assertEquals(published.getId(), published.getDirectory().getName());
        assertFalse(new File(parent, ".creating-" + published.getId()).exists());
        assertEquals(1, FirstSetupJournal.Companion.history(scoped).size());
        assertEquals(1, FirstSetupJournal.Companion.pending(scoped).size());
        published.beforeUninstall();
        assertEquals(FirstSetupPhase.UNINSTALL_INTENT, FirstSetupJournal.Companion.load(published.getDirectory()).getPhase());
        File corruptPublished = new File(parent, UUID.randomUUID().toString()); assertTrue(corruptPublished.mkdir());
        try { FirstSetupJournal.Companion.pending(scoped); fail("Missing published journal silently ignored"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("missing or oversized")); }
    }
    @Test public void testDataLossIntentAndUpdateWaitSurviveReload() {
        String sha = "0000000000000000000000000000000000000000000000000000000000000000";
        ApkIdentity normal = new ApkIdentity(1, sha, "com.tencent.tmgp.osgame", 1, "fixture", GameSigner.CERTIFICATE_SHA256, false);
        ApkIdentity source = new ApkIdentity(1, sha, normal.getPackageName(), 1, "fixture", sha, false);
        ApkIdentity access = new ApkIdentity(1, sha, normal.getPackageName(), 1, "fixture", GameSigner.CERTIFICATE_SHA256, true);
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        File parent = new File(root, "first-setups");
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), source, normal, access);
        try { FirstSetupJournal.Companion.create(parent, prepared, sha, false); fail("Missing data-loss consent accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("data-loss consent")); }
        assertFalse(root.exists());
        FirstSetupJournal journal = FirstSetupJournal.Companion.create(parent, prepared, sha, true);
        assertEquals(1, FirstSetupJournal.Companion.pending(scoped).size());
        try { new ApkPreparation(scoped).prepare(IPrivilegedDeviceService.Stub.asInterface(new Binder()), message -> kotlin.Unit.INSTANCE);
            fail("Preparation bypassed first setup"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("first-time setup")); }
        try { new PatchRequestStore(scoped).confirm(prepared, true); fail("Patch approval bypassed first setup"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("first-time setup")); }
        try { new PatchCoordinator(scoped, IPrivilegedDeviceService.Stub.asInterface(new Binder()), message -> kotlin.Unit.INSTANCE)
            .run(sha, new File(root, "missing-access.apk")); fail("Patch coordinator bypassed first setup"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("first-time setup")); }
        journal.beforeUninstall(); journal.interrupted("uninstall acknowledgment lost");
        journal = FirstSetupJournal.Companion.load(journal.getDirectory());
        assertEquals(FirstSetupPhase.UNINSTALL_INTENT, journal.getPhase());
        try { journal.result(); fail("Unverified normal installation reported ready"); }
        catch (IllegalStateException expected) { }
        journal.beforeInstall(); journal.interrupted("install acknowledgment lost");
        journal = FirstSetupJournal.Companion.load(journal.getDirectory());
        assertEquals(FirstSetupPhase.INSTALL_INTENT, journal.getPhase());
        journal.normalInstalled(normal);
        journal = FirstSetupJournal.Companion.load(journal.getDirectory());
        assertEquals("setup_waiting", journal.result().optString("status"));
        assertFalse(journal.result().optBoolean("translation_started", true));
        assertFalse(journal.result().has("counts"));
        assertTrue(WorkerStatus.INSTANCE.describe(journal.result()).contains("Translation has not started"));
        try { journal.updateFinished(false, normal); fail("Missing update confirmation accepted"); }
        catch (IllegalStateException expected) { }
        assertEquals(FirstSetupPhase.WAITING_FOR_GAME_UPDATE, journal.getPhase());
        journal.updateFinished(true, normal);
        String terminalHash = ApkIdentity.Companion.digest(new File(journal.getDirectory(), "journal.json"));
        journal.interrupted("Late worker destruction after completion");
        assertEquals(terminalHash, ApkIdentity.Companion.digest(new File(journal.getDirectory(), "journal.json")));
        assertEquals("setup_ready", FirstSetupJournal.Companion.load(journal.getDirectory()).result().optString("status"));
        assertTrue(FirstSetupJournal.Companion.pending(scoped).isEmpty());
    }
}
