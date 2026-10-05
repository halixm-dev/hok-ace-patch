package dev.halixm.hokacepatcher

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.ParcelFileDescriptor
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Verify installed content through a bounded pipe, independently of installer acknowledgments. */
class InstalledGameVerifier(private val context: Context, private val device: IPrivilegedDeviceService) {
    fun verify(expected: ApkIdentity) {
        check(expected.packageName == PrivilegedDeviceService.GAME)
        check(expected.bytes in 1..(3L * 1024 * 1024 * 1024))
        check(expected.sha256.matches(Regex("[0-9a-f]{64}")))
        val pipe = ParcelFileDescriptor.createPipe()
        val reader = Executors.newSingleThreadExecutor()
        val transfer = reader.submit<String> {
            val hash = MessageDigest.getInstance("SHA-256")
            var length = 0L
            ParcelFileDescriptor.AutoCloseInputStream(pipe[0]).use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    length += count
                    check(length <= expected.bytes) { "Installed APK length differs" }
                    hash.update(buffer, 0, count)
                }
            }
            check(length == expected.bytes) { "Installed APK stream is incomplete" }
            hash.digest().joinToString("") { "%02x".format(it) }
        }
        try {
            pipe[1].use { device.copyGameApk(it) }
            check(transfer.get(240, TimeUnit.SECONDS) == expected.sha256) { "Installed APK hash differs" }
            val info = context.packageManager.getPackageInfo(PrivilegedDeviceService.GAME,
                PackageManager.GET_SIGNING_CERTIFICATES)
            val signers = checkNotNull(info.signingInfo).apkContentsSigners
            check(signers.size == 1)
            val certificate = MessageDigest.getInstance("SHA-256").digest(signers.single().toByteArray())
                .joinToString("") { "%02x".format(it) }
            val debug = checkNotNull(info.applicationInfo).flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
            check(info.longVersionCode == expected.versionCode && info.versionName == expected.versionName &&
                certificate == expected.certificateSha256 && debug == expected.debuggable) {
                "Installed manifest/signature identity differs"
            }
        } finally {
            pipe.forEach { runCatching { it.close() } }
            reader.shutdownNow()
        }
    }
}
