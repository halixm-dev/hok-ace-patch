package dev.halixm.hokacepatcher

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Sizes people read: never "0.0 GB" for a file that has bytes, and no line for a release that freed nothing. */
class SizeLabelTest {
    @Test fun underOneGigabyteReadsInWholeMegabytes() {
        // The 2026-11-12 Re-download plan of package 1: 37,896,229 bytes.
        assertEquals("37 MB", StorageBudget.freeSpaceLabel(37_896_229L))
        assertEquals("999 MB", StorageBudget.freeSpaceLabel(999_999_999L))
        assertEquals("1 MB", StorageBudget.freeSpaceLabel(1_000_000L))
        assertEquals("<1 MB", StorageBudget.freeSpaceLabel(1L))
        assertEquals("0 MB", StorageBudget.freeSpaceLabel(0L))
    }

    @Test fun fromOneGigabyteReadsInDecimalGigabytesRoundedDown() {
        assertEquals("1.0 GB", StorageBudget.freeSpaceLabel(1_000_000_000L))
        assertEquals("2.4 GB", StorageBudget.freeSpaceLabel(2_499_999_999L))
    }

    @Test fun aHomeAppRestartReportsOnlyAReleasedGameApk() {
        assertNull(StorageBudget.replacedGameApksReport(0L))
        assertNull(StorageBudget.replacedGameApksReport(37_000_000L))
        assertNull(StorageBudget.replacedGameApksReport(StorageBudget.REPLACED_APK_MIN_BYTES - 1))
        assertEquals("Freed 2.4 GB of replaced game files the home screen app held",
            StorageBudget.replacedGameApksReport(2_400_000_000L))
    }
}
