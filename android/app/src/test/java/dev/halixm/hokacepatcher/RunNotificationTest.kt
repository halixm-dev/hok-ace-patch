package dev.halixm.hokacepatcher

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The notification a finished run posts: a result that leaves the game ready offers Open game; a failure says Work stopped. */
class RunNotificationTest {
    private fun state(status: String) = JSONObject().put("status", status)

    @Test fun translationAddedOffersOpenGame() {
        val note = RunNotification.of("en", state("complete").put("counts", JSONObject().put("text_tables", 1)
            .put("applied_textures", 2).put("skipped_tables", 0).put("skipped_textures", 0)))!!
        assertEquals("Translation added", note.title)
        assertEquals("Patch complete. Normal game app verified.", note.text)
        assertTrue(note.openGame)
    }

    @Test fun removedAndWrittenOfferOpenGame() {
        assertEquals("Translation removed", RunNotification.of("en", state("complete").put("removed", 3))!!.title)
        assertTrue(RunNotification.of("en", state("recovered_unconfirmed"))!!.openGame)
    }

    @Test fun aFailureSaysWorkStoppedAndOpensThePatcher() {
        for (status in listOf("error", "recovery_required")) {
            val note = RunNotification.of("en", state(status).put("error", "ERROR: raw"))!!
            assertEquals("Work stopped", note.title)
            assertEquals("Tap to see what happened and what to do next.", note.text)
            assertFalse(note.openGame)
        }
    }

    @Test fun inIndonesian() {
        assertEquals("Terjemahan diterapkan", RunNotification.of("id", state("complete"))!!.title)
    }

    /** Steps the automatic flow chains (verify, prepare), a stop the player asked for, and Space freed stay quiet. */
    @Test fun otherOutcomesPostNothing() {
        for (status in listOf("prepared", "verified", "cancelled", "running", "space_freed")) {
            assertNull(status, RunNotification.of("en", state(status)))
        }
    }
}
