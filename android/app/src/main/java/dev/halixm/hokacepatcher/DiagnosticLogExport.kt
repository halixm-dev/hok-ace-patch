package dev.halixm.hokacepatcher

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.io.Writer
import java.nio.file.Files
import java.security.MessageDigest
import java.util.UUID

/** Read-only, bounded raw diagnostics remain exportable when recovery records cannot be loaded. */
class DiagnosticLogExport(private val context: Context) {
    fun write(output: Writer) {
        val root = context.filesDir
        output.write("HOK ACE diagnostics. Raw records below are UNVALIDATED evidence, not recovery authorization.\n")
        var remaining = TOTAL_BYTES
        fun record(relative: String, tail: Boolean = false) {
            val file = File(root, relative)
            var cursor: File? = file
            while (cursor != null && cursor != root) {
                if (Files.isSymbolicLink(cursor.toPath())) {
                    output.write("Skipped linked path: $relative\n"); return
                }
                cursor = cursor.parentFile
            }
            if (!file.exists()) return
            if (!file.isFile) { output.write("Skipped non-file: $relative\n"); return }
            val length = file.length()
            val limit = if (tail) LOG_BYTES else RECORD_BYTES
            if (!tail && length > limit) {
                output.write("Skipped oversized record: $relative ($length bytes)\n"); return
            }
            val count = minOf(length, limit.toLong()).toInt()
            if (count > remaining) { output.write("Export byte limit reached: $relative\n"); return }
            val offset = length - count
            val bytes = try {
                RandomAccessFile(file, "r").use { input ->
                    check(input.length() == length) { "Record changed before reading" }
                    input.seek(offset)
                    ByteArray(count).also { input.readFully(it) }
                }
            } catch (error: Exception) {
                output.write("Cannot read $relative: ${error.javaClass.simpleName}\n"); return
            }
            remaining -= count
            val sha = MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it) }
            val value = JSONObject().put("path", relative).put("unvalidated", true)
                .put("file_bytes", length).put("offset", offset).put("exported_bytes", count)
                .put("exported_sha256", sha).put("raw_base64", Base64.encodeToString(bytes, Base64.NO_WRAP))
            output.write(value.toString() + "\n")
            if (tail) output.write(String(bytes, Charsets.UTF_8) + "\n")
        }
        record("feasibility.log", true)
        record("worker-state.json")
        record("worker-state.json.bak")
        for (folder in listOf("sessions", "first-setups")) {
            val directory = File(root, folder)
            if (Files.isSymbolicLink(directory.toPath())) {
                output.write("Skipped linked folder: $folder\n"); continue
            }
            // Stream the enumeration so a damaged directory cannot create an unbounded array.
            if (!directory.isDirectory) continue
            val paths = try {
                Files.newDirectoryStream(directory.toPath()).use { entries ->
                    entries.asSequence().take(ENTRY_LIMIT + 1).toList()
                }
            } catch (error: Exception) {
                output.write("Cannot enumerate $folder: ${error.javaClass.simpleName}\n"); continue
            }
            if (paths.size > ENTRY_LIMIT) output.write("Entry limit reached: $folder\n")
            for (path in paths.take(ENTRY_LIMIT)) {
                val name = path.fileName.toString()
                if (name == "coordinator.lock") continue
                if (name.startsWith(".creating-") && runCatching {
                    UUID.fromString(name.removePrefix(".creating-")).toString() == name.removePrefix(".creating-")
                }.getOrDefault(false)) continue
                if (!runCatching { UUID.fromString(name).toString() == name }.getOrDefault(false)) {
                    output.write("Unrecognized entry in $folder\n"); continue
                }
                if (Files.isSymbolicLink(path)) { output.write("Skipped linked session: $folder/$name\n"); continue }
                output.write("Unvalidated $folder/$name\n")
                record("$folder/$name/journal.json")
                record("$folder/$name/journal.json.bak")
                if (!File(path.toFile(), "journal.json").isFile &&
                    !File(path.toFile(), "journal.json.bak").isFile)
                    output.write("Published journal missing: $folder/$name\n")
            }
        }
        record("emergency-restore.json")
        record("emergency-restore.json.bak")
        output.flush()
    }

    companion object {
        private const val RECORD_BYTES = 1024 * 1024
        private const val LOG_BYTES = 256 * 1024
        private const val TOTAL_BYTES = 8 * 1024 * 1024
        private const val ENTRY_LIMIT = 256
    }
}
