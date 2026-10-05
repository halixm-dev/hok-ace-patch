package dev.halixm.hokacepatcher

/** Debug-only fixed fixture target exercising the production file adapter. */
class FixtureFileService : PrivilegedDeviceService() {
    override val dataPackage: String get() = FIXTURE
}
