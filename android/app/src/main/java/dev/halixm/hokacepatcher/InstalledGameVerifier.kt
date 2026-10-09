package dev.halixm.hokacepatcher

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.ParcelFileDescriptor
import java.security.MessageDigest
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Verify installed content through a bounded pipe, independently of installer acknowledgments. */
class InstalledGameVerifier(private val context: Context, private val device: IPrivilegedDeviceService) {
    companion object {
        /** Prefix of every mismatch; the UI matches on it. A mismatch is a different app, not a damaged one. */
        const val DIFFERENT_APP = "The installed game app is not the expected one"
    }

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
                    check(length <= expected.bytes) { "$DIFFERENT_APP: it is larger than the expected ${expected.bytes} bytes" }
                    hash.update(buffer, 0, count)
                }
            }
            // copyGameApk checks its own read, so a short stream here is a smaller installed file.
            check(length == expected.bytes) { "$DIFFERENT_APP: it is $length bytes, expected ${expected.bytes}" }
            hash.digest().joinToString("") { "%02x".format(it) }
        }
        try {
            pipe[1].use { device.copyGameApk(it) }
            val digest = try { transfer.get(240, TimeUnit.SECONDS) }
                catch (wrapped: ExecutionException) { throw wrapped.cause ?: wrapped }
            check(digest == expected.sha256) { "$DIFFERENT_APP: its contents differ" }
            val info = context.packageManager.getPackageInfo(PrivilegedDeviceService.GAME,
                PackageManager.GET_SIGNING_CERTIFICATES)
            val signers = checkNotNull(info.signingInfo).apkContentsSigners
            check(signers.size == 1)
            val certificate = MessageDigest.getInstance("SHA-256").digest(signers.single().toByteArray())
                .joinToString("") { "%02x".format(it) }
            val debug = checkNotNull(info.applicationInfo).flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
            check(info.longVersionCode == expected.versionCode && info.versionName == expected.versionName &&
                certificate == expected.certificateSha256 && debug == expected.debuggable) {
                "$DIFFERENT_APP: its version, signature or debug flag differs"
            }
        } finally {
            pipe.forEach { runCatching { it.close() } }
            reader.shutdownNow()
        }
    }
}
