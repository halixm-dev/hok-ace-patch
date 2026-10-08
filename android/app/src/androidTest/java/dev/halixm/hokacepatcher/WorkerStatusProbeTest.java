package dev.halixm.hokacepatcher;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Results preserve four distinct counts and keep stale progress/recovery visible. */
public final class WorkerStatusProbeTest {
    @Test public void testCompletionAndUnresolvedRecovery() throws Exception {
        JSONObject counts = new JSONObject().put("text_tables", 391).put("applied_textures", 395)
            .put("skipped_tables", 1).put("skipped_textures", 0);
        String complete = WorkerStatus.INSTANCE.describe(new JSONObject().put("status", "complete").put("counts", counts));
        assertTrue(complete.contains("Text tables applied: 391")); assertTrue(complete.contains("Images applied: 395"));
        assertTrue(complete.contains("Text tables skipped: 1")); assertTrue(complete.contains("Images skipped: 0"));
        String unresolved = WorkerStatus.INSTANCE.describe(new JSONObject().put("status", "recovery_required").put("counts", counts));
        assertTrue(unresolved.contains("Keep the game closed")); assertFalse(unresolved.contains("applied: 391"));
        assertTrue(WorkerStatus.INSTANCE.describe(new JSONObject().put("status", "running")).startsWith("Last saved progress:"));
    }
    @Test public void testInstallerFailuresKeepTheRecoveryRouteAndRawEvidence() throws Exception {
        String raw = "Device command failed (1): Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]";
        assertTrue(InstallerFailure.INSTANCE.explain(raw, "first_setup", true).contains("USB debugging (Security settings)"));
        JSONObject setup = new JSONObject().put("status", "recovery_required").put("action", "first_setup").put("error", raw);
        String message = WorkerStatus.INSTANCE.describe(setup);
        assertTrue(message.contains("Keep the game closed")); assertTrue(message.contains("Unlock it"));
        assertTrue(message.contains("Recover or finish game setup")); assertFalse(message.contains("Device command failed"));
        assertEquals(raw, setup.getString("error"));
        setup.put("action", "patch");
        assertTrue(WorkerStatus.INSTANCE.describe(setup).contains("Recover interrupted patch"));
        setup.put("status", "error");
        assertTrue(WorkerStatus.INSTANCE.describe(setup).contains("Retry the action after fixing it"));
        setup.put("error", "INSTALL_FAILED_INSUFFICIENT_STORAGE");
        assertTrue(WorkerStatus.INSTANCE.describe(setup).contains("Keep the patcher's recovery files"));
        setup.put("error", "INSTALL_FAILED_UPDATE_INCOMPATIBLE");
        assertTrue(WorkerStatus.INSTANCE.describe(setup).contains("Do not uninstall the game"));
        setup.put("error", "INSTALL_FAILED_ALREADY_EXISTS");
        assertTrue(WorkerStatus.INSTANCE.describe(setup).contains("do not repeat removal"));
        setup.put("error", "INSTALL_FAILED_USER_RESTRICTED; recovery stopped: INSTALL_FAILED_INSUFFICIENT_STORAGE");
        assertTrue(WorkerStatus.INSTANCE.describe(setup).contains("more free storage"));
        assertFalse(WorkerStatus.INSTANCE.describe(setup).contains("Unlock it"));
        setup.put("error", "Unrecognized failure");
        assertEquals("Stopped: Unrecognized failure", WorkerStatus.INSTANCE.describe(setup));
    }
}
