package dev.halixm.hokacepatcher

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.file.FileSystems
import java.nio.file.Files

/**
 * 2026-11-20 phone run: APK sharing turned a new preparation's access APK into a link to an identical copy, the
 * claim refused it as a linked record, and the automatic retry, charged to no new attempt, repeated every 4 s.
 */
class SharedApkClaimTest {
    @get:Rule val folder = TemporaryFolder()

    private fun posix() = assumeTrue(FileSystems.getDefault().supportedFileAttributeViews().contains("posix"))

    private fun apk(root: File, path: String, readOnly: Boolean = true) = File(root, path).apply {
        parentFile.mkdirs(); writeText("apk"); if (readOnly) check(setReadOnly())
    }

    @Test fun acceptsALinkToAReadOnlyPrivateCopy() {
        posix()
        val base = folder.root.canonicalFile
        val kept = apk(base, "preparations/old/apks/access.apk")
        val shared = File(base, "preparations/new/apks/access.apk").apply { parentFile.mkdirs() }
        Files.createSymbolicLink(shared.toPath(), kept.toPath())
        RunStore.safeShared(base, shared)
        RunStore.safeShared(base, kept)
    }

    @Test fun refusesALinkToAWritableOrOutsideFile() {
        posix()
        val base = File(folder.root, "files").canonicalFile.apply { mkdirs() }
        val writable = apk(base, "preparations/old/apks/access.apk", readOnly = false)
        val outside = apk(folder.root, "outside.apk")
        for ((name, target) in listOf("a" to writable, "b" to outside)) {
            val link = File(base, "preparations/$name/apks/access.apk").apply { parentFile.mkdirs() }
            Files.createSymbolicLink(link.toPath(), target.toPath())
            assertThrows(IllegalStateException::class.java) { RunStore.safeShared(base, link) }
        }
    }

    @Test fun aRepeatedFailureBeforeAnyNewAttemptSpendsTheRetry() {
        val attempts = JSONObject().put("preparation", 1)
        assertTrue(RunStore.chargeFailure(attempts, null, "preparation"))
        assertFalse(RunStore.chargeFailure(attempts, "preparation", "preparation"))
        assertEquals(2, attempts.getInt("preparation"))
    }

    @Test fun aFailureAfterAnotherOperationKeepsItsOwnRetry() {
        val attempts = JSONObject().put("preparation", 1).put("snapshot", 1)
        assertTrue(RunStore.chargeFailure(attempts, "preparation", "snapshot"))
        assertFalse(RunStore.chargeFailure(JSONObject().put("snapshot", 2), "preparation", "snapshot"))
    }
}
