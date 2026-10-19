package dev.halixm.hokacepatcher

import android.content.Context
import android.util.AtomicFile
import java.io.File
import org.json.JSONObject

/** Retain independently verified normal APKs, separate from source/access APKs and build outputs. */
class RecoveryStore(private val context: Context) {
    private val root = File(context.filesDir, "recovery")

    fun normal(id: String): File {
        require(id.matches(Regex("[0-9a-f]{64}"))) { "Invalid recovery identity" }
        return File(root, "$id/normal.apk")
    }

    fun expected(id: String): ApkIdentity {
        val folder = normal(id).parentFile!!
        val expected = ApkIdentity.fromJson(JSONObject(String(
            DurableFiles.readCommitted(File(folder, "identity.json")), Charsets.UTF_8)))
        expected.requireRecovery()
        check(expected.sha256 == id) { "Recovery metadata identity differs" }
        return expected
    }

    fun verify(id: String): ApkIdentity {
        val expected = expected(id)
        val actual = ApkIdentity.read(context, normal(id))
        actual.requireRecovery()
        check(actual == expected) { "Recovery APK changed; do not install it" }
        return actual
    }

    fun adopt(candidate: File): ApkIdentity {
        val identity = ApkIdentity.read(context, candidate)
        identity.requireRecovery()
        val target = normal(identity.sha256)
        DurableFiles.createDirectories(target.parentFile!!)
        if (!target.exists()) {
            val temp = File(target.parentFile, "normal.apk.partial")
            candidate.inputStream().use { input ->
                temp.outputStream().use { output -> input.copyTo(output, 1024 * 1024); output.fd.sync() }
            }
            check(ApkIdentity.read(context, temp) == identity) { "Recovery copy differs" }
            check(temp.renameTo(target)) { "Cannot retain recovery APK" }
            DurableFiles.syncDirectory(target.parentFile!!)
        } else {
            check(ApkIdentity.read(context, target) == identity) { "Existing recovery APK differs" }
        }
        check(target.setReadOnly()) { "Cannot protect recovery APK" }
        val metadata = AtomicFile(File(target.parentFile, "identity.json"))
        val stream = metadata.startWrite()
        try {
            stream.write(identity.json().toString().toByteArray(Charsets.UTF_8))
            stream.fd.sync()
            metadata.finishWrite(stream)
            DurableFiles.syncDirectory(target.parentFile!!)
        } catch (error: Throwable) {
            metadata.failWrite(stream)
            throw error
        }
        verify(identity.sha256)
        return identity
    }
}
