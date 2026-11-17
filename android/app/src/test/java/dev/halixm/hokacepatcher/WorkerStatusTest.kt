package dev.halixm.hokacepatcher

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.EOFException
import java.util.concurrent.TimeoutException

/** A saved action's wait names what it waits for; a check the provider's loss cut short is never a changed game app. */
class WorkerStatusTest {
    private fun waiting(reason: String) = WorkerStatus.describe(JSONObject().put("status", "waiting").put("reason", reason))

    @Test fun aDownloadWaitSaysToFinishTheDownloadsNotThatFilesAreDamaged() {
        val line = waiting(PatchCoordinator.SOURCE_DOWNLOADS)
        assertEquals(UiText.english("setup_update"), line)
        assertFalse(line.contains("Damaged"))
    }

    @Test fun theRedownloadWaitsKeepTheirLines() {
        assertEquals("Damaged game files need your review before they are deleted again. Nothing was deleted.",
            waiting(PatchCoordinator.REDOWNLOAD_CONSENT))
        assertEquals("Damaged files deleted. The translation waits until the game downloads them again.",
            waiting(PatchCoordinator.REDOWNLOAD_DOWNLOAD))
    }

    // Phone f15a72e, 2026-11-12: Wireless debugging dropped mid-check and the run read as INSTALLED_CHANGED.
    @Test fun aDeadWorkerOrEndedStreamIsAProviderLoss() {
        assertTrue(InstalledGameVerifier.providerLost(IllegalStateException("${InstalledGameVerifier.DIFFERENT_APP}: it is 0 bytes"), false))
        assertTrue(InstalledGameVerifier.providerLost(IllegalStateException("copy", EOFException()), true))
        assertTrue(InstalledGameVerifier.providerLost(TimeoutException(), true))
    }

    @Test fun aDifferentAppWithALiveWorkerStaysADifferentApp() {
        assertFalse(InstalledGameVerifier.providerLost(IllegalStateException("${InstalledGameVerifier.DIFFERENT_APP}: its contents differ"), true))
        assertFalse(InstalledGameVerifier.providerLost(IllegalStateException("Check failed."), true))
    }

    private fun stopped() = JSONObject().put("status", "stopped_consistent").put("action", "recover").put("phase", "CANCELLED")
    private val counts = JSONObject().put("text_tables", 120).put("applied_textures", 34).put("skipped_tables", 0).put("skipped_textures", 2)
    private fun journal(verified: Boolean = true, finalized: Boolean = true) = JSONObject().put("phase", "CANCELLED")
        .put("stopped", true).put("patch_payload_verified", verified).put("finalized", finalized).put("counts", counts)

    // Phone run 248572aa, 2026-11-12: Stop landed after the write was verified and the delta finalized; the game kept the translation.
    @Test fun aStopAfterTheVerifiedTranslationReportsTheTranslationAndItsCounts() {
        val result = WorkerStatus.afterStop(stopped(), journal())
        assertEquals("complete", result.getString("status"))
        assertTrue(result.getBoolean("stopped_after_finish"))
        val shown = UiText.result("en", result)!!
        assertEquals("Translation added", shown.heading)
        assertEquals("Text tables applied: 120", shown.items.first())
        assertFalse(WorkerStatus.describe(result).contains("Start when you want to patch again"))
        assertTrue(WorkerStatus.describe(result).startsWith("Patch complete."))
    }

    @Test fun aStopAfterAVerifiedRemovalReportsTheRemoval() {
        val result = WorkerStatus.afterStop(stopped(), journal().put("removed_count", 7))
        assertEquals("Translation removed", UiText.result("en", result)!!.heading)
    }

    @Test fun aStopAfterAnUnconfirmedLayerStaysUnconfirmed() {
        val result = WorkerStatus.afterStop(stopped(), journal().put("layer_unconfirmed", "Watchdog changed"))
        assertEquals("recovered_unconfirmed", result.getString("status"))
        assertFalse(result.has("counts"))
    }

    // Phone run 468d719c: a Stop mid-apply rolled the files back, so it is a plain stop.
    @Test fun aStopBeforeThePayloadWasVerifiedStaysAPlainStop() {
        for (record in listOf(journal(verified = false, finalized = false), journal(finalized = false), JSONObject())) {
            val result = WorkerStatus.afterStop(stopped(), record)
            assertEquals("stopped_consistent", result.getString("status"))
            assertFalse(result.has("counts"))
            assertNull(UiText.result("en", result))
        }
    }

    @Test fun otherResultsAreUnchanged() {
        for (status in listOf("complete", "recovered", "recovered_unconfirmed")) {
            val result = JSONObject().put("status", status)
            assertEquals(result.toString(), WorkerStatus.afterStop(JSONObject(result.toString()), journal()).toString())
        }
    }

    @Test fun theOriginalsProgressLinesAreTranslated() {
        assertEquals("Checking the original game files", UiText.english("progress_check_originals"))
        assertEquals("Restoring the original game files", UiText.english("progress_restore_originals"))
    }

    @Test fun theProviderLossLineReadsAsDisconnected() {
        assertTrue(InstalledGameVerifier.PROVIDER_LOST.contains("disconnected", true))
        assertFalse(InstalledGameVerifier.PROVIDER_LOST.contains(PatchCoordinator.INSTALLED_CHANGED))
    }
}
