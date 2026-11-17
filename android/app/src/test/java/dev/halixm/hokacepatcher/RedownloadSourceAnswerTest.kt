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
        Redownload("plan", sha, 3, listOf("1"), 37_896_229L, state,
            if (state in setOf(RedownloadConsent.APPROVED, RedownloadConsent.DELETING)) "approval" else null, null)

    @Test fun theConfirmedDownloadOfThisRunsOwnDeletionAnswers() {
        assertTrue(RedownloadConsent.answersSourceDownloads(true, consent(RedownloadConsent.DOWNLOADS_CONFIRMED), plan))
    }

    @Test fun anUnconfirmedOrUnfinishedPlanAnswersNothing() {
        for (state in RedownloadConsent.STATES - RedownloadConsent.DOWNLOADS_CONFIRMED) {
            assertFalse(state, RedownloadConsent.answersSourceDownloads(true, consent(state), plan))
        }
        assertFalse(RedownloadConsent.answersSourceDownloads(true, null, plan))
    }

    @Test fun aStoppedRunOrAnotherPlansDeletionAnswersNothing() {
        val confirmed = consent(RedownloadConsent.DOWNLOADS_CONFIRMED)
        assertFalse(RedownloadConsent.answersSourceDownloads(false, confirmed, plan))
        assertFalse(RedownloadConsent.answersSourceDownloads(true, confirmed, "b".repeat(64)))
        assertFalse(RedownloadConsent.answersSourceDownloads(true, confirmed, null))
        assertFalse(RedownloadConsent.answersSourceDownloads(true, confirmed, ""))
        assertFalse(RedownloadConsent.answersSourceDownloads(true, consent(RedownloadConsent.DOWNLOADS_CONFIRMED, "A".repeat(64)), "A".repeat(64)))
    }
}
