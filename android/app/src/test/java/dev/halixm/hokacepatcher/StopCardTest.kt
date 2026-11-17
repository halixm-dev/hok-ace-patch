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

    @Test fun aPatchRunDeletesStuckAndMixedFilesItself() {
        assertTrue(StopCard.damagedFiles("com.chaquo.python.PyException: PatchError: ${StopCard.UPDATE_STUCK}: package 1 (332 assets)"))
        assertTrue(StopCard.damagedFiles("PatchError: ${StopCard.UPDATE_MIXED}: package 15"))
        assertTrue(StopCard.damagedFiles("PatchError: ${StopCard.PACKAGE_UNREACHABLE}: package 15"))
        assertFalse(StopCard.damagedFiles("RuntimeError: 15_0.db: slot 0x1dd2c4 not in the B-tree"))
        assertFalse(StopCard.damagedFiles("PatchError: ${StopCard.UPDATE_WAITING}: package 1"))
        assertFalse(StopCard.damagedFiles("PatchError: ${StopCard.DOWNLOAD_UNFINISHED}: package 1"))
        assertFalse(StopCard.damagedFiles("PatchError: ${StopCard.CLEAR_DATA}"))
    }

    @Test fun aRedownloadNotYetFetchedWaitsForTheGame() {
        assertEquals(Exit.WAIT_FOR_GAME, error("PatchError: ${StopCard.UPDATE_WAITING}: package 1"))
    }

    // Xiaomi M2007J3SG, 2026-10-29: package 1060101007's folder without its index.
    @Test fun aPackageStillDownloadingWaitsForTheGame() {
        assertEquals(Exit.WAIT_FOR_GAME, error("PatchError: ${StopCard.DOWNLOAD_UNFINISHED}: package 1060101007"))
    }

    // Ticket 13: no Open game while unfinished work is unresolved; recovery comes first.
    @Test fun aDownloadWaitWithUnfinishedWorkRecoversBeforeOpenGame() {
        assertEquals(Exit.RECOVERY, error("PatchError: ${StopCard.UPDATE_WAITING}: package 1", pending = true))
        assertEquals(Exit.RECOVERY, error("PatchError: ${StopCard.DOWNLOAD_UNFINISHED}: package 1", pending = null))
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

    // Phone f15a72e, 2026-11-12: an update stuck on translated files never offers Re-download over unfinished work.
    @Test fun aStuckOrMixedUpdateWithUnfinishedWorkRecoversBeforeRedownload() {
        assertEquals(Exit.RECOVERY, error("PatchError: ${StopCard.UPDATE_STUCK}: package 1", pending = true))
        assertEquals(Exit.RECOVERY, error("PatchError: ${StopCard.UPDATE_MIXED}: package 15", pending = null))
    }

    private fun wait(status: String? = "waiting", pending: Boolean = false, mayContinue: Boolean = true,
                     waiting: String? = null, sourceDownloads: String? = null, needsAnswer: Boolean = false,
                     state: String? = null) =
        StopCard.savedWait(status, pending, mayContinue, waiting, sourceDownloads, needsAnswer, state)

    @Test fun aConsistentSavedActionShowsItsWait() {
        assertEquals(StopCard.Wait.STORAGE, wait(waiting = "storage"))
        assertEquals(StopCard.Wait.SOURCE_DOWNLOADS, wait(sourceDownloads = "required"))
        assertEquals(StopCard.Wait.REDOWNLOAD_ANSWER, wait(needsAnswer = true, state = RedownloadConsent.AWAITING))
        assertEquals(StopCard.Wait.REDOWNLOAD_DOWNLOAD, wait(state = RedownloadConsent.DELETED))
        assertNull(wait())
    }

    // Phone f15a72e, 2026-11-12: recovery_required with the access APK installed showed "Review Re-download".
    @Test fun requiredRecoveryLeadsBeforeEveryWait() {
        val status = "recovery_required"
        assertNull(wait(status = status, needsAnswer = true, state = RedownloadConsent.AWAITING))
        assertNull(wait(status = status, sourceDownloads = "required"))
        assertNull(wait(status = status, state = RedownloadConsent.DELETED))
        assertNull(wait(status = status, waiting = "storage"))
        assertNull(wait(pending = true, needsAnswer = true, state = RedownloadConsent.AWAITING))
        assertNull(wait(pending = true, sourceDownloads = "required"))
        assertNull(wait(pending = true, state = RedownloadConsent.DELETED))
        assertNull(wait(pending = true, waiting = "storage"))
    }

    @Test fun aStoppedActionOffersNoWait() {
        assertNull(wait(mayContinue = false, needsAnswer = true, state = RedownloadConsent.AWAITING))
    }
}
