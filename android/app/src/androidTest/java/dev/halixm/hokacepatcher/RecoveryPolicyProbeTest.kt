package dev.halixm.hokacepatcher

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Policy parser/transport controls only. No shell, APK, device binding or live game path. */
@RunWith(AndroidJUnit4::class)
class RecoveryPolicyProbeTest {
    private fun policy() = JSONObject().put("schema", 1).put("watchdog_absent", false).put("files",
        JSONObject().put("packages/1/1.db", JSONObject().put("absent", false).put("states", JSONArray().put(
            JSONObject().put("sha256", "a".repeat(64)).put("bytes", 10)))))
    private fun reject(action: () -> Unit) {
        try { action(); fail("Malformed recovery policy accepted") } catch (_: IllegalArgumentException) {
        } catch (_: IllegalStateException) { }
    }
    @Test fun strictTypesCountsPathsAndDuplicates() {
        val mutations: List<(JSONObject) -> Unit> = listOf(
            { it.put("schema", "1") }, { it.put("schema", 1.0) }, { it.put("watchdog_absent", "false") },
            { it.put("extra", true) }, { it.put("files", JSONObject()) },
            { it.getJSONObject("files").put("../outside", it.getJSONObject("files").get("packages/1/1.db")) },
            { it.getJSONObject("files").getJSONObject("packages/1/1.db").put("absent", 1) },
            { it.getJSONObject("files").getJSONObject("packages/1/1.db").getJSONArray("states").getJSONObject(0).put("bytes", 1.5) },
            { it.getJSONObject("files").getJSONObject("packages/1/1.db").getJSONArray("states").getJSONObject(0).put("bytes", "10") },
            { it.getJSONObject("files").getJSONObject("packages/1/1.db").getJSONArray("states").getJSONObject(0).put("sha256", "A".repeat(64)) })
        for (mutate in mutations) { val p = policy(); mutate(p); reject { RecoveryFilePolicy.parse(p) } }
        val duplicate = policy().toString().replace("\"schema\":1", "\"schema\":1,\"schema\":1")
        reject { RecoveryFilePolicy.parse(ArtifactReceipts.parse(duplicate.toByteArray())) }
    }
    @Test fun largeManifestUsesRowsOnStdinAndKeepsCommandArgumentSmall() {
        val value = policy(); val files = value.getJSONObject("files"); val item = files.get("packages/1/1.db")
        for (i in 2..8192) files.put("packages/$i/$i.db", item)
        val parsed = RecoveryFilePolicy.parse(ArtifactReceipts.parse(value.toString().toByteArray()))
        val command = RecoveryFilePolicy.script(parsed)
        assertTrue(command.length < 8192)
        assertTrue(RecoveryFilePolicy.rows(parsed, false).size > 128 * 1024)
        assertFalse(command.contains("packages/8192/8192.db"))
        val target = RecoveryFilePolicy.script(parsed, "packages/8192/8192.db")
        assertTrue(target.length < 4096); assertTrue(target.contains("packages/8192/8192.db"))
        files.put("packages/8193/8193.db", item)
        reject { RecoveryFilePolicy.parse(value) }
    }
}
