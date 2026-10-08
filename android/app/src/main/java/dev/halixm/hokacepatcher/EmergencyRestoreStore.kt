package dev.halixm.hokacepatcher

import android.content.Context
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.nio.channels.OverlappingFileLockException
import java.util.UUID

/** Opening an installer records intent; only an independent installed-APK check resolves it. */
class EmergencyRestoreStore(context: Context) {
    private val directory = context.filesDir
    private val storage = AtomicFile(File(directory, "emergency-restore.json"))

    fun snapshot(): JSONObject? = synchronized(lock) {
        if (!storage.baseFile.exists() && !File(storage.baseFile.path + ".bak").exists()) null
        else JSONObject(String(storage.readFully(), Charsets.UTF_8)).also { value ->
            check(value.getInt("schema") == 1)
            UUID.fromString(value.getString("id"))
            check(value.getString("normal").matches(Regex("[0-9a-f]{64}")))
            check(value.getString("status") in setOf("verification_pending", "apk_verified"))
            check(value.getLong("created_ms") > 0)
            if (value.getString("status") == "apk_verified")
                check(value.getLong("verified_ms") >= value.getLong("created_ms"))
            else check(!value.has("verified_ms"))
        }
    }

    /** Called after cache verification and before launching the external installer. */
    fun begin(normal: String): JSONObject {
        val sessions = File(directory, "sessions")
        DurableFiles.createDirectories(sessions)
        RandomAccessFile(File(sessions, "coordinator.lock"), "rw").use { file ->
            file.channel.use { channel ->
                val guard = try { channel.tryLock() } catch (_: OverlappingFileLockException) { null }
                checkNotNull(guard) { "Wait for the active patch or recovery to stop before opening the emergency installer" }
                guard.use { return beginIdle(normal) }
            }
        }
    }

    private fun beginIdle(normal: String): JSONObject = synchronized(lock) {
        check(normal.matches(Regex("[0-9a-f]{64}")))
        snapshot()?.takeIf { it.getString("status") == "verification_pending" }?.let {
            check(it.getString("normal") == normal) { "Verify the previous emergency restore before choosing another APK" }
            return@synchronized it
        }
        val value = JSONObject().put("schema", 1).put("id", UUID.randomUUID().toString())
            .put("normal", normal).put("status", "verification_pending")
            .put("created_ms", System.currentTimeMillis())
        persist(value)
        JSONObject(value.toString())
    }

    fun verify(id: String, normal: String, installedVerifier: (String) -> Unit) {
        fun expected(): JSONObject = checkNotNull(snapshot()).also {
            check(it.getString("id") == id && it.getString("normal") == normal &&
                it.getString("status") == "verification_pending") { "Emergency restore request changed" }
        }
        synchronized(lock) { expected() }
        installedVerifier(normal)
        synchronized(lock) {
            val value = expected()
            value.put("status", "apk_verified").put("verified_ms", System.currentTimeMillis())
            persist(value)
        }
    }

    fun describe(): String = snapshot()?.let {
        if (it.getString("status") == "verification_pending")
            "Emergency restore is unverified. Finish or cancel the installer, then press Verify installed normal APK. Keep the game closed until unfinished game-data changes are recovered."
        else "Emergency APK restore verified. Unfinished game-data changes still require recovery."
    } ?: ""

    fun requireResolved() {
        check(snapshot()?.getString("status") != "verification_pending") {
            "Verify the pending emergency APK restore before starting another patch or first setup"
        }
    }

    private fun persist(value: JSONObject) {
        val stream = storage.startWrite()
        try {
            stream.write(value.toString().toByteArray(Charsets.UTF_8))
            stream.fd.sync()
            storage.finishWrite(stream)
            DurableFiles.syncDirectory(directory)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
    }

    companion object { private val lock = Any() }
}
