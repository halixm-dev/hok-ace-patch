package dev.halixm.hokacepatcher

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** The shell provider choice, the worker's uid dispatch and the provider-specific strings. */
class ShellProviderTest {
    @Test fun eachProviderReadsBackFromTheKeyItIsSavedUnder() {
        ShellProvider.entries.forEach { assertEquals(it, ShellProvider.of(it.key)) }
        assertEquals(ShellProvider.entries.size, ShellProvider.entries.map { it.key }.toSet().size)
    }

    @Test fun nothingSavedOrAnUnknownKeyIsShizuku() {
        // A phone patched before the picker existed has nothing saved, so it keeps Shizuku.
        assertEquals(ShellProvider.SHIZUKU, ShellProvider.of(null))
        assertEquals(ShellProvider.SHIZUKU, ShellProvider.of("adb"))
        assertEquals(ShellProvider.SHIZUKU, ShellProvider.DEFAULT)
    }

    @Test fun theTwoNewProvidersAreTaggedBetaAndShizukuIsNot() {
        assertFalse(ShellProvider.SHIZUKU.beta)
        assertTrue(ShellProvider.WIRELESS.beta)
        assertTrue(ShellProvider.ROOT.beta)
        assertEquals(listOf(ShellProvider.SHIZUKU, ShellProvider.WIRELESS, ShellProvider.ROOT), ShellProvider.entries)
    }

    @Test fun theWorkerTakesTheShellPathOnlyAsUid2000() {
        assertEquals(WorkerAccess.SHELL, WorkerAccess.of(2000))
        assertThrows(IllegalStateException::class.java) { WorkerAccess.of(0) }
        assertThrows(IllegalStateException::class.java) { WorkerAccess.of(10234) }
    }

    @Test fun everyProviderNameAndTheRootedShizukuRefusalHaveIndonesian() {
        ShellProvider.entries.forEach { assertTrue(it.label, UiText.translate("id", it.label).isNotEmpty()) }
        assertEquals("Debugging nirkabel", UiText.translate("id", ShellProvider.WIRELESS.label))
        assertNotEquals(ShellProvider.SHIZUKU_AS_ROOT, UiText.translate("id", ShellProvider.SHIZUKU_AS_ROOT))
        assertEquals(ShellProvider.SHIZUKU_AS_ROOT, UiText.translate("en", ShellProvider.SHIZUKU_AS_ROOT))
    }

    @Test fun gameMissingNamesNoProvider() {
        ShellProvider.entries.forEach { assertFalse(PrivilegedDeviceService.GAME_MISSING.contains(it.label, ignoreCase = true)) }
    }
}
