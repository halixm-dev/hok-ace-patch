package dev.halixm.hokacepatcher;

import android.util.AtomicFile;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.util.UUID;
import static org.junit.Assert.*;

/** Exercise persisted recovery state and interrupted writes on the actual Android filesystem. */
@RunWith(AndroidJUnit4.class)
public final class JournalProbeTest {
    @Test public void testInterruptedJournalKeepsMutationAndRejectsCompletion() throws Exception {
        File parent = new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir(),
            "journal-probes/" + UUID.randomUUID());
        SessionJournal journal = SessionJournal.Companion.create(parent,
            new String(new char[64]).replace((char) 0, 'a'), new String(new char[64]).replace((char) 0, 'b'));
        journal.intent("install_access", new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
        journal.intent("install_normal", new JSONObject());
        journal.outcome(PatchPhase.NORMAL_RESTORED_FOR_BUILD, new JSONObject().put("normal_verified", true));
        journal.outcome(PatchPhase.BUILDING, new JSONObject());
        JSONObject counts = new JSONObject().put("text_tables", 391).put("applied_textures", 395)
            .put("skipped_tables", 1).put("skipped_textures", 0);
        journal.outcome(PatchPhase.STAGED, new JSONObject().put("counts", counts));
        journal.intent("install_access", new JSONObject());
        journal.outcome(PatchPhase.APPLY_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.APPLYING, new JSONObject());
        journal.intent("write_file", new JSONObject().put("relative", "packages/1/1.db"));
        // Simulate a process exiting before AtomicFile.finishWrite. The prior durable intent remains.
        AtomicFile storage = new AtomicFile(new File(journal.getDirectory(), "journal.json"));
        try (FileOutputStream unfinished = storage.startWrite()) {
            unfinished.write("{partial".getBytes(java.nio.charset.StandardCharsets.UTF_8));
            unfinished.getFD().sync();
        }
        SessionJournal loaded = SessionJournal.Companion.load(journal.getDirectory());
        assertTrue(loaded.getHasMutationIntent());
        assertTrue(loaded.getDirtyPackages());
        assertEquals(PatchPhase.APPLYING, loaded.getPhase());
        try {
            loaded.outcome(PatchPhase.COMPLETE, new JSONObject().put("normal_verified", true));
            fail("Dirty packages reported completion");
        } catch (IllegalStateException expected) { }
        loaded.recoveryRequired("Simulated process loss");
        SessionJournal recovery = SessionJournal.Companion.load(journal.getDirectory());
        assertTrue(recovery.getHasMutationIntent());
        assertTrue(recovery.getDirtyPackages());
        assertEquals(PatchPhase.RECOVERY_REQUIRED, recovery.getPhase());
        assertEquals(counts.toString(), recovery.snapshot().getJSONObject("counts").toString());
        try { recovery.terminalResult(); fail("Unresolved recovery reported results"); }
        catch (IllegalStateException expected) { }
        recovery.beginRecoveryNormal(new ApkIdentity(1L, recovery.getRecoveryId(), PrivilegedDeviceService.GAME,
            1L, "fixture", GameSigner.CERTIFICATE_SHA256, false));
        recovery = SessionJournal.Companion.load(recovery.getDirectory());
        assertTrue(recovery.getHasRecoveryNormalIntent()); assertTrue(recovery.getHasMutationIntent());
        assertTrue(recovery.getDirtyPackages()); assertFalse(recovery.snapshot().getBoolean("normal_verified"));
        recovery.recoveryNormalVerified();
        recovery = SessionJournal.Companion.load(recovery.getDirectory());
        assertFalse(recovery.getHasRecoveryNormalIntent()); assertTrue(recovery.getHasMutationIntent());
        assertTrue(recovery.getDirtyPackages()); assertTrue(recovery.snapshot().getBoolean("normal_verified"));
        recovery.outcome(PatchPhase.RESTORING, new JSONObject());
        try {
            recovery.outcome(PatchPhase.COMPLETE, new JSONObject().put("normal_verified", true));
            fail("Restoring dirty packages reported completion");
        } catch (IllegalStateException expected) { }
        recovery.outcome(PatchPhase.RESTORING, new JSONObject().put("packages_dirty", false)
            .put("patch_payload_verified", true));
        recovery.intent("install_normal", new JSONObject());
        recovery.recoveryRequired("Final install interruption");
        recovery = SessionJournal.Companion.load(recovery.getDirectory());
        recovery.outcome(PatchPhase.RESTORING, new JSONObject());
        recovery.outcome(PatchPhase.COMPLETE, new JSONObject().put("normal_verified", true));
        JSONObject complete = recovery.terminalResult();
        assertEquals("complete", complete.getString("status"));
        assertEquals(counts.toString(), complete.getJSONObject("counts").toString());
        // Rolled-back sessions must not report their planned translations as applied results.
        SessionJournal cancelled = SessionJournal.Companion.create(parent,
            new String(new char[64]).replace((char) 0, 'a'), new String(new char[64]).replace((char) 0, 'b'));
        cancelled.outcome(PatchPhase.RESTORING, new JSONObject().put("counts", counts));
        cancelled.outcome(PatchPhase.CANCELLED, new JSONObject().put("normal_verified", true));
        assertEquals("recovered", cancelled.terminalResult().getString("status"));
        assertFalse(cancelled.terminalResult().has("counts"));
        android.util.Log.i("HokAceProbe", "PASS: interrupted journal retains mutation/dirty state and rejects completion");
    }

    @Test public void testFixedPathsRejectTraversalAndMetadataWrites() {
        GameFilePolicy.INSTANCE.validate("packages/1/1_0.db", true);
        GameFilePolicy.INSTANCE.validate("packages/builtin/Globalindex/GlobalIndexPrime.data", false);
        String[] rejected = {"../files", "packages/1/../2.db", "packages/1/1.info",
            "packages/builtin/Globalindex/GlobalIndexPrime.data", "packages/1/2.db",
            "packages/1/1.db;echo", "Watchdog/../outside"};
        for (String path : rejected) {
            try { GameFilePolicy.INSTANCE.validate(path, true); fail("Accepted " + path); }
            catch (IllegalArgumentException expected) { }
        }
    }
}
