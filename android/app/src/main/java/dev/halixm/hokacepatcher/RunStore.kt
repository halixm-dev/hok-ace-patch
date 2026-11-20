package dev.halixm.hokacepatcher

import android.content.Context
import android.provider.Settings
import android.util.AtomicFile
import java.io.File
import java.io.RandomAccessFile
import java.nio.channels.OverlappingFileLockException
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermission
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import org.json.JSONObject

/** Durable ordinary Start authority. Receipts and worker-state.json are never permission.
 * Lock order: sessions/coordinator.lock, then runs/store.lock. All updates reread disk.
 * Thread ownership permits coordinator callbacks without reacquiring the same OS lock.
 */
class RunStore(private val context: Context) {
    private val base = context.filesDir.canonicalFile
    private val root = File(base, "runs")

    data class Target(val device: String, val androidUser: Int, val packageName: String) {
        fun json() = JSONObject().put("device", device).put("android_user", androidUser).put("package", packageName)
        companion object {
            fun local(context: Context): Target {
                check(android.os.Process.myUid() / 100000 == 0) { "Only the primary Android user is supported" }
                val id = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
                check(!id.isNullOrBlank()) { "Device identity is unavailable" }
                return Target(id, 0, PrivilegedDeviceService.GAME)
            }
        }
    }
    data class Run(val id: String, val action: String, val language: String, val provider: ShellProvider,
                   val target: Target, val sessionId: String, val continuation: Boolean,
                   val stopRequested: Boolean, val lifecycle: String, val preparation: JSONObject?,
                   val attempts: JSONObject, val authorizationKey: String, val inputIdentity: JSONObject?,
                   val lastOperation: String? = null, val failure: JSONObject? = null, val waiting: String? = null,
                   val redownload: Redownload? = null, val sourceDownloads: String? = null,
                   val redownloadedPackages: List<String> = emptyList()) {
        val mayContinue: Boolean get() = continuation && !stopRequested && lifecycle !in TERMINAL
        /** The logical operation and class of the last failure, if any (`failure`). */
        val failedOperation: String? get() = failure?.getString("operation")
        val failureClass: String? get() = failure?.getString("class")
        /**
         * The last failed operation used its initial attempt and its one automatic retry (its [beginAttempt]
         * count is 2): the action waits for an explicit Retry. Survives reopen.
         */
        val retryExhausted: Boolean get() = failedOperation?.let { attempts.optInt(it, 0) >= 2 } ?: false
    }

    companion object {
        private const val MAX_BYTES = ArtifactReceipts.MAX_JSON
        private val HASH = Regex("[0-9a-f]{64}")
        private val ACTIONS = setOf("translate", "remove", "first_setup", "redownload")
        private val TERMINAL = setOf("complete", "stopped")
        private val owner = ThreadLocal<String?>()
        /** One in-process mutex per store lock file ([storeLocked]); the OS lock alone throws in-process. */
        private val storeMutexes = ConcurrentHashMap<String, ReentrantLock>()
        /** How long an in-process caller waits for another thread's (short) store update. */
        private const val STORE_WAIT_MS = 3_000L
        /** Attempts key for a failure before any logical operation began (provider, worker start). */
        const val START_OPERATION = "start"
        /** Why a saved action waits: its provider to return, or an explicit Retry after its budget. */
        val WAITING = setOf("provider", "explicit_retry", "storage")
        private val OPERATION = Regex("[a-z][a-z0-9_]{0,63}")
        private val FAILURE_CLASS = Regex("[a-z][a-z0-9_]{0,31}")
        /** A game package folder name, as in `redownloaded_packages`. */
        private val PACKAGE = Regex("[0-9]{1,20}")
        private val OPTIONAL = setOf("last_operation", "failure", "waiting", "redownload", "source_download",
            "redownloaded_packages")
        /** Operations an explicit Retry never re-arms; destructive work needs its own fresh consent instead. */
        private val SAFETY_OPERATIONS = setOf("recovery_access_audit", "recovery_rollback_access",
            "recovery_normal_restore", "recovery_emergency_normal")
        private val NEVER_REARMED = setOf("uninstall", "first_setup", RedownloadConsent.DELETE_OPERATION)
        /**
         * One shared kernel lock for preparation, claims, setup and recovery. Busy flags are projections.
         * It is held for a whole run, so a second holder, in this process or another, is refused at once
         * (never waited on); an in-process `tryLock` throws instead of returning null, and is mapped to the
         * same refusal.
         */
        fun <T> coordinator(context: Context, action: () -> T): T {
            val base = context.filesDir.canonicalFile
            if (owner.get() == base.path) return action()
            check(owner.get() == null) { "Cannot nest coordinators for different roots" }
            val sessions = File(base, "sessions")
            DurableFiles.createDirectories(sessions)
            safe(base, sessions, true)
            val lockFile = File(sessions, "coordinator.lock")
            if (lockFile.exists() || Files.isSymbolicLink(lockFile.toPath())) safe(base, lockFile)
            RandomAccessFile(lockFile, "rw").use { handle ->
                val held = try { handle.channel.tryLock() } catch (_: OverlappingFileLockException) { null }
                checkNotNull(held) { "Another patch, setup or recovery is running" }.use {
                    owner.set(base.path)
                    try { return action() } finally { owner.remove() }
                }
            }
        }
        /**
         * The app's private files folder, canonicalized once: every private record path is built from it,
         * so [safe]'s exact canonical comparison holds. Android may reach the app's data folder through its
         * own per-user alias (`/data/user/0/<package>` for `/data/data/<package>`); that alias, at or above
         * the data folder, is the only one trusted. Every folder from the data folder down to the files
         * folder must be unlinked and resolve to the same relative path under the canonical data folder.
         */
        fun privateRoot(context: Context): File {
            val files = context.filesDir.absoluteFile.toPath().normalize()
            val data = context.dataDir.absoluteFile.toPath().normalize()
            val canonicalData = context.dataDir.canonicalFile.toPath()
            val from = listOf(data, canonicalData).firstOrNull { files.startsWith(it) && files != it }
            checkNotNull(from) { "Private files folder is outside the app data folder" }
            var current = files
            while (current != from) {
                check(!Files.isSymbolicLink(current)) { "Linked private root" }
                current = checkNotNull(current.parent)
            }
            check(!Files.isSymbolicLink(from)) { "Linked app data folder" }
            val canonical = context.filesDir.canonicalFile
            check(canonical.toPath() == canonicalData.resolve(from.relativize(files))) { "Private path alias" }
            return canonical
        }
        internal fun requireCoordinator(context: Context) {
            check(ownsCoordinator(context)) { "Coordinator ownership required" }
        }
        /** Whether this thread holds the coordinator lock for <context>'s private root. */
        internal fun ownsCoordinator(context: Context): Boolean = owner.get() == context.filesDir.canonicalPath
        internal fun safe(base: File, file: File, directory: Boolean = false) {
            val path = file.absoluteFile.toPath().normalize()
            check(path.startsWith(base.toPath()) && path != base.toPath()) { "Record escaped private root" }
            var current = path
            while (current != base.toPath()) {
                check(!Files.isSymbolicLink(current)) { "Linked private record" }
                current = checkNotNull(current.parent)
            }
            check(file.canonicalFile.toPath() == path) { "Private path alias" }
            check(if (directory) file.isDirectory else file.isFile) { "Missing private record" }
        }
        private val WRITABLE = setOf(PosixFilePermission.OWNER_WRITE, PosixFilePermission.GROUP_WRITE,
            PosixFilePermission.OTHERS_WRITE)
        /**
         * [safe] for a saved APK that [ApkPreparation.deduplicateApks] may have replaced by a symbolic link to an
         * identical copy: its folders are plain, and a link resolves to a plain, read-only file inside <base>. The
         * caller still verifies the bytes. 2026-11-20: a shared access APK refused the claim as a linked record.
         */
        internal fun safeShared(base: File, file: File) {
            val path = file.absoluteFile.toPath().normalize()
            if (!Files.isSymbolicLink(path)) return safe(base, file)
            safe(base, checkNotNull(path.parent).toFile(), directory = true)
            val target = file.canonicalFile
            safe(base, target)
            check(Files.getPosixFilePermissions(target.toPath()).none { it in WRITABLE }) { "Shared APK is writable" }
        }
        /**
         * [recordFailure]'s charge: whether <operation> may retry automatically. A failure that again names the
         * operation of the failure already recorded came before any new attempt began ([beginAttempt] counts
         * those), so it spends the retry. 2026-11-20: a claim refused before its operation began retried forever.
         */
        internal fun chargeFailure(attempts: JSONObject, recorded: String?, operation: String): Boolean {
            if (recorded == operation) attempts.put(operation, 2)
            return attempts.optInt(operation, 0) < 2
        }
    }

    private fun file(id: String): File { GameFilePolicy.session(id); return File(root, "$id.json") }
    private fun <T> locked(action: () -> T): T = coordinator(context) { storeLocked(action) }
    /**
     * The store lock. An OS file lock alone cannot serialize threads of one process: a second in-process
     * `tryLock` throws [OverlappingFileLockException] (the 2026-11-12 device cycle: the automatic retry's
     * `pending()` raced another UI read and failed the retry with "ERROR: null"). So in-process callers first
     * queue on one mutex per store folder (bounded: every store update is short), and a nested call on the
     * same thread reuses the lock it holds. The file lock then keeps exclusivity against another process,
     * which is refused as before rather than waited on.
     */
    private fun <T> storeLocked(action: () -> T): T {
        DurableFiles.createDirectories(root); safe(base, root, true)
        val lock = File(root, "store.lock")
        if (lock.exists() || Files.isSymbolicLink(lock.toPath())) safe(base, lock)
        val mutex = storeMutexes.computeIfAbsent(lock.path) { ReentrantLock() }
        if (mutex.isHeldByCurrentThread) return action()
        check(mutex.tryLock(STORE_WAIT_MS, TimeUnit.MILLISECONDS)) { "Another run update is in progress" }
        try {
            RandomAccessFile(lock, "rw").use { handle ->
                val held = try { handle.channel.tryLock() } catch (_: OverlappingFileLockException) { null }
                checkNotNull(held) { "Another run update is in progress" }.use { return action() }
            }
        } finally { mutex.unlock() }
    }
    private fun read(id: String): JSONObject {
        val path = file(id)
        listOf(path, File(path.path + ".bak"), File(path.path + ".new")).filter { it.exists() || Files.isSymbolicLink(it.toPath()) }.forEach {
            safe(base, it); check(it.length() in (if (it.name.endsWith(".new")) 0 else 1)..MAX_BYTES) { "Run record oversized" }
        }
        val bytes = DurableFiles.readCommitted(path)
        check(bytes.size in 1..MAX_BYTES)
        return ArtifactReceipts.parse(bytes).also { validate(id, it) }
    }
    private fun fields(value: JSONObject, expected: Set<String>) {
        check(value.keys().asSequence().toSet() == expected) { "Unknown or missing run fields" }
    }
    private fun integer(value: JSONObject, key: String): Long {
        val raw = value.get(key); check(raw is Int || raw is Long) { "Expected integer $key" }; return (raw as Number).toLong()
    }
    private fun bool(value: JSONObject, key: String): Boolean {
        val raw = value.get(key); check(raw is Boolean) { "Expected Boolean $key" }; return raw
    }
    private fun requireStrings(value: JSONObject, vararg names: String) { names.forEach { check(value.get(it) is String) } }
    private fun apk(value: JSONObject) {
        fields(value, setOf("bytes", "sha256", "package", "version_code", "version_name", "certificate_sha256", "debuggable"))
        check(integer(value, "bytes") in 1..(3L * 1024 * 1024 * 1024) && integer(value, "version_code") >= 0)
        requireStrings(value, "sha256", "package", "version_name", "certificate_sha256"); bool(value, "debuggable")
        check(HASH.matches(value.getString("sha256")) && HASH.matches(value.getString("certificate_sha256")) && value.getString("package") == PrivilegedDeviceService.GAME)
    }
    private fun validate(id: String, value: JSONObject) {
        fields(value, setOf("schema", "id", "session_id", "authorization", "authorization_key", "continuation", "stop_requested", "lifecycle", "attempts", "preparation", "input_identity", "record_sha256") +
            value.keys().asSequence().filter { it in OPTIONAL })
        requireStrings(value, "id", "session_id", "authorization_key", "lifecycle", "record_sha256")
        check(integer(value, "schema") == 1L && value.getString("id") == id)
        val auth = value.getJSONObject("authorization")
        check(auth.keys().asSequence().toSet() == setOf("action", "language", "provider", "target", "work_root", "authorized_ms", "source"))
        requireStrings(auth, "action", "language", "provider", "work_root", "source")
        check(auth.getString("action") in ACTIONS && auth.getString("language") in PatchLanguage.choices)
        check(ShellProvider.entries.any { it.key == auth.getString("provider") }) { "Unknown saved provider" }
        val target = auth.getJSONObject("target")
        check(target.keys().asSequence().toSet() == setOf("device", "android_user", "package"))
        requireStrings(target, "device", "package")
        check(target.getString("device").length in 1..256 && integer(target, "android_user") == 0L &&
            target.getString("package") == PrivilegedDeviceService.GAME) { "Unsupported saved target" }
        check(auth.getString("work_root") == base.path && auth.getString("source") == "explicit_start" && integer(auth, "authorized_ms") > 0)
        check(value.getString("authorization_key") == ArtifactReceipts.identityKey(auth)) { "Authorization changed" }
        check(value.getString("session_id") == id)
        check(value.getString("lifecycle") in setOf("authorized", "prepared", "claimed", "complete", "stopped"))
        val continuation = bool(value, "continuation"); val stopped = bool(value, "stop_requested")
        check(!(continuation && stopped))
        val attempts = value.getJSONObject("attempts"); check(attempts.length() <= 64)
        for (operation in attempts.keys()) {
            check(operation.matches(Regex("[a-z][a-z0-9_]{0,63}")))
            check(integer(attempts, operation) in 1L..2L)
        }
        if (value.has("last_operation")) check(OPERATION.matches(value.get("last_operation") as String))
        if (value.has("failure")) {
            val failure = value.get("failure"); check(failure is JSONObject)
            fields(failure, setOf("operation", "class")); requireStrings(failure, "operation", "class")
            check(OPERATION.matches(failure.getString("operation")) && FAILURE_CLASS.matches(failure.getString("class")))
            check(attempts.has(failure.getString("operation"))) { "Failure of an operation that never began" }
        }
        if (value.has("waiting")) check(value.get("waiting") in WAITING)
        value.optJSONObject("source_download")?.let { source ->
            check(source.keys().asSequence().toSet() == setOf("snapshot_sha256", "state"))
            check(HASH.matches(source.getString("snapshot_sha256")))
            check(source.getString("state") in setOf("required", "confirmed"))
        }
        if (value.has("source_download")) check(value.get("source_download") is JSONObject)
        if (value.has("redownload")) {
            val redownload = value.get("redownload"); check(redownload is JSONObject)
            RedownloadConsent.validate(redownload)
        }
        if (value.has("redownloaded_packages")) {
            val packages = value.get("redownloaded_packages"); check(packages is org.json.JSONArray && packages.length() in 1..1024)
            val names = (0 until packages.length()).map { val name = packages.get(it); check(name is String && PACKAGE.matches(name)); name as String }
            check(names.toSet().size == names.size) { "Duplicate re-downloaded package" }
        }
        check(value.isNull("preparation") || value.get("preparation") is JSONObject)
        check(value.isNull("input_identity") || value.get("input_identity") is JSONObject)
        value.optJSONObject("input_identity")?.let {
            val inputTarget = it.getJSONObject("target"); val request = it.getJSONObject("request")
            check(inputTarget.get("device") == target.get("device") && integer(inputTarget, "android_user") == integer(target, "android_user") &&
                inputTarget.get("package") == target.get("package") && inputTarget.get("provider") == auth.get("provider"))
            check(request.get("action") == auth.get("action") && request.get("language") == auth.get("language"))
            ArtifactReceipts.identityKey(it)
        }
        value.optJSONObject("preparation")?.let {
            fields(it, if (bool(it, "root")) setOf("id", "receipt_sha256", "root", "source") else setOf("id", "receipt_sha256", "root", "source", "normal", "access"))
            requireStrings(it, "id", "receipt_sha256")
            GameFilePolicy.session(it.getString("id"))
            check(HASH.matches(it.getString("receipt_sha256")))
            check(it.getBoolean("root") == (auth.getString("provider") == "root"))
            apk(it.getJSONObject("source"))
            if (!it.getBoolean("root")) {
                apk(it.getJSONObject("normal")); apk(it.getJSONObject("access"))
            }
        }
        val copy = JSONObject(value.toString()); val checksum = copy.getString("record_sha256"); copy.remove("record_sha256")
        check(checksum == ArtifactReceipts.identityKey(copy)) { "Run record changed" }
    }
    private fun write(value: JSONObject) {
        value.remove("record_sha256")
        value.put("record_sha256", ArtifactReceipts.identityKey(value))
        val id = value.getString("id"); validate(id, value)
        val path = file(id)
        listOf(path, File(path.path + ".bak"), File(path.path + ".new")).filter {
            it.exists() || Files.isSymbolicLink(it.toPath())
        }.forEach { safe(base, it); check(it.length() <= MAX_BYTES) }
        val atomic = AtomicFile(path); val stream = atomic.startWrite()
        try {
            val bytes = ArtifactReceipts.canonical(value).toByteArray(Charsets.UTF_8); check(bytes.size <= MAX_BYTES)
            stream.write(bytes); stream.fd.sync(); atomic.finishWrite(stream); DurableFiles.syncDirectory(root)
        } catch (error: Throwable) { atomic.failWrite(stream); throw error }
        check(ArtifactReceipts.canonical(read(id)) == ArtifactReceipts.canonical(value)) { "Run read-back differs" }
    }
    private fun model(value: JSONObject): Run {
        val auth = value.getJSONObject("authorization"); val target = auth.getJSONObject("target")
        return Run(value.getString("id"), auth.getString("action"), auth.getString("language"),
            ShellProvider.entries.single { it.key == auth.getString("provider") },
            Target(target.getString("device"), target.getInt("android_user"), target.getString("package")),
            value.getString("session_id"), value.getBoolean("continuation"), value.getBoolean("stop_requested"),
            value.getString("lifecycle"), value.optJSONObject("preparation"), value.getJSONObject("attempts"), value.getString("authorization_key"), value.optJSONObject("input_identity"),
            value.optString("last_operation").ifEmpty { null }, value.optJSONObject("failure"), value.optString("waiting").ifEmpty { null },
            value.optJSONObject("redownload")?.let { RedownloadConsent.decode(it) }, value.optJSONObject("source_download")?.getString("state"),
            value.optJSONArray("redownloaded_packages")?.let { list -> (0 until list.length()).map { list.getString(it) } }.orEmpty())
    }
    private fun records(): List<JSONObject> {
        val ids = root.listFiles().orEmpty().filter { it.name != "store.lock" }.map {
            check(it.name.endsWith(".json") || it.name.endsWith(".json.bak") || it.name.endsWith(".json.new")) { "Unknown run material" }
            it.name.removeSuffix(".bak").removeSuffix(".new").removeSuffix(".json")
        }.distinct()
        check(ids.size <= 1024) { "Too many run records" }
        return ids.map { read(it) }
    }
    fun load(id: String): Run = storeLocked { model(read(id)) }
    fun pending(): List<Run> = storeLocked { records().map { model(it) }.filter { it.lifecycle !in TERMINAL } }

    /** Call on explicit Start, before preparation. No checkbox or expiring ordinary approval. */
    fun start(action: String, language: String, provider: ShellProvider, target: Target): Run = locked {
        check(action in ACTIONS && language in PatchLanguage.choices)
        check(target == Target.local(context)) { "Start target is not this device and Android user" }
        check(records().none { it.getString("lifecycle") !in TERMINAL }) { "Stop or finish the pending action first" }
        check(FirstSetupJournal.pending(context).isEmpty() && SessionJournal.pending(File(base, "sessions")).isEmpty()) {
            "Resolve existing recovery before Start"
        }
        val id = UUID.randomUUID().toString()
        val auth = JSONObject().put("action", action).put("language", language).put("provider", provider.key)
            .put("target", target.json()).put("work_root", base.path).put("authorized_ms", System.currentTimeMillis()).put("source", "explicit_start")
        val value = JSONObject().put("schema", 1).put("id", id).put("session_id", id).put("authorization", auth)
            .put("authorization_key", ArtifactReceipts.identityKey(auth)).put("continuation", true).put("stop_requested", false)
            .put("lifecycle", "authorized").put("attempts", JSONObject()).put("preparation", JSONObject.NULL).put("input_identity", JSONObject.NULL)
        write(value); model(value)
    }
    fun requireTarget(run: Run) { check(run.target == Target.local(context)) { "Saved action belongs to another device or Android user" } }
    private fun update(id: String, change: (JSONObject, Run) -> Unit): Run = storeLocked {
        val value = read(id); val run = model(value); requireTarget(run); change(value, run); write(value); model(value)
    }
    fun stop(id: String): Run = update(id) { value, run ->
        if (run.lifecycle !in TERMINAL) value.put("continuation", false).put("stop_requested", true)
    }

    /** Short completion linearization; all APK/artifact hashing happens before this store lock. */
    fun finishVerified(id: String, journal: SessionJournal, publish: (Boolean) -> Unit): Run = update(id) { value, run ->
        requireCoordinator(context)
        check(run.lifecycle == "claimed" && journal.runId == run.id && journal.id == run.sessionId &&
            journal.authorizationKey == run.authorizationKey && journal.payloadVerified &&
            !journal.dirtyPackages && !journal.hasMutationIntent && !journal.hasRecoveryNormalIntent &&
            journal.snapshot().optBoolean("normal_verified", false) && journal.snapshot().optBoolean("finalized", false))
        publish(run.stopRequested)
        journal.outcome(if (run.stopRequested) PatchPhase.CANCELLED else PatchPhase.COMPLETE,
            JSONObject().put("normal_verified", true).put("stopped", run.stopRequested))
        value.put("lifecycle", if (run.stopRequested) "stopped" else "complete").put("continuation", false)
    }
    /**
     * Persist an attempt of logical <operation> before it is sent: the initial attempt plus one automatic retry
     * per operation, never reset on reopen. It also names the operation a later failure is charged to.
     * Retry callers reconcile uncertain effects first. Waiting for access never calls this API.
     */
    fun beginAttempt(id: String, operation: String): Run = update(id) { value, run ->
        check(run.mayContinue) { "Run is stopped or resolved" }
        check(OPERATION.matches(operation))
        val attempts = value.getJSONObject("attempts"); val count = attempts.optInt(operation, 0)
        check(count < 2) { "Automatic attempt budget exhausted" }
        attempts.put(operation, count + 1)
        value.put("last_operation", operation)
        value.remove("waiting")
    }
    /**
     * Record a failure of the saved action, charged to the logical operation last begun ([beginAttempt]); a
     * failure before any operation began is charged to [START_OPERATION], counted here. True while that
     * operation's own budget still has its retry: the caller may retry automatically once (after reconciling).
     * False when the same operation failed on its retry; the run then waits for an explicit Retry, persistently.
     * Waiting for a provider, permission or download is not a failure and never calls this.
     */
    fun recordFailure(id: String, failureClass: String): Boolean {
        check(FAILURE_CLASS.matches(failureClass))
        var retry = false
        update(id) { value, run ->
            check(run.mayContinue) { "Run is stopped or resolved" }
            val attempts = value.getJSONObject("attempts")
            val operation = run.lastOperation ?: START_OPERATION.also {
                attempts.put(it, minOf(attempts.optInt(it, 0) + 1, 2)); value.put("last_operation", it)
            }
            retry = chargeFailure(attempts, value.optJSONObject("failure")?.optString("operation"), operation)
            value.put("failure", JSONObject().put("operation", operation).put("class", failureClass))
            if (retry) value.remove("waiting") else value.put("waiting", "explicit_retry")
        }
        return retry
    }
    /** Bounded read-back recovery access cycle; Stop never revokes mandatory safety repair. */
    fun beginSafetyAttempt(id: String, operation: String): Run = update(id) { value, run ->
        check(operation in SAFETY_OPERATIONS)
        check(run.lifecycle !in TERMINAL)
        val attempts = value.getJSONObject("attempts"); val count = attempts.optInt(operation, 0)
        check(count < 2) { "Automatic recovery audit budget exhausted; Retry is required" }
        attempts.put(operation, count + 1); value.put("last_operation", operation)
    }

    /**
     * After an ordinary stage failure triggers clean safety recovery, restore [last_operation] to the
     * operation that failed so [recordFailure] charges that stage rather than the recovery fallback.
     */
    internal fun restoreOperation(id: String, operation: String?): Run = update(id) { value, run ->
        requireCoordinator(context)
        check(operation == null || OPERATION.matches(operation))
        if (run.lifecycle !in TERMINAL) {
            if (operation == null) value.remove("last_operation") else value.put("last_operation", operation)
        }
    }

    /** Explicit Retry only: restores safety budgets without revoking Stop or granting new continuation. */
    fun rearmSafety(id: String): Run = update(id) { value, run ->
        check(run.lifecycle !in TERMINAL)
        val attempts = value.getJSONObject("attempts")
        for (operation in SAFETY_OPERATIONS) attempts.remove(operation)
        if (run.failedOperation in SAFETY_OPERATIONS) { value.remove("failure"); value.remove("waiting") }
    }

    /** A source changed during a pending action: stable hashes alone never establish update readiness. */
    fun requireSourceDownloads(id: String, snapshotSha256: String): Run = update(id) { value, run ->
        check(run.mayContinue && HASH.matches(snapshotSha256))
        val kept = value.optJSONObject("source_download")
        if (kept?.optString("snapshot_sha256") != snapshotSha256)
            value.put("source_download", JSONObject().put("snapshot_sha256", snapshotSha256).put("state", "required"))
    }
    fun confirmSourceDownloads(id: String): Run = update(id) { value, run ->
        check(run.mayContinue && run.sourceDownloads == "required")
        value.getJSONObject("source_download").put("state", "confirmed")
    }
    fun sourceDownloadsConfirmed(id: String, snapshotSha256: String): Boolean = storeLocked {
        val source = read(id).optJSONObject("source_download") ?: return@storeLocked false
        source.getString("snapshot_sha256") == snapshotSha256 && source.getString("state") == "confirmed"
    }
    fun consumeSourceDownloads(id: String): Run = update(id) { value, run ->
        check(run.mayContinue && run.sourceDownloads == "confirmed"); value.remove("source_download")
    }
    /**
     * Coordinator only: the user's answer that the game finished downloading the files an approved Re-download
     * deleted ([confirmRedownloadDownloads]) is also the source-download answer for the snapshot that deletion
     * made stale ([snapshotSha256], the snapshot saved before it). It binds that one snapshot digest, like
     * [confirmSourceDownloads]: the snapshot is still retired and retaken, the build still checks readiness,
     * and [consumeSourceDownloads] spends it once. Only [RedownloadConsent.answersSourceDownloads] grants it.
     */
    fun confirmSourceDownloadsAfterRedownload(id: String, snapshotSha256: String, deletedPlanSha256: String?): Run =
        update(id) { value, run ->
            requireCoordinator(context)
            check(HASH.matches(snapshotSha256))
            check(RedownloadConsent.answersSourceDownloads(run.mayContinue, run.redownload, deletedPlanSha256)) {
                "No confirmed Re-download download answers this change"
            }
            value.put("source_download", JSONObject().put("snapshot_sha256", snapshotSha256).put("state", "confirmed"))
        }

    /** Record why a continuing saved action waits (one of [WAITING]), or null once it goes on. Never an attempt. */
    fun waitFor(id: String, reason: String?): Run = update(id) { value, run ->
        check(reason == null || reason in WAITING)
        if (reason != null) check(run.mayContinue) { "Run is stopped or resolved" }
        if (reason == null) value.remove("waiting") else value.put("waiting", reason)
    }
    /**
     * An explicit user Retry: re-arm the safe, reconciled operations of a run that may still continue. It never
     * clears Stop, never re-arms destructive work and never grants consent; setup and Re-download consent stay
     * one-use in their own stores.
     */
    fun rearm(id: String): Run = update(id) { value, run ->
        check(run.mayContinue) { "Run is stopped or resolved" }
        val attempts = value.getJSONObject("attempts")
        for (operation in attempts.keys().asSequence().toList()) if (operation !in NEVER_REARMED) attempts.remove(operation)
        value.remove("last_operation"); value.remove("failure"); value.remove("waiting")
    }
    /**
     * Coordinator only: the exact Re-download plan a damaged-file refusal produced for this claimed action
     * ([RedownloadConsent.proposed]). <automatic> (the coordinator, user decision 2026-11-13) gives that approval
     * in the same write when [RedownloadConsent.automaticAllowed] holds, so no cut can leave a plan proposed but
     * not yet approved; otherwise the plan waits for the user's review.
     */
    fun proposeRedownload(id: String, planId: String, planSha256: String, files: Int, packages: List<String>,
                          bytes: Long, automatic: Boolean = false): Run = update(id) { value, run ->
        requireCoordinator(context)
        check(run.mayContinue && run.lifecycle == "claimed") { "Run is stopped or resolved" }
        val proposed = RedownloadConsent.proposed(run.redownload, planId, planSha256, files, packages, bytes)
        val deleteAttempts = value.getJSONObject("attempts").optInt(RedownloadConsent.DELETE_OPERATION, 0)
        if (automatic && RedownloadConsent.automaticAllowed(proposed.state, deleteAttempts, run.redownloadedPackages, proposed.packages)) {
            approve(value, proposed, RedownloadConsent.APPROVAL_AUTOMATIC, run.redownload?.state)
        } else value.put("redownload", RedownloadConsent.encode(proposed))
    }
    /**
     * Approve [plan] as <source>. A new approval is a new destructive attempt scope, and it re-arms safe work
     * too, exactly as the user's approval always did; the loop guard bounds how often that happens. An automatic
     * approval replacing an interrupted plan keeps the deletion count ([RedownloadConsent.keepsDeleteAttempts]).
     */
    private fun approve(value: JSONObject, plan: Redownload, source: String, previousState: String? = null) {
        value.put("redownload", RedownloadConsent.encode(RedownloadConsent.approved(plan, source,
            UUID.randomUUID().toString(), System.currentTimeMillis())))
        val attempts = value.getJSONObject("attempts")
        val kept = if (RedownloadConsent.keepsDeleteAttempts(source, previousState))
            setOf("uninstall", "first_setup", RedownloadConsent.DELETE_OPERATION) else setOf("uninstall", "first_setup")
        for (operation in attempts.keys().asSequence().toList()) if (operation !in kept) attempts.remove(operation)
        value.remove("last_operation"); value.remove("failure"); value.remove("waiting")
    }
    /**
     * The user's explicit approval of the exact plan [planSha256] (shown with its files and consequences). A new
     * approval is a new destructive attempt scope, and as an explicit action it re-arms safe work too. It never
     * clears Stop, and never covers a plan with another digest.
     */
    fun approveRedownload(id: String, planSha256: String): Run = update(id) { value, run ->
        check(run.mayContinue && run.lifecycle == "claimed") { "Run is stopped or resolved" }
        approve(value, RedownloadConsent.answerable(run.redownload, planSha256), RedownloadConsent.APPROVAL_USER)
    }
    /** The user declined (or dismissed) the exact plan [planSha256]: nothing is deleted, and it is not asked again by itself. */
    fun declineRedownload(id: String, planSha256: String): Run = update(id) { value, run ->
        value.put("redownload", RedownloadConsent.encode(RedownloadConsent.declined(run.redownload, planSha256)))
    }
    /** Coordinator only: progress of the approved plan [planSha256] ([RedownloadConsent.progressed]). */
    fun redownloadProgress(id: String, planSha256: String, state: String): Run = update(id) { value, run ->
        requireCoordinator(context)
        val plan = RedownloadConsent.progressed(run.redownload, planSha256, state, run.mayContinue)
        value.put("redownload", RedownloadConsent.encode(plan))
        // The loop guard's memory: every package this run deleted, whoever approved it.
        if (state == RedownloadConsent.DELETED) {
            val deleted = (run.redownloadedPackages + plan.packages).distinct()
            check(deleted.size <= 1024) { "Too many re-downloaded packages" }
            value.put("redownloaded_packages", org.json.JSONArray(deleted))
        }
    }
    /**
     * Coordinator only: the approved plan cannot go on under its approval (its deletion budget is spent), so it
     * waits for a fresh answer to the same exact plan. Nothing is deleted here.
     */
    fun requireFreshRedownloadConsent(id: String, planSha256: String): Run = update(id) { value, run ->
        requireCoordinator(context)
        value.put("redownload", RedownloadConsent.encode(RedownloadConsent.awaitingFreshConsent(run.redownload, planSha256)))
    }
    /** The user's answer that the game finished downloading the deleted files; the saved action then continues. */
    fun confirmRedownloadDownloads(id: String): Run = update(id) { value, run ->
        check(run.mayContinue) { "Run is stopped or resolved" }
        value.put("redownload", RedownloadConsent.encode(RedownloadConsent.downloadsConfirmed(run.redownload)))
    }
    internal fun bind(id: String, binding: JSONObject): Run = update(id) { value, run ->
        check(run.mayContinue && run.lifecycle in setOf("authorized", "prepared", "claimed")) { "Run is stopped or resolved" }
        check(run.preparation == null || ArtifactReceipts.canonical(run.preparation) == ArtifactReceipts.canonical(binding)) { "Cannot retarget prepared input" }
        value.put("preparation", binding).put("lifecycle", "prepared")
    }
    /**
     * Link the complete measured snapshot/build input identity; it is never permission. Before claim any
     * caller may bind; after claim only the coordinator owner may, because the full source manifest exists
     * only once its own snapshot is verified against the live layer. Saved action/target/provider and
     * authorization never change, and a bound identity is immutable until [invalidateInputs].
     */
    fun bindInputs(id: String, identity: JSONObject): Run = update(id) { value, run ->
        check(run.mayContinue && run.lifecycle in setOf("authorized", "prepared", "claimed"))
        if (run.lifecycle == "claimed") requireCoordinator(context)
        check(identity.getJSONObject("target").let { it.getString("device") == run.target.device &&
            it.getInt("android_user") == run.target.androidUser && it.getString("package") == run.target.packageName &&
            it.getString("provider") == run.provider.key })
        check(identity.getJSONObject("request").let { it.getString("action") == run.action && it.getString("language") == run.language })
        if (!value.isNull("input_identity")) check(ArtifactReceipts.identityKey(value.getJSONObject("input_identity")) == ArtifactReceipts.identityKey(identity))
        value.put("input_identity", ArtifactReceipts.parse(ArtifactReceipts.canonical(identity).toByteArray(Charsets.UTF_8)))
    }
    /**
     * Explicit invalidation once consistency is established: no game file is mid-change and no verified
     * payload awaits forward completion. Rebinding still checks immutable saved choices. Coordinator owner only.
     */
    fun invalidateInputs(id: String): Run = update(id) { value, run ->
        requireCoordinator(context)
        val journal = SessionJournal.load(File(base, "sessions/${run.sessionId}"))
        check(journal.runId == id && journal.authorizationKey == run.authorizationKey &&
            !journal.dirtyPackages && !journal.hasMutationIntent && !journal.hasRecoveryNormalIntent &&
            !journal.payloadVerified) { "Recover consistency before invalidation" }
        check(run.mayContinue && run.lifecycle == "claimed")
        value.put("input_identity", JSONObject.NULL)
    }
    /** Recoverable claim: repeated dispatch uses the SAME session UUID; never consumes/removes authorization. */
    fun claim(id: String, action: String, provider: ShellProvider): Run = update(id) { value, run ->
        requireCoordinator(context)
        check(run.mayContinue && run.action == action && run.provider == provider && run.preparation != null) { "Dispatch differs from saved Start" }
        check(run.lifecycle in setOf("prepared", "claimed"))
        value.put("lifecycle", "claimed")
    }
    /** Caller must finish safety recovery first; a saved status alone cannot resolve an action. */
    fun resolve(id: String): Run = coordinator(context) { update(id) { value, run ->
        check(FirstSetupJournal.pending(context).isEmpty()) { "Setup recovery still owns this action" }
        EmergencyRestoreStore(context).requireResolved()
        check(SessionJournal.pending(File(base, "sessions")).isEmpty()) { "Patch recovery remains unresolved" }
        val child = File(base, "sessions/${run.sessionId}")
        if (child.exists()) {
            val journal = SessionJournal.load(child)
            check(journal.runId == id && journal.authorizationKey == run.authorizationKey && journal.phase in setOf(PatchPhase.COMPLETE, PatchPhase.CANCELLED))
            check(journal.phase == PatchPhase.COMPLETE || run.stopRequested) { "Recovery does not finish ordinary authorization" }
            check(journal.phase != PatchPhase.COMPLETE || run.lifecycle == "complete") {
                "Split completion requires current live audit and finishVerified, not saved terminal flags"
            }
        } else check(run.stopRequested && run.lifecycle in setOf("authorized", "prepared")) { "Missing claimed journal needs recovery attention" }
        value.put("lifecycle", if (run.stopRequested) "stopped" else "complete").put("continuation", false)
    } }
}
