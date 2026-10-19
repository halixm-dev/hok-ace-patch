package dev.halixm.hokacepatcher

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import java.io.File
import java.security.MessageDigest
import org.json.JSONObject
import org.xmlpull.v1.XmlPullParser

/** Full content identity, manifest and signer checks; an access APK can never become recovery material. */
data class ApkIdentity(
    val bytes: Long,
    val sha256: String,
    val packageName: String,
    val versionCode: Long,
    val versionName: String,
    val certificateSha256: String,
    val debuggable: Boolean,
) {
    fun json(): JSONObject = JSONObject().put("bytes", bytes).put("sha256", sha256)
        .put("package", packageName).put("version_code", versionCode).put("version_name", versionName)
        .put("certificate_sha256", certificateSha256).put("debuggable", debuggable)

    companion object {
        fun digest(file: File): String {
            val hash = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    hash.update(buffer, 0, count)
                }
            }
            return hash.digest().joinToString("") { "%02x".format(it) }
        }

        fun read(context: Context, file: File): ApkIdentity {
            require(file.isFile && file.length() in 1..(3L * 1024 * 1024 * 1024)) { "Invalid game APK file" }
            val beforeLength = file.length()
            val beforeTime = file.lastModified()
            val sha = digest(file)
            val info = context.packageManager.getPackageArchiveInfo(file.path,
                PackageManager.GET_SIGNING_CERTIFICATES) ?: error("Cannot read the game APK manifest")
            check(info.packageName == PrivilegedDeviceService.GAME) { "The APK does not belong to Honor of Kings: ACE" }
            val signers = checkNotNull(info.signingInfo) { "The APK has no signing identity" }.apkContentsSigners
            check(signers.size == 1) { "Multiple game APK signers are unsupported" }
            val certificate = MessageDigest.getInstance("SHA-256").digest(signers.single().toByteArray())
                .joinToString("") { "%02x".format(it) }
            val debuggable = declaresDebuggable(context, file, info)
            check(file.length() == beforeLength && file.lastModified() == beforeTime) { "The game APK changed while verifying" }
            return ApkIdentity(beforeLength, sha, info.packageName, info.longVersionCode,
                info.versionName ?: "", certificate, debuggable)
        }

        /**
         * android:debuggable as Android resolves it: by resource id, through the attribute walk the package
         * parser itself uses. Not ApplicationInfo.flags: Android 15's first release (android-15.0.0_r1, the
         * AP3A builds) never calls hideAsFinal() in getPackageArchiveInfo, so an APK file's flags are never
         * derived and FLAG_DEBUGGABLE reads false for every archive (Infinix X6851, moto g45, realme RMX3830).
         */
        private fun declaresDebuggable(context: Context, file: File, info: PackageInfo): Boolean {
            val application = checkNotNull(info.applicationInfo) { "The APK has no application manifest" }
            application.sourceDir = file.path
            application.publicSourceDir = file.path
            val resources = context.packageManager.getResourcesForApplication(application)
            resources.assets.openXmlResourceParser("AndroidManifest.xml").use { parser ->
                var type = parser.next()
                while (type != XmlPullParser.END_DOCUMENT) {
                    if (type == XmlPullParser.START_TAG && parser.depth == 1)
                        check(parser.getAttributeValue(null, "package") == info.packageName) {
                            "Cannot read the game APK manifest"
                        }
                    if (type == XmlPullParser.START_TAG && parser.depth == 2 && parser.name == "application") {
                        val values = resources.obtainAttributes(parser, intArrayOf(android.R.attr.debuggable))
                        try { return values.getBoolean(0, false) } finally { values.recycle() }
                    }
                    type = parser.next()
                }
            }
            error("The APK has no application manifest")
        }

        fun fromJson(value: JSONObject): ApkIdentity = ApkIdentity(value.getLong("bytes"),
            value.getString("sha256"), value.getString("package"), value.getLong("version_code"),
            value.getString("version_name"), value.getString("certificate_sha256"), value.getBoolean("debuggable"))
    }

    fun requireRecovery() {
        check(!debuggable && certificateSha256 == GameSigner.CERTIFICATE_SHA256 &&
            packageName == PrivilegedDeviceService.GAME) { "Recovery requires a verified normal game APK" }
    }
}
