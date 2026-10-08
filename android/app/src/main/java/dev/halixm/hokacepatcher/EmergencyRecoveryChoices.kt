package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File
import java.nio.file.Files

/** A damaged transaction record must not hide retained APKs from explicit emergency selection. */
class EmergencyRecoveryChoices(private val context: Context) {
    data class Choices(val ids: List<String>, val needsSelection: Boolean)

    fun resolve(preferred: () -> String): Choices {
        // A pending emergency request remains authoritative; never replace damaged emergency intent.
        EmergencyRestoreStore(context).snapshot()?.takeIf {
            it.getString("status") == "verification_pending"
        }?.let { return Choices(listOf(it.getString("normal")), false) }
        return try { Choices(listOf(preferred()), false) } catch (error: Exception) {
            val root = File(context.filesDir, "recovery")
            check(!Files.isSymbolicLink(root.toPath())) { "Recovery folder is a link" }
            val ids = root.listFiles().orEmpty().filter {
                it.isDirectory && !Files.isSymbolicLink(it.toPath()) &&
                    it.name.matches(Regex("[0-9a-f]{64}"))
            }.mapNotNull { folder ->
                runCatching {
                    val store = RecoveryStore(context)
                    val apk = store.normal(folder.name)
                    check(apk.isFile && !Files.isSymbolicLink(apk.toPath()))
                    store.expected(folder.name)
                    folder.name
                }.getOrNull()
            }.sorted()
            check(ids.isNotEmpty()) { "Recovery records cannot be read and no retained normal APK is available" }
            Choices(ids, true)
        }
    }
}
