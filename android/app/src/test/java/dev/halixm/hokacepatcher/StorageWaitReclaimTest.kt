package dev.halixm.hokacepatcher

import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/**
 * The two storage gaps of the 2026-11-19 Wireless debugging cycle: APK preparation refused for space without
 * the measured-shortage reclaim, and a Start refused for space left a pending run that blocked Free up space.
 */
class StorageWaitReclaimTest {
    private val apk = 2_030_000_000L

    @Test fun preparationReclaimsOnceThenRemeasuresTheSameBudget() {
        val required = StorageBudget.required(apk, apk, apk, apk)
        var free = required - 1; var reclaims = 0
        val disk = object : File("unused") { override fun getUsableSpace() = free }
        val budget = ApkPreparation.requirePreparationSpace(disk, apk) { reclaims++; free = required }
        assertEquals(1, reclaims)
        assertEquals("APK preparation", budget.getString("phase"))
        assertEquals(required, budget.getLong("required_bytes"))
    }

    @Test fun preparationStillWaitsWhenTheReclaimIsNotEnough() {
        var free = 0L; var reclaims = 0
        val disk = object : File("unused") { override fun getUsableSpace() = free }
        try {
            ApkPreparation.requirePreparationSpace(disk, apk) { reclaims++; free = 1_000L }
            fail("Preparation went ahead short of space")
        } catch (shortage: StorageBudget.Shortage) {
            assertEquals(1, reclaims)
            assertEquals("APK preparation", shortage.phase)
            assertEquals(1_000L, shortage.availableBytes)
        }
    }

    @Test fun preparationWithEnoughSpaceNeverReclaims() {
        val disk = object : File("unused") { override fun getUsableSpace() = Long.MAX_VALUE }
        ApkPreparation.requirePreparationSpace(disk, apk) { fail("Reclaimed with enough space") }
    }

    private fun run(waiting: String?, stop: Boolean = false) = RunStore.Run(
        "11111111-1111-4111-8111-111111111111", "translate", "en", ShellProvider.WIRELESS,
        RunStore.Target("device", 0, PrivilegedDeviceService.GAME), "22222222-2222-4222-8222-222222222222",
        true, stop, "authorized", null, JSONObject(), "a".repeat(64), null, waiting = waiting)

    @Test fun freeSpaceRunsEverythingWithNoSavedAction() {
        assertEquals(PatchCoordinator.FreeSpaceScope.EVERYTHING, PatchCoordinator.freeSpaceScope(emptyList()))
    }

    @Test fun aStartRefusedForSpaceStillLetsFreeUpSpaceReclaim() {
        assertEquals(PatchCoordinator.FreeSpaceScope.SHORTAGE_RECLAIM, PatchCoordinator.freeSpaceScope(listOf(run("storage"))))
    }

    @Test fun everyOtherSavedActionStillRefusesFreeUpSpace() {
        for (pending in listOf(run(null), run("provider"), run("explicit_retry"), run("storage", stop = true))) {
            // One other action that waits for storage never unlocks the reclaim for this one.
            val scope = PatchCoordinator.freeSpaceScope(listOf(pending, run("storage")))
            assertEquals("${pending.waiting} stop=${pending.stopRequested}", PatchCoordinator.FreeSpaceScope.REFUSED, scope)
        }
    }
}
