package dev.halixm.hokacepatcher

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** ② Start while work runs: "Step N of M · <step>" from the worker record's step key and total. */
class ProgressStepTest {
    private fun running(action: String, step: String?) = JSONObject().put("status", "running").put("action", action)
        .put("progress", "Opening game data access").also { if (step != null) it.put("step", step).put("steps", 6) }

    @Test fun aPatchStepReadsItsNumberTotalAndName() {
        assertEquals("Step 3 of 6 · Unlock access", UiText.step("en", running("patch", "unlock_access"))?.line)
        assertEquals(3, UiText.step("en", running("patch", "unlock_access"))?.number)
    }

    @Test fun indonesianNamesTheStepInIndonesian() {
        assertEquals("Langkah 1 dari 6 · Periksa game", UiText.step("id", running("prepare", "check_game"))?.line)
    }

    @Test fun removalNamesItsBuildAndWriteStepsForTheOriginalFiles() {
        assertEquals("Step 4 of 6 · Rebuild original files", UiText.step("en", running("remove", "build"))?.line)
        assertEquals("Step 5 of 6 · Write original files", UiText.step("en", running("remove", "write"))?.line)
        assertEquals("Step 5 of 6 · Write translation", UiText.step("en", running("patch", "write"))?.line)
    }

    /** The step keys a run of <action> records as it reports <messages>, in order. */
    private fun steps(action: String, vararg messages: String) =
        messages.runningFold(null as String?) { step, message -> WorkerStep.next(action, step, message) }.drop(1)

    @Test fun preparationReportsStepsOneAndTwoEvenWhenItReusesSavedApks() {
        assertEquals(listOf("check_game", "check_game", "prepare_files", "prepare_files"), steps("prepare",
            "Preparing verified recovery material", "Checking saved normal and access APKs",
            "Reusing verified saved APKs — no new APK copies needed", "Freed 1.0 GB by sharing identical saved APKs. Recovery copies kept."))
    }

    @Test fun aPatchCountsThreeToSixAcrossTheConfirmation() {
        assertEquals(listOf("unlock_access", "unlock_access", "unlock_access", "build", "write", "write", "restore_game_app"), steps("patch",
            "Preparing verified recovery material", "Opening game data access", "Saving complete game data and Watchdog snapshot",
            "Building text and graphics from the verified private snapshot", "Applying package file 21", "Applying package file 30",
            "Restoring normal game APK"))
    }

    @Test fun aFailedBuildRestoringTheGameAppIsNotStepSix() {
        assertEquals(listOf("unlock_access", "build", "build"), steps("remove",
            "Opening game data access", "Rebuilding the original game files from the pristine delta", "Restoring normal game APK"))
    }

    @Test fun recoveryAndFreeUpSpaceReportNoStep() {
        assertEquals(listOf(null, null), steps("recover", "Opening game data access", "Restoring normal game APK"))
        assertEquals(listOf(null), steps("free_space", "Checking the installed normal game app"))
    }

    private val preparedLog = listOf("09:21:12  Checking saved normal and access APKs",
        "09:21:58  Reusing verified saved APKs — no new APK copies needed")
    private fun savedWithLog(status: String, action: String) = JSONObject().put("status", status).put("action", action)
        .put("messages", JSONArray(preparedLog))

    @Test fun aPatchKeepsTheLogOfThePreparationItContinues() {
        assertEquals(preparedLog, WorkerStep.carriedMessages("patch", savedWithLog("prepared", "prepare")))
        assertEquals(preparedLog, WorkerStep.carriedMessages("remove", savedWithLog("prepared", "prepare")))
    }

    @Test fun otherRunsStartAFreshLog() {
        assertEquals(emptyList<String>(), WorkerStep.carriedMessages("prepare", savedWithLog("prepared", "prepare")))
        assertEquals(emptyList<String>(), WorkerStep.carriedMessages("recover", savedWithLog("prepared", "prepare")))
        assertEquals(emptyList<String>(), WorkerStep.carriedMessages("patch", savedWithLog("complete", "patch")))
        assertEquals(emptyList<String>(), WorkerStep.carriedMessages("patch", savedWithLog("cancelled", "prepare")))
        assertEquals(emptyList<String>(), WorkerStep.carriedMessages("patch", null))
    }

    @Test fun aStateWithoutAStepHasNoStepLine() {
        assertNull(UiText.step("en", running("patch", null)))
        assertNull(UiText.step("en", running("recover", "unlock_access")))
        assertNull(UiText.step("en", JSONObject().put("status", "complete")))
    }
}
