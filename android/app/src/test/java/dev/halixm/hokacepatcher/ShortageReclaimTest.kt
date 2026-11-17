package dev.halixm.hokacepatcher

import java.io.File
import java.nio.file.Files
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

/** The pure selection behind the measured-shortage reclaim: retired snapshots and stale engine folders. */
class ShortageReclaimTest {
    private val first = "11111111-1111-4111-8111-111111111111"
    private val second = "22222222-2222-4222-8222-222222222222"
    private val current = "33333333-3333-4333-8333-333333333333"

    private fun journal() = JSONObject().put("packages_dirty", false).put("mutation_intent", JSONObject.NULL)
        .put("patch_payload_verified", false).put("snapshot_attempt", current)
        .put("retired_snapshots", JSONArray().put(first).put(second))

    @Test fun retiredSnapshotsAreReleasableOnlyFromAConsistentJournal() {
        assertEquals(listOf(first, second), RetiredSnapshots.releasable(journal()))
        assertTrue(RetiredSnapshots.releasable(journal().put("packages_dirty", true)).isEmpty())
        assertTrue(RetiredSnapshots.releasable(journal().put("mutation_intent", JSONObject().put("operation", "write_file"))).isEmpty())
        assertTrue(RetiredSnapshots.releasable(journal().put("patch_payload_verified", true)).isEmpty())
        assertTrue(RetiredSnapshots.releasable(JSONObject().put("mutation_intent", JSONObject.NULL)).isEmpty())
    }

    @Test fun currentAttemptReleasedAndMalformedIdsAreNeverReleasable() {
        val saved = journal().put("retired_snapshots", JSONArray().put(first).put(current).put("../snapshot").put(7))
            .put(RetiredSnapshots.RELEASED, JSONArray().put(second))
        assertEquals(listOf(first), RetiredSnapshots.releasable(saved))
        assertTrue(RetiredSnapshots.releasable(saved.put(RetiredSnapshots.RELEASED, JSONArray().put(first))).isEmpty())
    }

    @Test fun releasedListKeepsHistoryAndAddsEachIdOnce() {
        val saved = journal()
        val once = RetiredSnapshots.released(saved, first)
        saved.put(RetiredSnapshots.RELEASED, once)
        assertEquals(1, RetiredSnapshots.released(saved, first).length())
        assertEquals(2, saved.getJSONArray("retired_snapshots").length())
        assertEquals(listOf(second), RetiredSnapshots.releasable(saved))
    }

    private val now = "a".repeat(64)
    private val old = "b".repeat(64)
    private val pending = "c".repeat(64)
    private val linked = "d".repeat(64)

    private fun engineRoot(): File {
        val root = Files.createTempDirectory("engine-reclaim").toFile()
        for (name in listOf(now, old, pending, linked, "notes")) File(root, "$name/payload").apply { parentFile.mkdirs(); writeText("x") }
        File(root, "e".repeat(64)).writeText("a file, not a folder")
        return root
    }

    @Test fun onlyUnreferencedEarlierDigestFoldersAreStale() {
        val root = engineRoot()
        try {
            val target = File(root, "$linked/payload").canonicalPath
            val stale = EngineAssets.staleFolders(root, now, setOf(pending), listOf(target))
            assertEquals(listOf(old), stale!!.map { it.name })
            assertEquals(listOf(linked, old).sorted(), EngineAssets.staleFolders(root, now, setOf(pending), emptyList())!!.map { it.name })
        } finally { root.deleteRecursively() }
    }

    @Test fun missingEngineFolderReleasesNothingAndUnreadableRootRefuses() {
        val root = Files.createTempDirectory("engine-reclaim").toFile()
        try {
            assertEquals(emptyList<File>(), EngineAssets.staleFolders(File(root, "absent"), now, emptySet(), emptyList()))
            val file = File(root, "engine").apply { writeText("not a folder") }
            assertNull(EngineAssets.staleFolders(file, now, emptySet(), emptyList()))
        } finally { root.deleteRecursively() }
    }

    @Test fun linkedEngineFolderIsNeverStale() {
        val root = engineRoot()
        try {
            val link = File(root, "f".repeat(64))
            val made = runCatching { Files.createSymbolicLink(link.toPath(), File(root, old).toPath()) }.isSuccess
            assumeTrue("symbolic links unavailable", made)
            assertFalse(EngineAssets.staleFolders(root, now, setOf(pending), emptyList())!!.any { it.name == link.name })
        } finally { root.deleteRecursively() }
    }
}
