package dev.halixm.hokacepatcher

import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Real storage guard and result rendering, using no Android/device transport. */
class StorageWaitTest {
    @Test fun shortageEvictsOptionalCacheOnceAndContinuesSameBudget() {
        var free = 0L; var evictions = 0
        val disk = object : File("unused") { override fun getUsableSpace() = free }
        val required = StorageBudget.required(100L, 200L)
        val result = StorageBudget.requireAvailable(disk, "snapshot", 100L, 200L, reclaim = {
            evictions++; free = required
        })
        assertEquals(1, evictions)
        assertEquals(required, result.getLong("required_bytes"))
        assertEquals(required, result.getLong("available_bytes"))
    }
    @Test fun sufficientSpaceRetainsCacheAndRemainingShortageStillWaits() {
        var free = StorageBudget.required(100L); var evictions = 0
        val disk = object : File("unused") { override fun getUsableSpace() = free }
        StorageBudget.requireAvailable(disk, "snapshot", 100L, reclaim = { evictions++ })
        assertEquals(0, evictions)
        free = 0
        try {
            StorageBudget.requireAvailable(disk, "snapshot", 100L, reclaim = { evictions++; free = 10L })
            fail("Remaining shortage proceeded")
        } catch (shortage: StorageBudget.Shortage) {
            assertEquals(1, evictions)
            assertEquals(StorageBudget.required(100L), shortage.requiredBytes)
            assertEquals(10L, shortage.availableBytes)
        }
    }
    @Test fun measuredGuardRaisesTypedWaitInsteadOfRetryFailure() {
        val empty = object : File("unused") { override fun getUsableSpace() = 0L }
        val error = try { StorageBudget.requireAvailable(empty, "snapshot", 100L); null }
            catch (error: IllegalStateException) { error }
        assertNotNull(error)
        assertEquals("Shortage", error!!.javaClass.simpleName)
        assertTrue(error.message!!.contains("bytes required, 0 available"))
    }
    @Test fun recoveryShortageWinsOverEarlierStageBudget() {
        val stage = StorageBudget.Shortage("snapshot", 8_000, 4_000)
        val recovery = StorageBudget.Shortage("normal restore", 3_000, 1_000)
        stage.addSuppressed(recovery)
        assertSame(recovery, StorageBudget.shortage(stage))
        assertNull(StorageBudget.shortage(IllegalStateException("not a measured shortage")))
    }
    @Test fun shortageCannotTurnUnresolvedRecoveryIntoSafeWaiting() {
        val shortage = StorageBudget.Shortage("normal restore", 2_000_000_000, 1_000_000_000)
        assertEquals("recovery_required", shortage.result(true).getString("status"))
        assertEquals("waiting", shortage.result(false).getString("status"))
        assertFalse(shortage.result(true).getBoolean("launch_allowed"))
    }
    @Test fun storageWaitingResultShowsMeasuredSpaceInsteadOfDeletionApproval() {
        val result = JSONObject().put("status", "waiting").put("reason", "storage")
            .put("error", "Insufficient storage for snapshot: 8214798243 bytes required, 4489297920 available; keep recovery material")
        assertTrue(WorkerStatus.describe(result).startsWith("Need 8.3 GB"))
        assertFalse(WorkerStatus.describe(result).contains("Re-download"))
    }
}
