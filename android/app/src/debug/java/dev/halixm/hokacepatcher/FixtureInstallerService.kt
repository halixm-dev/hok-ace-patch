package dev.halixm.hokacepatcher

/** Debug-only real installer boundary; both APK and data targets are the fixed disposable fixture. */
class FixtureInstallerService : PrivilegedDeviceService() {
    override val installerPackage: String get() = FIXTURE
    override val dataPackage: String get() = FIXTURE
}
