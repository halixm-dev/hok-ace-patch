package dev.halixm.hokacepatcher

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** ② Start's result states: a heading, a summary line, the run's own counts as a list, then the login note. */
class ResultStateTest {
    private fun complete(counts: JSONObject? = null) = JSONObject().put("status", "complete").also { if (counts != null) it.put("counts", counts) }
    private val counts = JSONObject().put("text_tables", 12345).put("applied_textures", 3).put("skipped_tables", 0).put("skipped_textures", 1)

    @Test fun translationAddedListsItsCountsThenTheLoginNote() {
        val result = UiText.result("en", complete(counts))!!
        assertEquals("Translation added", result.heading)
        assertEquals("Patch complete. Normal game app verified.", result.summary)
        assertEquals(listOf("Text tables applied: 12345", "Images applied: 3", "Text tables skipped: 0", "Images skipped: 1"), result.items)
        assertEquals("Log in with Scan to login. Direct WeChat or QQ login does not work with this game app.", result.note)
    }

    @Test fun translationAddedInIndonesian() {
        val result = UiText.result("id", complete(counts))!!
        assertEquals("Terjemahan diterapkan", result.heading)
        assertEquals("Tabel teks diterapkan: 12345", result.items.first())
    }

    @Test fun translationAddedWithoutCountsSaysSo() {
        val result = UiText.result("en", complete())!!
        assertEquals("Patch complete. Normal game app verified; result counts are unavailable.", result.summary)
        assertEquals(emptyList<String>(), result.items)
    }

    @Test fun translationRemovedListsRestoredFilesAndTheOfficialApp() {
        val result = UiText.result("en", complete().put("removed", 7))!!
        assertEquals("Translation removed", result.heading)
        assertEquals("Translation removed. Normal game app verified.", result.summary)
        assertEquals(listOf("Original game files restored: 7"), result.items)
        assertEquals("Keep using Scan to login. For the official app, reinstall the game from the store.", result.note)
    }

    @Test fun damagedFilesDeletedSendsThePlayerToTheGameUpdateFirst() {
        val result = UiText.result("en", complete().put("action", "redownload").put("redownloaded", 3).put("packages", 1))!!
        assertEquals("Damaged files deleted", result.heading)
        assertEquals(listOf("Package files deleted: 3"), result.items)
        assertEquals("Open the game, let it finish the update to the login screen, close it, then tap Start to patch again.", result.note)
        assertTrue(result.gameReady)
    }

    @Test fun translationWrittenHasNoCountsAndNoNote() {
        val result = UiText.result("id", JSONObject().put("status", "recovered_unconfirmed"))!!
        assertEquals("Terjemahan ditulis", result.heading)
        assertEquals(UiText.translate("id", WorkerStatus.UNCONFIRMED), result.summary)
        assertEquals(emptyList<String>(), result.items)
        assertEquals("", result.note)
    }

    @Test fun spaceFreedListsFreedAndFreeNow() {
        val state = JSONObject().put("status", "space_freed").put("freed_bytes", 2_000_000_000L).put("free_bytes", 5_000_000_000L)
        val result = UiText.result("en", state)!!
        assertEquals("Space freed", result.heading)
        assertEquals("Space freed. The record for switching languages and the saved game app were kept.", result.summary)
        assertEquals(listOf("Freed: 2.0 GB", "Free now: 5.0 GB"), result.items)
        assertEquals("", result.note)
    }

    /** A result that leaves the game ready to play leads with Open game; Space freed changed no game files. */
    @Test fun onlyResultsThatLeaveTheGameReadyOfferOpenGame() {
        assertTrue(UiText.result("en", complete(counts))!!.gameReady)
        assertTrue(UiText.result("en", complete().put("removed", 7))!!.gameReady)
        assertTrue(UiText.result("en", JSONObject().put("status", "recovered_unconfirmed"))!!.gameReady)
        assertFalse(UiText.result("en", JSONObject().put("status", "space_freed"))!!.gameReady)
    }

    @Test fun otherStatesAreNotResults() {
        assertNull(UiText.result("en", JSONObject().put("status", "error")))
    }
}
