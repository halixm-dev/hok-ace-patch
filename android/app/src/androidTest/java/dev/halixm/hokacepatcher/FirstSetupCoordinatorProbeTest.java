package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Private simulated installer only: never binds Shizuku or uninstalls the game. */
public final class FirstSetupCoordinatorProbeTest {
    private static final String SHA = "0000000000000000000000000000000000000000000000000000000000000000";
    private static final ApkIdentity NORMAL = new ApkIdentity(1, SHA, "com.tencent.tmgp.osgame", 1,
        "fixture", GameSigner.CERTIFICATE_SHA256, false);
    private static final ApkIdentity SOURCE = new ApkIdentity(1, SHA, NORMAL.getPackageName(), 1, "fixture", SHA, false);
    private static final ApkIdentity ACCESS = new ApkIdentity(1, SHA, NORMAL.getPackageName(), 1,
        "fixture", GameSigner.CERTIFICATE_SHA256, true);

    private static final class Fake implements FirstSetupCoordinator.Transport {
        ApkIdentity installed = SOURCE;
        int uninstalls, installs;
        Runnable afterRemoval;
        int fault;
        Fake(int fault) { this.fault = fault; }
        public void verifyInstalled(ApkIdentity expected) {
            if (!expected.equals(installed)) throw new IllegalStateException("Installed game changed");
        }
        public boolean gameAbsent() { return installed == null; }
        public void forceStop() { }
        public void uninstallVerified(ApkIdentity expected) {
            if (fault == 3) throw new IllegalStateException("Uninstall refused before removal");
            verifyInstalled(expected); installed = null; uninstalls++;
            if (afterRemoval != null) afterRemoval.run();
            if (fault == 4) {
                installed = new ApkIdentity(1, SHA, SOURCE.getPackageName(), 2, "changed", SHA, false);
                throw new IllegalStateException("Uninstall reply lost and another app appeared");
            }
            if (fault == 1) throw new IllegalStateException("Uninstall reply lost");
        }
        public void installNormal(File file, ApkIdentity expected) {
            assertNull(installed); installs++;
            if (fault == 6 || (fault == 5 && installs == 1)) throw new IllegalStateException("Installer rejected the app");
            installed = expected;
            if (fault == 2) throw new IllegalStateException("Install reply lost");
        }
    }

    @Test public void testSuccessAndLostRepliesAutomaticallyRestoreWithoutRepeatUninstall() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        for (int fault = 0; fault <= 2; fault++) {
            File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
            Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
            Fake fake = new Fake(fault);
            FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake,
                message -> kotlin.Unit.INSTANCE, expected -> { assertEquals(NORMAL, expected); return new File(root, "dummy.apk"); });
            ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
            try { coordinator.run(prepared, SHA, false); fail("Missing consent accepted"); }
            catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("data-loss consent")); }
            assertEquals(0, fake.uninstalls);
            assertEquals(0, fake.installs);
            JSONObject initial = coordinator.run(prepared, SHA, true);
            assertEquals("setup_waiting", initial.getString("status"));
            assertEquals(fault != 0, initial.optBoolean("automatic_recovery", false));
            FirstSetupJournal journal = FirstSetupJournal.Companion.pending(scoped).get(0);
            JSONObject result = coordinator.recover(journal.getId());
            assertEquals("setup_waiting", result.getString("status"));
            assertFalse(result.getBoolean("translation_started"));
            assertEquals(1, fake.uninstalls);
            assertEquals(1, fake.installs);
            try { coordinator.finishUpdate(journal.getId(), false); fail("Update ack missing"); }
            catch (IllegalStateException expected) { }
            assertEquals("setup_ready", coordinator.finishUpdate(journal.getId(), true).getString("status"));
            assertTrue(FirstSetupJournal.Companion.pending(scoped).isEmpty());
        }
    }

    @Test public void testChangedInstalledAppIsNeverDeletedDuringRecovery() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        Fake fake = new Fake(4);
        FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake,
            message -> kotlin.Unit.INSTANCE, expected -> new File(root, "dummy.apk"));
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
        try { coordinator.run(prepared, SHA, true); fail("Fault missing"); }
        catch (IllegalStateException expected) { }
        FirstSetupJournal journal = FirstSetupJournal.Companion.pending(scoped).get(0);
        try { coordinator.recover(journal.getId()); fail("Changed installed app accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("changed")); }
        assertEquals(1, fake.uninstalls);
        assertEquals(0, fake.installs);
        assertEquals(FirstSetupPhase.UNINSTALL_INTENT, FirstSetupJournal.Companion.load(journal.getDirectory()).getPhase());
    }
    @Test public void testRefusedRemovalCanStopWithOriginalAppVerified() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        Fake fake = new Fake(3);
        FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake,
            message -> kotlin.Unit.INSTANCE, expected -> new File(root, "dummy.apk"));
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
        JSONObject result = coordinator.run(prepared, SHA, true);
        assertTrue(result.getBoolean("automatic_recovery"));
        assertEquals("setup_cancelled", result.getString("status"));
        assertTrue(result.getBoolean("original_verified"));
        assertTrue(result.getBoolean("data_loss_may_have_happened"));
        assertFalse(result.getBoolean("translation_started"));
        assertEquals(0, fake.uninstalls); assertEquals(0, fake.installs);
        assertTrue(FirstSetupJournal.Companion.pending(scoped).isEmpty());
        File folder = new File(root, "first-setups").listFiles()[0];
        assertEquals(FirstSetupPhase.CANCELLED, FirstSetupJournal.Companion.load(folder).getPhase());
    }
    @Test public void testCancellationBeforeRemovalHasNoInstallerCalls() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        Fake fake = new Fake(0);
        FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake,
            message -> kotlin.Unit.INSTANCE, expected -> new File(root, "dummy.apk"));
        coordinator.cancel();
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
        try { coordinator.run(prepared, SHA, true); fail("Cancelled setup ran"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("cancelled before removal")); }
        assertEquals(0, fake.uninstalls); assertEquals(0, fake.installs);
        assertTrue(FirstSetupJournal.Companion.pending(scoped).isEmpty());
    }
    @Test public void testInstallerRetryIsBoundedAndLaterRecoveryWorks() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        for (int fault : new int[] {5, 6}) {
            File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
            Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
            Fake fake = new Fake(fault);
            FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake,
                message -> kotlin.Unit.INSTANCE, expected -> new File(root, "dummy.apk"));
            ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
            if (fault == 5) {
                JSONObject result = coordinator.run(prepared, SHA, true);
                assertEquals("setup_waiting", result.getString("status"));
                assertTrue(result.getBoolean("automatic_recovery"));
                assertEquals(NORMAL, fake.installed);
            } else {
                try { coordinator.run(prepared, SHA, true); fail("Persistent install failure hidden"); }
                catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("Installer rejected")); assertTrue(expected.getSuppressed().length > 0); }
                assertNull(fake.installed);
                FirstSetupJournal journal = FirstSetupJournal.Companion.pending(scoped).get(0);
                assertEquals(FirstSetupPhase.INSTALL_INTENT, journal.getPhase());
                assertFalse(journal.getNormalVerified());
                assertEquals("recovery_required", coordinator.pendingRecoveryResult().getString("status"));
                assertEquals(2, fake.installs);
                fake.fault = 0;
                assertEquals("setup_waiting", coordinator.recover(journal.getId()).getString("status"));
                assertEquals(NORMAL, fake.installed);
            }
            assertEquals(1, fake.uninstalls);
            assertEquals(fault == 5 ? 2 : 3, fake.installs);
        }
    }
    @Test public void testChangedRecoveryMaterialRefusesAutomaticInstallation() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        Fake fake = new Fake(1);
        java.util.concurrent.atomic.AtomicInteger checks = new java.util.concurrent.atomic.AtomicInteger();
        java.util.concurrent.atomic.AtomicBoolean repaired = new java.util.concurrent.atomic.AtomicBoolean();
        FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake, message -> kotlin.Unit.INSTANCE,
            expected -> { if (checks.incrementAndGet() > 1 && !repaired.get()) throw new IllegalStateException("Recovery cache changed");
                return new File(root, "dummy.apk"); });
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
        try { coordinator.run(prepared, SHA, true); fail("Changed recovery material accepted"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("reply lost"));
            assertTrue(expected.getSuppressed()[0].getMessage().contains("Recovery cache changed")); }
        assertEquals(1, fake.uninstalls); assertEquals(0, fake.installs); assertNull(fake.installed);
        FirstSetupJournal journal = FirstSetupJournal.Companion.pending(scoped).get(0);
        assertEquals(FirstSetupPhase.UNINSTALL_INTENT, journal.getPhase()); assertFalse(journal.getNormalVerified());
        repaired.set(true);
        assertEquals("setup_waiting", coordinator.recover(journal.getId()).getString("status"));
        assertEquals(1, fake.uninstalls); assertEquals(1, fake.installs);
    }
    @Test public void testCancellationAfterRemovalAndProgressFailureDoNotPreventRestore() throws Exception {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "first-setup-controller-probes/" + UUID.randomUUID());
        Context scoped = new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
        Fake fake = new Fake(1);
        FirstSetupCoordinator coordinator = new FirstSetupCoordinator(scoped, fake,
            message -> { throw new IllegalStateException("Progress storage unavailable"); }, expected -> new File(root, "dummy.apk"));
        fake.afterRemoval = coordinator::cancel;
        ApkPreparation.Prepared prepared = new ApkPreparation.Prepared(new File(root, UUID.randomUUID().toString()), SOURCE, NORMAL, ACCESS);
        JSONObject result = coordinator.run(prepared, SHA, true);
        assertEquals("setup_waiting", result.getString("status")); assertTrue(result.getBoolean("automatic_recovery"));
        assertTrue(WorkerStatus.INSTANCE.describe(result).contains("restored after a setup error"));
        assertFalse(result.has("counts")); assertFalse(result.getBoolean("translation_started"));
        assertEquals(NORMAL, fake.installed); assertEquals(1, fake.uninstalls); assertEquals(1, fake.installs);
        assertTrue(FirstSetupJournal.Companion.pending(scoped).get(0).getNormalVerified());
    }
}
