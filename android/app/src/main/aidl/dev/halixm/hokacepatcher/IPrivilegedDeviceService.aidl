package dev.halixm.hokacepatcher;

import android.os.ParcelFileDescriptor;

// Fixed targets only. Large files travel through descriptors, never Binder byte arrays.
interface IPrivilegedDeviceService {
    String diagnostics() = 0;
    String gameApkInfo() = 1;
    String copyGameApk(in ParcelFileDescriptor destination) = 2;
    byte[] probeFixture(in byte[] payload) = 3;
    void forceStopGame() = 4;
    String reinstallFixture(boolean abandonAfterWrite) = 5;
    String replaceGameApk(in ParcelFileDescriptor source, long length) = 6;
    String probeGame(in byte[] payload) = 7;
    String snapshotGame(in ParcelFileDescriptor destination, long maximumBytes) = 8;
    String validateGameSnapshot(in ParcelFileDescriptor manifest) = 9;
    String writeGameFile(String session, String relative, in ParcelFileDescriptor source, long length, String sha256) = 10;
    void clearGameWatchdog() = 11;
    void clearSessionTemp(String session, String relative) = 12;
    void restoreWatchdogDirectory(String relative) = 13;
    boolean firstSetupGameAbsent() = 14;
    void removeGameForFirstSetup(String expectedSourceSha256) = 15;
    String installFirstSetupGame(in ParcelFileDescriptor source, long length) = 16;
    void validateFirstSetupSource(String expectedSourceSha256) = 17;
    String estimateGameSnapshot() = 18;
    void destroy() = 16777114;
}
