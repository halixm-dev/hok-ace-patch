package dev.halixm.hokacepatcher

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.io.RandomAccessFile
import java.util.UUID
import org.json.JSONObject

/** One-use consent binds irreversible data loss and Scan-to-login to the verified preparation. */
class FirstSetupRequestStore(private val context: Context) {
    private val root = File(context.filesDir, "setup-requests")
    private fun file(id: String): File { GameFilePolicy.session(id); return File(root, "$id.json") }
    private fun receipt(id: String) = File(context.filesDir, "preparations/$id/receipt.json")
    private fun ready() {
        check(FirstSetupJournal.pending(context).isEmpty()) { "Recover or finish the pending game setup first" }
        check(SessionJournal.pending(File(context.filesDir, "sessions")).isEmpty()) {
            "Recover the interrupted translation first"
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

    fun confirm(prepared: ApkPreparation.Prepared, dataLossConfirmed: Boolean, scanLoginConfirmed: Boolean): String {
        check(dataLossConfirmed && scanLoginConfirmed) { "Confirm local data loss and Scan-to-login first" }
        ready()
        check(prepared.requiresSignatureConversion) { "This game is already converted; use the update checkpoint" }
        val preparation = prepared.directory.name; GameFilePolicy.session(preparation)
        check(prepared.directory.canonicalFile == File(context.filesDir, "preparations/$preparation").canonicalFile)
        val metadata = JSONObject(String(AtomicFile(receipt(preparation)).readFully(), Charsets.UTF_8))
        check(ApkIdentity.fromJson(metadata.getJSONObject("source")) == prepared.source &&
            ApkIdentity.fromJson(metadata.getJSONObject("normal")) == prepared.normal &&
            ApkIdentity.fromJson(metadata.getJSONObject("access")) == prepared.access) { "Prepared files changed before consent" }
        val id = UUID.randomUUID().toString()
        write(id, JSONObject().put("schema", 1).put("id", id).put("preparation", preparation)
            .put("receipt_sha256", ApkIdentity.digest(receipt(preparation))).put("source", prepared.source.sha256)
            .put("normal", prepared.normal.sha256).put("access", prepared.access.sha256)
            .put("data_loss_confirmed", true).put("scan_login_confirmed", true)
            .put("confirmed_ms", System.currentTimeMillis()).put("consumed", false))
        return id
    }

    fun claim(id: String): ApkPreparation.Prepared {
        DurableFiles.createDirectories(root)
        RandomAccessFile(File(root, "claim.lock"), "rw").use { handle -> handle.channel.use { channel ->
            checkNotNull(channel.tryLock()) { "Another setup confirmation is being checked" }.use {
                val bytes = AtomicFile(file(id)).readFully()
                check(bytes.size <= 8192)
                val saved = JSONObject(String(bytes, Charsets.UTF_8))
                check(saved.getInt("schema") == 1 && saved.getString("id") == id &&
                    saved.getBoolean("data_loss_confirmed") && saved.getBoolean("scan_login_confirmed"))
                check(!saved.getBoolean("consumed")) { "Setup consent was already used; confirm again" }
                val elapsed = System.currentTimeMillis() - saved.getLong("confirmed_ms")
                check(elapsed in 0..(15 * 60 * 1000L)) { "Setup consent expired; confirm again" }
                ready()
                val preparation = saved.getString("preparation"); GameFilePolicy.session(preparation)
                check(ApkIdentity.digest(receipt(preparation)) == saved.getString("receipt_sha256")) { "Prepared files changed; prepare and confirm again" }
                val prepared = ApkPreparation(context).load(preparation)
                check(prepared.requiresSignatureConversion && prepared.source.sha256 == saved.getString("source") &&
                    prepared.normal.sha256 == saved.getString("normal") && prepared.access.sha256 == saved.getString("access"))
                write(id, saved.put("consumed", true).put("claimed_ms", System.currentTimeMillis()))
                return prepared
            }
        } }
    }

    /** Bind the journal's mutation attempt to the consumed consent; a second attempt needs new consent. */
    fun begin(id: String, prepared: ApkPreparation.Prepared) {
        RandomAccessFile(File(root, "claim.lock"), "rw").use { handle -> handle.channel.use { channel ->
            checkNotNull(channel.tryLock()) { "Another setup confirmation is being checked" }.use {
                val bytes = AtomicFile(file(id)).readFully(); check(bytes.size <= 8192)
                val saved = JSONObject(String(bytes, Charsets.UTF_8))
                check(saved.getInt("schema") == 1 && saved.getString("id") == id && saved.getBoolean("consumed") &&
                    saved.getBoolean("data_loss_confirmed") && saved.getBoolean("scan_login_confirmed"))
                check(!saved.optBoolean("started", false)) { "Setup consent already started a mutation attempt" }
                check(System.currentTimeMillis() - saved.getLong("confirmed_ms") in 0..(15 * 60 * 1000L)) { "Setup consent expired; confirm again" }
                check(saved.getString("preparation") == prepared.directory.name &&
                    saved.getString("source") == prepared.source.sha256 && saved.getString("normal") == prepared.normal.sha256 &&
                    saved.getString("access") == prepared.access.sha256 &&
                    saved.getString("receipt_sha256") == ApkIdentity.digest(receipt(prepared.directory.name))) {
                    "Prepared files changed before setup"
                }
                write(id, saved.put("started", true).put("started_ms", System.currentTimeMillis()))
            }
        } }
    }
}
