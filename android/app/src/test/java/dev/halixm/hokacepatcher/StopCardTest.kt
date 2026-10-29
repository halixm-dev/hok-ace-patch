package dev.halixm.hokacepatcher

import dev.halixm.hokacepatcher.StopCard.Exit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** ③ after a stop: the retained normal APK (recoverable true) never takes Start away from a stop that left nothing unfinished. */
class StopCardTest {
    private fun error(message: String, pending: Boolean? = false, recoverable: Boolean = true) =
        StopCard.decide("error", message, pending, recoverable)

    @Test fun aRunThatDidNotStopHasNoStopCard() {
        assertNull(StopCard.decide("complete", "", false, true))
        assertNull(StopCard.decide(null, "", false, true))
    }

    @Test fun anUpdateStuckOnTranslatedFilesOffersRedownload() {
        assertEquals(Exit.REDOWNLOAD_STUCK, error("PatchError: ${StopCard.UPDATE_STUCK}: package 1 (45 assets)"))
    }

    @Test fun anUpdateThatKeptPartOfTheTranslationOffersRedownload() {
        assertEquals(Exit.REDOWNLOAD_MIXED, error("PatchError: ${StopCard.UPDATE_MIXED}: package 15"))
    }

    @Test fun aRedownloadNotYetFetchedWaitsForTheGame() {
        assertEquals(Exit.WAIT_FOR_GAME, error("PatchError: ${StopCard.UPDATE_WAITING}: package 1"))
    }

    // Xiaomi M2007J3SG, 2026-10-29: package 1060101007's folder without its index.
    @Test fun aPackageStillDownloadingWaitsForTheGame() {
        assertEquals(Exit.WAIT_FOR_GAME, error("PatchError: ${StopCard.DOWNLOAD_UNFINISHED}: package 1060101007"))
    }

    @Test fun aProviderRefusalOffersStartEvenWithWorkPending() {
        assertEquals(Exit.START, error(WirelessDebugging.SWITCHED_OFF, pending = true))
        assertEquals(Exit.START, error(RootWorkerStarter.REFUSALS.first(), pending = true))
    }

    // 2026-10-29: a FileNotFoundError the worker recovered from left only "Open recovery options".
    @Test fun aStopThatRecoveredItselfOffersTryAgainDespiteTheRetainedApk() {
        val exit = error("FileNotFoundError: /data/.../1060101007.db", pending = false, recoverable = true)
        assertEquals(Exit.TRY_AGAIN, exit)
        assertFalse(StopCard.pointsAtRecovery(exit!!, recoverable = true))
    }

    @Test fun aStopWithUnfinishedWorkOpensRecovery() {
        val exit = error("Worker lost", pending = true)
        assertEquals(Exit.RECOVERY, exit)
        assertTrue(StopCard.pointsAtRecovery(exit!!, recoverable = true))
    }

    @Test fun unreadableRecordsOpenRecovery() {
        assertEquals(Exit.RECOVERY, error("Worker lost", pending = null))
    }

    @Test fun recoveryRequiredOpensRecoveryEvenWithAStuckUpdateLine() {
        assertEquals(Exit.RECOVERY, StopCard.decide("recovery_required", StopCard.UPDATE_STUCK, false, true))
    }

    @Test fun withNoRecoveryMaterialEveryStopOffersTryAgain() {
        assertEquals(Exit.TRY_AGAIN, error("Worker lost", pending = true, recoverable = false))
        assertEquals(Exit.TRY_AGAIN, StopCard.decide("recovery_required", "", true, false))
    }

    @Test fun onlyTheUpdateCardsReplaceTheStopsOwnLine() {
        assertEquals(setOf(Exit.REDOWNLOAD_STUCK, Exit.REDOWNLOAD_MIXED, Exit.WAIT_FOR_GAME), Exit.entries.filter(StopCard::ownCard).toSet())
    }
}
