package dev.halixm.hokacepatcher

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The loop guard of automatic Re-download (user decision 2026-11-13): the coordinator approves a freshly
 * measured plan itself, at most once per package in one run. Pure rule; the RunStore write that applies it
 * with the proposal (`proposeRedownload(automatic = true)`) is covered on a device by RunStoreProbeTest.
 */
class AutomaticRedownloadTest {
    private fun allowed(state: String? = RunStore.REDOWNLOAD_AWAITING, attempts: Int = 0,
                        redownloaded: List<String> = emptyList(), packages: List<String> = listOf("15")) =
        RunStore.automaticRedownloadAllowed(state, attempts, redownloaded, packages)

    @Test fun aFreshPlanIsApprovedAutomatically() {
        assertTrue(allowed())
        assertTrue(allowed(packages = listOf("1", "15")))
    }

    @Test fun aPackageAlreadyReDownloadedInThisRunIsNeverDeletedAgainByItself() {
        assertFalse(allowed(redownloaded = listOf("15")))
        // One repeated package holds back the whole plan, even beside new ones.
        assertFalse(allowed(redownloaded = listOf("15"), packages = listOf("1", "15")))
    }

    @Test fun anotherPackageAfterAnEarlierReDownloadIsStillApproved() {
        assertTrue(allowed(attempts = 1, redownloaded = listOf("15"), packages = listOf("21")))
    }

    @Test fun aChangedPlanBeforeAnyDeletionIsApprovedAgain() {
        // The changed plan replaces the approved one unanswered; nothing of it was deleted yet.
        assertTrue(allowed(state = RunStore.REDOWNLOAD_AWAITING, attempts = 1))
    }

    @Test fun aSpentDeletionBudgetWaitsForTheUser() {
        assertFalse(allowed(attempts = 2))
    }

    @Test fun onlyAnUnansweredPlanIsApproved() {
        for (state in RunStore.REDOWNLOAD_STATES - RunStore.REDOWNLOAD_AWAITING) assertFalse(state, allowed(state = state))
        assertFalse(allowed(state = null))
        assertFalse(allowed(packages = emptyList()))
    }
}
