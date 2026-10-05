package dev.halixm.hokacepatcher;

import java.io.File;
import org.junit.Test;
import static org.junit.Assert.*;

/** Real budget failure and conservative clearing advice; no Android/game operations. */
public final class StorageMessageTest {
    @Test public void budgetFailureIncludesRecoverableAmounts() {
        File disk = new File(System.getProperty("java.io.tmpdir"));
        try {
            StorageBudget.INSTANCE.requireAvailable(disk, "forced refusal", new long[]{disk.getUsableSpace(), 1000000000L});
            fail("An allocation larger than the free disk space must be refused");
        } catch (IllegalStateException expected) {
            String explained = StorageBudget.INSTANCE.explainFailure(expected.getMessage(), 1000000000L);
            assertNotNull(explained); assertTrue(explained.contains("GB free for this step"));
            assertTrue(explained.contains("Free now: 1.0 GB"));
            assertTrue(explained.contains("Keep saved recovery files"));
        }
    }
    @Test public void requiredRoundsUpAndClearingAdviceMatchesShownNumbers() {
        String error = "Insufficient storage for APK preparation: 8511854056 bytes required, 5987654321 available; keep recovery material";
        assertEquals("Need 8.6 GB free for this step.\nFree now: 5.9 GB.\n" +
            "Clear at least 2.7 GB more, then try again.\nKeep saved recovery files.",
            StorageBudget.INSTANCE.explainFailure(error));
    }
    @Test public void tinyShortageIsNeverDisplayedAsZeroAndLocaleDoesNotChangeNumbers() {
        java.util.Locale prior = java.util.Locale.getDefault();
        try {
            java.util.Locale.setDefault(java.util.Locale.GERMANY);
            String text = StorageBudget.INSTANCE.explainFailure("1000000001 bytes required, 1000000000 available");
            assertTrue(text.contains("Need 1.1 GB")); assertTrue(text.contains("0.1 GB more"));
        } finally { java.util.Locale.setDefault(prior); }
    }
    @Test public void freedSpaceUsesCurrentAvailableAndStopsAskingForMore() {
        String error = "2000000000 bytes required, 1000000000 available";
        assertTrue(StorageBudget.INSTANCE.explainFailure(error, 2000000000L).startsWith("Enough space now"));
        assertTrue(StorageBudget.INSTANCE.explainFailure(error, 0L).contains("2.0 GB more"));
    }
    @Test public void unknownOrInvalidAmountsAreNotInvented() {
        assertNull(StorageBudget.INSTANCE.explainFailure("INSTALL_FAILED_INSUFFICIENT_STORAGE"));
        assertNull(StorageBudget.INSTANCE.explainFailure("9999999999999999999999 bytes required, 0 available"));
        assertNull(StorageBudget.INSTANCE.explainFailure("0 bytes required, 0 available"));
        assertNull(StorageBudget.INSTANCE.explainFailure("100 bytes required, 0 available", -1L));
    }
    @Test public void latestRecoveryShortageWinsAndHugeBudgetsDoNotOverflow() {
        assertTrue(StorageBudget.INSTANCE.explainFailure("9000000000 bytes required, 0 available; recovery stopped: 3000000000 bytes required, 1000000000 available")
            .startsWith("Need 3.0 GB"));
        assertTrue(StorageBudget.INSTANCE.explainFailure(Long.MAX_VALUE + " bytes required, 0 available").contains("GB more"));
        try { StorageBudget.INSTANCE.required(new long[]{Long.MAX_VALUE, 1}); fail("Overflow accepted"); }
        catch (ArithmeticException expected) { }
    }
}
