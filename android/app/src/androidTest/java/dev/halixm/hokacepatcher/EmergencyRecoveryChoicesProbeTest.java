package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import java.io.File;
import java.nio.file.Files;
import java.util.UUID;
import static org.junit.Assert.*;

/** Private damaged-record selection checks; no installer or game calls. */
public final class EmergencyRecoveryChoicesProbeTest {
    private static final String HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private Context context() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "emergency-choice-probes/" + UUID.randomUUID());
        assertTrue(root.mkdirs());
        return new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
    }
    private void candidate(Context context, String hash, boolean debug) throws Exception {
        File folder = new File(context.getFilesDir(), "recovery/" + hash);
        assertTrue(folder.mkdirs());
        Files.write(new File(folder, "normal.apk").toPath(), new byte[] {1, 2, 3});
        ApkIdentity identity = new ApkIdentity(3, hash, "com.tencent.tmgp.osgame", 1,
            "private", GameSigner.CERTIFICATE_SHA256, debug);
        Files.write(new File(folder, "identity.json").toPath(), identity.json().toString().getBytes("UTF-8"));
    }
    @Test public void damagedPublishedJournalOffersExplicitSelectionButNeverVerifiesBytes() throws Exception {
        Context context = context();
        File broken = new File(context.getFilesDir(), "sessions/" + UUID.randomUUID());
        assertTrue(broken.mkdirs());
        candidate(context, HASH, false);
        EmergencyRecoveryChoices.Choices choice = new EmergencyRecoveryChoices(context).resolve(() -> {
            SessionJournal.Companion.pending(new File(context.getFilesDir(), "sessions"));
            throw new AssertionError("Damaged journal accepted");
        });
        assertTrue(choice.getNeedsSelection());
        assertEquals(java.util.Collections.singletonList(HASH), choice.getIds());
        assertTrue(broken.isDirectory());
        assertEquals(0, broken.listFiles().length);
        try { new RecoveryStore(context).verify(HASH); fail("Selection substituted for APK verification"); }
        catch (Exception expected) { }
        assertNull(new EmergencyRestoreStore(context).snapshot());
    }
    @Test public void pendingEmergencyIdentityOverridesBrokenPatchDiscovery() throws Exception {
        Context context = context();
        new EmergencyRestoreStore(context).begin(HASH);
        EmergencyRecoveryChoices.Choices choice = new EmergencyRecoveryChoices(context).resolve(() -> {
            throw new AssertionError("Pending emergency request consulted damaged journals");
        });
        assertFalse(choice.getNeedsSelection());
        assertEquals(java.util.Collections.singletonList(HASH), choice.getIds());
        assertEquals("verification_pending", new EmergencyRestoreStore(context).snapshot().getString("status"));
    }
    @Test public void damagedEmergencyIntentCannotBeReplacedByFallback() throws Exception {
        Context context = context();
        candidate(context, HASH, false);
        File intent = new File(context.getFilesDir(), "emergency-restore.json");
        Files.write(intent.toPath(), "{damaged".getBytes("UTF-8"));
        try { new EmergencyRecoveryChoices(context).resolve(() -> HASH); fail("Damaged emergency intent ignored"); }
        catch (Exception expected) { }
        assertEquals("{damaged", new String(Files.readAllBytes(intent.toPath()), "UTF-8"));
    }
    @Test public void accessAndLinkedCandidatesAreExcludedAndEmptyFallbackRefuses() throws Exception {
        Context context = context();
        candidate(context, HASH, true);
        String linked = HASH.replace('a', 'b');
        Files.createSymbolicLink(new File(context.getFilesDir(), "recovery/" + linked).toPath(),
            new File(context.getFilesDir(), "recovery/" + HASH).toPath());
        try { new EmergencyRecoveryChoices(context).resolve(() -> { throw new IllegalStateException("Journal unreadable"); });
            fail("Access or linked candidate offered"); }
        catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("no retained normal APK")); }
    }
}
