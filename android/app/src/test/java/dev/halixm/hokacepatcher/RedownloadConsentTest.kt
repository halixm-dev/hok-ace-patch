package dev.halixm.hokacepatcher

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Re-download consent state changes and the record they are saved as, without a Context or a store. RunStore
 * persists these values under its lock; RunStoreProbeTest covers that write on a device.
 */
class RedownloadConsentTest {
    private val sha = "a".repeat(64)
    private val other = "b".repeat(64)
    private val planId = "00000000-0000-4000-8000-000000000001"
    private val approvalId = "00000000-0000-4000-8000-000000000002"
    private fun fresh() = RedownloadConsent.proposed(null, planId, sha, 3, listOf("12", "40"), 1_000L)

    @Test fun aSameDigestKeepsItsAnswerAndFollowsTheNewestFolder() {
        val declined = RedownloadConsent.declined(fresh(), sha)
        val again = RedownloadConsent.proposed(declined, "00000000-0000-4000-8000-000000000009", sha, 3, listOf("12", "40"), 1_000L)
        assertEquals(RedownloadConsent.DECLINED, again.state)
        assertEquals("00000000-0000-4000-8000-000000000009", again.planId)
    }

    @Test fun aChangedDigestOrAConsumedPlanStartsUnanswered() {
        val approved = RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_USER, approvalId, 5L)
        val changed = RedownloadConsent.proposed(approved, planId, other, 4, listOf("12"), 9L)
        assertEquals(RedownloadConsent.AWAITING, changed.state); assertNull(changed.approvalId)
        val deleted = RedownloadConsent.progressed(RedownloadConsent.progressed(approved, sha, RedownloadConsent.DELETING, true),
            sha, RedownloadConsent.DELETED, true)
        val reproposed = RedownloadConsent.proposed(deleted, planId, sha, 3, listOf("12", "40"), 1_000L)
        assertEquals(RedownloadConsent.AWAITING, reproposed.state); assertNull(reproposed.approvalId)
    }

    @Test fun onlyAnUnansweredPlanOfTheSameDigestTakesAnAnswer() {
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.answerable(null, sha) }
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.answerable(fresh(), other) }
        val approved = RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_AUTOMATIC, approvalId, 5L)
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.declined(approved, sha) }
        assertTrue(RedownloadConsent.answerable(RedownloadConsent.declined(fresh(), sha), sha).needsAnswer)
    }

    @Test fun deletionNeedsAnApprovalAndARunThatMayContinue() {
        val approved = RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_USER, approvalId, 5L)
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.progressed(fresh(), sha, RedownloadConsent.DELETING, true) }
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.progressed(approved, sha, RedownloadConsent.DELETING, false) }
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.progressed(approved, sha, RedownloadConsent.DELETED, true) }
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.progressed(approved, sha, RedownloadConsent.APPROVED, true) }
        val deleting = RedownloadConsent.progressed(approved, sha, RedownloadConsent.DELETING, true)
        // A finished deletion is recorded even after a Stop.
        assertEquals(RedownloadConsent.DELETED, RedownloadConsent.progressed(deleting, sha, RedownloadConsent.DELETED, false).state)
    }

    @Test fun aSpentBudgetAsksTheSamePlanAgainAndDownloadsFollowDeletion() {
        val approved = RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_AUTOMATIC, approvalId, 5L)
        val fresher = RedownloadConsent.awaitingFreshConsent(approved, sha)
        assertEquals(RedownloadConsent.AWAITING, fresher.state); assertNull(fresher.approvalSource); assertNull(fresher.approvedMs)
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.awaitingFreshConsent(fresher, sha) }
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.downloadsConfirmed(approved) }
        val deleted = RedownloadConsent.progressed(RedownloadConsent.progressed(approved, sha, RedownloadConsent.DELETING, true),
            sha, RedownloadConsent.DELETED, true)
        assertEquals(RedownloadConsent.DOWNLOADS_CONFIRMED, RedownloadConsent.downloadsConfirmed(deleted).state)
    }

    @Test fun everySavedStateRoundTripsThroughItsRecord() {
        val approved = RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_AUTOMATIC, approvalId, 5L)
        val deleting = RedownloadConsent.progressed(approved, sha, RedownloadConsent.DELETING, true)
        for (plan in listOf(fresh(), RedownloadConsent.declined(fresh(), sha), approved, deleting)) {
            val record = RedownloadConsent.encode(plan)
            RedownloadConsent.validate(record)
            assertEquals(plan, RedownloadConsent.decode(record))
        }
    }

    @Test fun aLegacyApprovalKeepsItsShapeAndReadsAsTheUsers() {
        val record = RedownloadConsent.encode(RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_USER, approvalId, 5L))
        record.getJSONObject("approval").remove("source")
        RedownloadConsent.validate(record)
        val legacy = RedownloadConsent.decode(record)
        assertEquals(RedownloadConsent.APPROVAL_USER, legacy.approvalSource); assertTrue(legacy.legacyApproval)
        val deleting = RedownloadConsent.encode(RedownloadConsent.progressed(legacy, sha, RedownloadConsent.DELETING, true))
        assertFalse(deleting.getJSONObject("approval").has("source"))
    }

    @Test fun aRecordInconsistentWithItsStateIsRefused() {
        val unanswered = RedownloadConsent.encode(fresh())
        unanswered.put("approval", JSONObject().put("id", approvalId).put("approved_ms", 5L).put("source", "user"))
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.validate(unanswered) }
        val approved = RedownloadConsent.encode(RedownloadConsent.approved(fresh(), RedownloadConsent.APPROVAL_USER, approvalId, 5L))
        approved.put("approval", JSONObject.NULL)
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.validate(approved) }
        val duplicate = RedownloadConsent.encode(fresh()).put("packages", org.json.JSONArray(listOf("12", "12")))
        assertThrows(IllegalStateException::class.java) { RedownloadConsent.validate(duplicate) }
    }
}
