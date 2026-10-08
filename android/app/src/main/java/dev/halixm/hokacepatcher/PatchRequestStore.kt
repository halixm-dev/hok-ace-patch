package dev.halixm.hokacepatcher

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.io.RandomAccessFile
import java.util.UUID
import org.json.JSONObject

/** One-use update confirmation bound to a verified preparation, never caller-supplied APK paths. */
class PatchRequestStore(private val context: Context) {
    private val root = File(context.filesDir, "patch-requests")
    private fun file(id: String): File { GameFilePolicy.session(id); return File(root, "$id.json") }
    private fun receipt(id: String) = File(context.filesDir, "preparations/$id/receipt.json")
    private fun noPendingRecovery() {
        check(FirstSetupJournal.pending(context).isEmpty()) { "Finish or recover first-time setup before starting a patch" }
        check(SessionJournal.pending(File(context.filesDir, "sessions")).isEmpty()) {
            "Recover the interrupted patch before starting another patch"
        }
    }
    private fun write(id: String, value: JSONObject) {
        DurableFiles.createDirectories(root)
        val storage = AtomicFile(file(id)); val stream = storage.startWrite()
        try {
            stream.write(value.toString().toByteArray(Charsets.UTF_8)); stream.fd.sync(); storage.finishWrite(stream)
            DurableFiles.syncDirectory(root)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
    }

    fun confirm(prepared: ApkPreparation.Prepared, updateFinishedAndGameClosed: Boolean): String {
        check(updateFinishedAndGameClosed) { "Wait for the complete game update and close the game first" }
        noPendingRecovery()
        check(!prepared.requiresSignatureConversion) { "Initial game setup needs separate data-loss consent" }
        val preparation = prepared.directory.name; GameFilePolicy.session(preparation)
        check(prepared.directory.canonicalFile == File(context.filesDir, "preparations/$preparation").canonicalFile)
        val metadata = JSONObject(String(AtomicFile(receipt(preparation)).readFully(), Charsets.UTF_8))
        check(ApkIdentity.fromJson(metadata.getJSONObject("normal")) == prepared.normal &&
            ApkIdentity.fromJson(metadata.getJSONObject("access")) == prepared.access &&
            ApkIdentity.fromJson(metadata.optJSONObject("installed_source") ?: metadata.getJSONObject("source")) == prepared.source) { "Prepared files changed before confirmation" }
        val id = UUID.randomUUID().toString()
        write(id, JSONObject().put("schema", 1).put("id", id).put("preparation", preparation)
            .put("normal", prepared.normal.sha256).put("access", prepared.access.sha256)
            .put("receipt_sha256", ApkIdentity.digest(receipt(preparation)))
            .put("confirmed_ms", System.currentTimeMillis()).put("update_finished_and_game_closed", true)
            .put("consumed", false))
        return id
    }

    fun claim(id: String): ApkPreparation.Prepared {
        DurableFiles.createDirectories(root)
        RandomAccessFile(File(root, "claim.lock"), "rw").use { handle -> handle.channel.use { channel ->
            checkNotNull(channel.tryLock()) { "Another patch request is being checked" }.use {
                val storage = AtomicFile(file(id)); val bytes = storage.readFully()
                check(bytes.size <= 8192) { "Patch request is oversized" }
                val saved = JSONObject(String(bytes, Charsets.UTF_8))
                check(saved.getInt("schema") == 1 && saved.getString("id") == id &&
                    saved.getBoolean("update_finished_and_game_closed")) { "Confirm the completed game update first" }
                check(!saved.getBoolean("consumed")) { "This confirmation was already used; confirm again" }
                val elapsed = System.currentTimeMillis() - saved.getLong("confirmed_ms")
                check(elapsed in 0..(15 * 60 * 1000L)) { "Update confirmation expired; confirm again" }
                noPendingRecovery()
                val preparation = saved.getString("preparation"); GameFilePolicy.session(preparation)
                check(ApkIdentity.digest(receipt(preparation)) == saved.getString("receipt_sha256")) {
                    "Prepared files changed; prepare and confirm again"
                }
                val prepared = ApkPreparation(context).load(preparation)
                check(!prepared.requiresSignatureConversion && prepared.normal.sha256 == saved.getString("normal") &&
                    prepared.access.sha256 == saved.getString("access")) { "Prepared identities changed" }
                write(id, saved.put("consumed", true).put("claimed_ms", System.currentTimeMillis()))
                return prepared
            }
        } }
    }
}
