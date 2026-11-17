package dev.halixm.hokacepatcher

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * When a confirmed Re-download download also answers the source-download gate for the snapshot that deletion
 * made stale (the 2026-11-12 device cycle asked for Downloads finished twice). Pure rule; the RunStore write
 * and its one-use consumption are covered on a device by RunStoreProbeTest.
 */
class RedownloadSourceAnswerTest {
    private val plan = "a".repeat(64)
    private fun consent(state: String, sha: String = plan) =
        RunStore.Redownload("plan", sha, 3, listOf("1"), 37_896_229L, state,
            if (state in setOf(RunStore.REDOWNLOAD_APPROVED, RunStore.REDOWNLOAD_DELETING)) "approval" else null, null)

    @Test fun theConfirmedDownloadOfThisRunsOwnDeletionAnswers() {
        assertTrue(RunStore.redownloadAnswersSourceDownloads(true, consent(RunStore.REDOWNLOAD_DOWNLOADS_CONFIRMED), plan))
    }

    @Test fun anUnconfirmedOrUnfinishedPlanAnswersNothing() {
        for (state in RunStore.REDOWNLOAD_STATES - RunStore.REDOWNLOAD_DOWNLOADS_CONFIRMED) {
            assertFalse(state, RunStore.redownloadAnswersSourceDownloads(true, consent(state), plan))
        }
        assertFalse(RunStore.redownloadAnswersSourceDownloads(true, null, plan))
    }

    @Test fun aStoppedRunOrAnotherPlansDeletionAnswersNothing() {
        val confirmed = consent(RunStore.REDOWNLOAD_DOWNLOADS_CONFIRMED)
        assertFalse(RunStore.redownloadAnswersSourceDownloads(false, confirmed, plan))
        assertFalse(RunStore.redownloadAnswersSourceDownloads(true, confirmed, "b".repeat(64)))
        assertFalse(RunStore.redownloadAnswersSourceDownloads(true, confirmed, null))
        assertFalse(RunStore.redownloadAnswersSourceDownloads(true, confirmed, ""))
        assertFalse(RunStore.redownloadAnswersSourceDownloads(true, consent(RunStore.REDOWNLOAD_DOWNLOADS_CONFIRMED, "A".repeat(64)), "A".repeat(64)))
    }
}
