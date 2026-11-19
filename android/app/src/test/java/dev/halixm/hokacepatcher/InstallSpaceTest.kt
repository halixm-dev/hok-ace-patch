package dev.halixm.hokacepatcher

import org.junit.Assert.assertArrayEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.util.zip.CRC32
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * An APK install holds the staged APK, its installed size and Android's low-storage reserve at once: the
 * 2026-11-19 phone run failed to restore the normal APK with 4.1 GB free while one APK was budgeted.
 */
class InstallSpaceTest {
    @get:Rule val folder = TemporaryFolder()

    @Test fun countsTheStagedCopyTheExtractedLibrariesAndTheReserve() {
        val apk = folder.newFile("game.apk")
        ZipOutputStream(apk.outputStream()).use { zip ->
            fun put(name: String, size: Int, stored: Boolean = false) {
                val bytes = ByteArray(size)
                val entry = ZipEntry(name)
                if (stored) {
                    entry.method = ZipEntry.STORED
                    entry.size = size.toLong()
                    entry.crc = CRC32().apply { update(bytes) }.value
                }
                zip.putNextEntry(entry); zip.write(bytes); zip.closeEntry()
            }
            put("classes.dex", 5_000)
            put("lib/arm64-v8a/libunity.so", 70_000)
            put("lib/arm64-v8a/libil2cpp.so", 30_000)
            put("lib/arm64-v8a/libstored.so", 9_000, stored = true) // Installed in place, never extracted.
            put("assets/lib/fake.so", 4_000)
        }
        val bytes = apk.length()
        assertArrayEquals(longArrayOf(bytes, bytes + 100_000, 500L * 1024 * 1024),
            StorageBudget.installAllocations(apk, bytes))
    }
}
