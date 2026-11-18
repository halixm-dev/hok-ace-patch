package dev.halixm.hokacepatcher

import java.io.File
import java.nio.file.Files
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

/** Shared bytes and hashes test compatibility; these are not transformation tests. */
class ArtifactReceiptsTest {
    private fun vectors(): JSONObject = javaClass.getResourceAsStream("/vectors.json")!!.use {
        JSONObject(String(it.readBytes(), Charsets.UTF_8))
    }

    private fun refused(call: () -> Unit) {
        try { call() } catch (_: Exception) { return }
        fail("Incomplete or changed content was accepted")
    }

    @Test fun canonicalVectorsMatchPython() {
        val values = vectors().getJSONArray("canonical")
        for (index in 0 until values.length()) {
            val vector = values.getJSONObject(index)
            assertEquals(vector.getString("canonical"), ArtifactReceipts.canonical(vector.get("value")))
            assertEquals(vector.getString("key"), ArtifactReceipts.identityKey(vector.get("value")))
        }
    }

    @Test fun strictJsonAndPathVectorsRefuse() {
        val vectors = vectors()
        val paths = vectors.getJSONArray("invalid_paths")
        for (index in 0 until paths.length()) refused { ArtifactReceipts.relativePath(paths.getString(index)) }
        val json = vectors.getJSONArray("invalid_json")
        for (index in 0 until json.length()) refused { ArtifactReceipts.parse(json.getString(index).toByteArray(Charsets.UTF_8)) }
        refused { ArtifactReceipts.parse(ByteArray(ArtifactReceipts.MAX_JSON + 1)) }
        val collision = JSONObject().put("A", JSONObject().put("size", 1).put("sha256", "0".repeat(64)))
            .put("a", JSONObject().put("size", 1).put("sha256", "0".repeat(64)))
        refused { ArtifactReceipts.validateManifest(collision) }
    }

    /** The production link-count reader where the host has the unix view; else this test's explicit opt-in that its fresh files have one link. */
    private fun hostLinkCount(): (java.nio.file.Path) -> Long {
        val production = ArtifactReceipts.linkCount
        return if ("unix" in java.nio.file.FileSystems.getDefault().supportedFileAttributeViews()) production else { _ -> 1L }
    }

    /** Writes the shared payloads and the committed receipt under a fresh canonical root. */
    private fun staged(root: File): JSONObject {
        val vectors = vectors()
        val payloads = vectors.getJSONObject("payloads")
        payloads.keys().forEach { name ->
            val file = File(root, name); file.parentFile!!.mkdirs()
            file.writeText(payloads.getString(name), Charsets.UTF_8)
        }
        val receipt = vectors.getJSONObject("receipt")
        File(root, ArtifactReceipts.NAME).writeText(ArtifactReceipts.canonical(receipt), Charsets.UTF_8)
        return receipt
    }

    private fun withLinkCount(reader: (java.nio.file.Path) -> Long, call: () -> Unit) {
        val production = ArtifactReceipts.linkCount
        ArtifactReceipts.linkCount = reader
        try { call() } finally { ArtifactReceipts.linkCount = production }
    }

    /** An unreadable or aliased link count refuses verification; unknown is never taken as one link. */
    @Test fun unreadableOrSharedLinkCountRefuses() {
        val root = Files.createTempDirectory("artifact-receipt-").toFile().canonicalFile
        try {
            val receipt = staged(root)
            val identity = receipt.getJSONObject("identity")
            withLinkCount(hostLinkCount()) { ArtifactReceipts.verify(root, identity, stage = "staged") }
            withLinkCount({ throw UnsupportedOperationException("View 'unix' not available") }) { refused { ArtifactReceipts.verify(root, identity) } }
            withLinkCount({ 2L }) { refused { ArtifactReceipts.verify(root, identity) } }
            val marker = File(root, ArtifactReceipts.NAME).toPath()
            withLinkCount({ if (it == marker) 1L else 2L }) { refused { ArtifactReceipts.verify(root, identity) } }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test fun receiptReadsSharedBytesAndRejectsMutations() = withLinkCount(hostLinkCount()) {
        // Canonicalize the trusted test directory boundary just as Android filesDir is.
        val root = Files.createTempDirectory("artifact-receipt-").toFile().canonicalFile
        try {
            val vectors = vectors()
            val payloads = vectors.getJSONObject("payloads")
            payloads.keys().forEach { name ->
                val file = File(root, name); file.parentFile!!.mkdirs()
                file.writeText(payloads.getString(name), Charsets.UTF_8)
            }
            val receipt = vectors.getJSONObject("receipt")
            val marker = File(root, ArtifactReceipts.NAME)
            marker.writeText(ArtifactReceipts.canonical(receipt), Charsets.UTF_8)
            val identity = receipt.getJSONObject("identity")
            assertEquals(receipt.getString("input_key"), ArtifactReceipts.verify(root, identity, stage = "staged").getString("input_key"))
            val payload = File(root, "1/1_0.db")
            val original = payload.readBytes()
            payload.writeBytes(ByteArray(original.size) { 'X'.code.toByte() })
            refused { ArtifactReceipts.verify(root) }
            payload.writeBytes(original)
            val extra = File(root, "unexpected"); extra.writeText("extra")
            refused { ArtifactReceipts.verify(root) }; check(extra.delete())
            check(payload.delete()); refused { ArtifactReceipts.verify(root) }; payload.writeBytes(original)
            marker.writeText(ArtifactReceipts.canonical(JSONObject(receipt.toString()).put("schema", 999)))
            refused { ArtifactReceipts.verify(root) }
            marker.writeText(ArtifactReceipts.canonical(JSONObject(receipt.toString()).put("committed", false)))
            refused { ArtifactReceipts.verify(root) }
            marker.writeText(ArtifactReceipts.canonical(receipt))
            val changed = JSONObject(identity.toString())
            changed.getJSONObject("request").put("language", "id")
            refused { ArtifactReceipts.verify(root, changed) }
            check(marker.delete()); refused { ArtifactReceipts.verify(root) }
        } finally {
            // Only the freshly created private test root is removed.
            root.deleteRecursively()
        }
    }
}
