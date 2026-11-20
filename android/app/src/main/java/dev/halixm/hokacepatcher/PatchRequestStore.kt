package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File
import org.json.JSONObject

/** Start-bound prepared input. No checkbox/status/receipt alone grants dispatch permission. */
class PatchRequestStore(private val context: Context) {
    private val runs = RunStore(context)
    private val base = context.filesDir.canonicalFile

    private fun receipt(id: String): File {
        GameFilePolicy.session(id)
        val folder = File(base, "preparations/$id")
        RunStore.safe(base, folder, true)
        return File(folder, "receipt.json").also {
            listOf(it, File(it.path + ".bak")).filter { candidate -> candidate.exists() || java.nio.file.Files.isSymbolicLink(candidate.toPath()) }.forEach { candidate ->
                RunStore.safe(base, candidate); check(candidate.length() in 1..65536) { "Preparation receipt oversized" }
            }
        }
    }
    private fun binding(directory: File, source: ApkIdentity, normal: ApkIdentity?, access: ApkIdentity?): JSONObject {
        val id = directory.name; GameFilePolicy.session(id)
        check(directory.canonicalFile == File(base, "preparations/$id")) { "Wrong preparation root" }
        val path = receipt(id); val bytes = DurableFiles.readCommitted(path); check(bytes.size in 1..65536)
        val metadata = ArtifactReceipts.parse(bytes)
        check(metadata.get("schema") is Int || metadata.get("schema") is Long)
        check(metadata.getInt("schema") == 1)
        val root = normal == null
        check(metadata.keys().asSequence().toSet().let { keys ->
            if (root) keys == setOf("schema", "root", "source") else
                keys.containsAll(setOf("schema", "source", "normal", "access", "engine_id")) &&
                    keys.all { it in setOf("schema", "source", "normal", "access", "engine_id", "label_warning", "installed_source") }
        }) { "Unknown preparation fields" }
        if (metadata.has("root")) check(metadata.get("root") is Boolean)
        for (key in listOf("source", "installed_source", "normal", "access")) if (metadata.has(key)) {
            val identity = metadata.getJSONObject(key)
            check(ArtifactReceipts.canonical(ApkIdentity.fromJson(identity).json()) == ArtifactReceipts.canonical(identity)) { "Malformed APK identity" }
        }
        check(metadata.optBoolean("root", false) == root) { "Wrong preparation kind" }
        val selected = if (root) metadata.getJSONObject("source") else
            metadata.optJSONObject("installed_source") ?: metadata.getJSONObject("source")
        check(ApkIdentity.fromJson(selected) == source) { "Prepared source identity changed" }
        if (!root) check(ApkIdentity.fromJson(metadata.getJSONObject("normal")) == normal &&
            ApkIdentity.fromJson(metadata.getJSONObject("access")) == access) { "Prepared APK identities changed" }
        return JSONObject().put("id", id).put("receipt_sha256", ArtifactReceipts.digest(bytes)).put("root", root)
            .put("source", source.json()).also {
                normal?.let { identity -> it.put("normal", identity.json()) }
                access?.let { identity -> it.put("access", identity.json()) }
            }
    }
    fun authorize(runId: String, prepared: ApkPreparation.Prepared): String = RunStore.coordinator(context) {
        val run = runs.load(runId); check(run.provider != ShellProvider.ROOT)
        check(!prepared.requiresSignatureConversion) { "Initial game setup needs separate data-loss consent" }
        val saved = binding(prepared.directory, prepared.source, prepared.normal, prepared.access)
        // Independent loader rehashes exact APK bytes and validates installed/prepared semantic identities.
        check(ApkPreparation(context).load(prepared.directory.name) == prepared) { "Prepared files changed" }
        runs.bind(runId, saved); runId
    }
    fun authorizeRoot(runId: String, prepared: ApkPreparation.RootPrepared): String = RunStore.coordinator(context) {
        check(runs.load(runId).provider == ShellProvider.ROOT)
        val saved = binding(prepared.directory, prepared.installed, null, null)
        check(ApkPreparation(context).loadRoot(prepared.directory.name) == prepared) { "Prepared files changed" }
        runs.bind(runId, saved); runId
    }
    fun isRoot(id: String): Boolean = runs.load(id).provider == ShellProvider.ROOT

    /** Must be called within coordinator ownership, then journal publication uses run.sessionId. */
    fun claimRun(id: String, action: String, provider: ShellProvider): RunStore.Run {
        RunStore.requireCoordinator(context)
        val run = runs.load(id); val saved = checkNotNull(run.preparation)
        val path = receipt(saved.getString("id"))
        check(ApkIdentity.digest(path) == saved.getString("receipt_sha256")) { "Prepared receipt changed" }
        if (provider == ShellProvider.ROOT) loadRoot(run) else load(run)
        return runs.claim(id, action, provider)
    }
    fun load(run: RunStore.Run): ApkPreparation.Prepared {
        check(run.provider != ShellProvider.ROOT)
        val saved = checkNotNull(run.preparation)
        check(ApkIdentity.digest(receipt(saved.getString("id"))) == saved.getString("receipt_sha256")) { "Prepared receipt changed" }
        RunStore.safeShared(base, File(base, "preparations/${saved.getString("id")}/apks/access.apk"))
        val normal = ApkIdentity.fromJson(saved.getJSONObject("normal"))
        RunStore.safe(base, RecoveryStore(context).normal(normal.sha256))
        RunStore.safe(base, File(RecoveryStore(context).normal(normal.sha256).parentFile, "identity.json"))
        val prepared = ApkPreparation(context).load(saved.getString("id"))
        check(!prepared.requiresSignatureConversion && ArtifactReceipts.canonical(binding(prepared.directory, prepared.source, prepared.normal, prepared.access)) == ArtifactReceipts.canonical(saved)) {
            "Prepared identities changed"
        }
        return prepared
    }
    fun loadRoot(run: RunStore.Run): ApkPreparation.RootPrepared {
        check(run.provider == ShellProvider.ROOT)
        val saved = checkNotNull(run.preparation)
        check(ApkIdentity.digest(receipt(saved.getString("id"))) == saved.getString("receipt_sha256")) { "Prepared receipt changed" }
        RunStore.safeShared(base, File(base, "preparations/${saved.getString("id")}/original.apk"))
        val prepared = ApkPreparation(context).loadRoot(saved.getString("id"))
        check(ArtifactReceipts.canonical(binding(prepared.directory, prepared.installed, null, null)) == ArtifactReceipts.canonical(saved)) {
            "Prepared identities changed"
        }
        return prepared
    }

    /** Schema-1 requests have no durable target/action. They cannot authorize a fresh mutation. */
    @Deprecated("Use RunStore.start then authorize")
    fun confirm(prepared: ApkPreparation.Prepared, updateFinishedAndGameClosed: Boolean): String =
        error("Explicit durable Start authorization required")
    @Deprecated("Use RunStore.start then authorizeRoot")
    fun confirmRoot(prepared: ApkPreparation.RootPrepared, updateFinishedAndGameClosed: Boolean): String =
        error("Explicit durable Start authorization required")
    @Deprecated("Use coordinator-owned claimRun and load")
    fun claim(id: String): ApkPreparation.Prepared = error("Explicit durable Start authorization required")
    @Deprecated("Use coordinator-owned claimRun and loadRoot")
    fun claimRoot(id: String): ApkPreparation.RootPrepared = error("Explicit durable Start authorization required")
}
