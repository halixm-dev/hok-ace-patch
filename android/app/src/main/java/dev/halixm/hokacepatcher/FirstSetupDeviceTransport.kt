package dev.halixm.hokacepatcher

import android.content.Context
import android.os.ParcelFileDescriptor
import java.io.File

/** Fixed game-only Shizuku adapter; installer replies never substitute for installed verification. */
class FirstSetupDeviceTransport(private val context: Context, private val device: IPrivilegedDeviceService) :
    FirstSetupCoordinator.Transport {
    override fun verifyInstalled(expected: ApkIdentity) {
        InstalledGameVerifier(context, device).verify(expected)
        if (expected.certificateSha256 != GameSigner.CERTIFICATE_SHA256 && !expected.debuggable)
            device.validateFirstSetupSource(expected.sha256)
    }
    override fun gameAbsent(): Boolean = device.firstSetupGameAbsent()
    override fun forceStop() = device.forceStopGame()

    override fun uninstallVerified(expectedSource: ApkIdentity) {
        check(expectedSource.packageName == PrivilegedDeviceService.GAME && !expectedSource.debuggable &&
            expectedSource.certificateSha256 != GameSigner.CERTIFICATE_SHA256) { "Only an unconverted normal game can enter first setup" }
        verifyInstalled(expectedSource)
        device.removeGameForFirstSetup(expectedSource.sha256)
    }

    override fun installNormal(file: File, expected: ApkIdentity) {
        expected.requireRecovery()
        check(ApkIdentity.read(context, file) == expected) { "First setup recovery APK changed before installation" }
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use {
            device.installFirstSetupGame(it, expected.bytes)
        }
    }
}
