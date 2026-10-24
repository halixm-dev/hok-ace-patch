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

    @Test fun theWorkerTakesTheShellPathAsUid2000AndTheRootPathAsUid0() {
        assertEquals(WorkerAccess.SHELL, WorkerAccess.of(2000))
        assertEquals(WorkerAccess.ROOT, WorkerAccess.of(0))
        assertThrows(IllegalStateException::class.java) { WorkerAccess.of(10234) }
        assertThrows(IllegalStateException::class.java) { WorkerAccess.of(1000) }
    }

    @Test fun rootsRefusalsAndSkippedStepsHaveIndonesian() {
        (RootWorkerStarter.REFUSALS + listOf(WorkerStep.ROOT_SKIPS_ACCESS, WorkerStep.ROOT_SKIPS_RESTORE,
            PatchCoordinator.ROOT_ACCESS_INSTALLED, PatchCoordinator.OTHER_PROVIDER)).forEach {
            assertNotEquals(it, UiText.translate("id", it))
            assertEquals(it, UiText.translate("en", it))
        }
    }

    @Test fun onlyTheRootLockGivesWhatItCreatesTheGamesOwnerAndLabel() {
        val shell = GameFileLock.script("own x")
        val root = GameFileLock.script("own x", root = true)
        assertFalse(shell.contains("chown") || shell.contains("chcon"))
        assertTrue(shell.contains("own() { :; }"))
        // Defined before the lock is opened and again inside the exec'd body, which does not inherit functions.
        assertEquals(2, Regex("chcon").findAll(root).count())
        assertTrue(root.contains("stat -c %C files/QtsVFSCache"))
        assertTrue(root.contains("umask 000"))
        assertTrue(root.contains("own 'files/QtsVFSCache/.hok-ace-patcher.lock'"))
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
