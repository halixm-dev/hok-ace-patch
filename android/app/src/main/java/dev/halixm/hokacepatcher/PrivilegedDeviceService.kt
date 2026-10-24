package dev.halixm.hokacepatcher

import android.os.ParcelFileDescriptor
import android.os.Process
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * The worker, started by the chosen [ShellProvider] as shell (uid 2000) or root (uid 0). No normal application
 * Context or arbitrary command endpoint. It reads its uid on every call through [WorkerAccess] and refuses any
 * other. Shell reaches the game's files through `run-as` and the access APK; root runs the same scripts in the
 * game's data directory, gives what it creates the game's owner and label, and never installs or removes the
 * game app (ADR 0007).
 */
open class PrivilegedDeviceService : IPrivilegedDeviceService.Stub() {
    companion object {
        const val GAME = "com.tencent.tmgp.osgame"
        const val FIXTURE = "io.github.hokace.fixture"
        const val PROTOCOL_VERSION = 12
        /** Root writes the game's files itself; an APK install or removal under root is a bug, refused here. */
        const val ROOT_INSTALLS = "Root never installs or removes the game app"
        /** The UI matches on it; keep it free of any shell provider's name and of "permission". */
        const val GAME_MISSING = "The game is not installed for the phone's main user"
        private const val MAX_DIAGNOSTIC = 16384
        /** The rule files run-as reads to enter an app. Shell may read them; an app process may not. */
        private val SEAPP_CONTEXTS = listOf("/system/etc/selinux/plat_seapp_contexts",
            "/system_ext/etc/selinux/system_ext_seapp_contexts", "/product/etc/selinux/product_seapp_contexts",
            "/vendor/etc/selinux/vendor_seapp_contexts", "/odm/etc/selinux/odm_seapp_contexts")
        private const val POLICY_LINES = 40
        /** Never force-stopped as the home app: the system, the targets, the patcher and Shizuku. */
        private val NEVER_STOPPED = setOf("android", "com.android.settings", GAME, FIXTURE,
            "dev.halixm.hokacepatcher", "moe.shizuku.privileged.api")
    }

    // Only the debug source set overrides this, with a fixed disposable fixture package.
    protected open val dataPackage: String get() = GAME
    // The release service always targets GAME. Only a debug-only fixture service overrides this.
    protected open val installerPackage: String get() = GAME

    private val access: WorkerAccess get() = WorkerAccess.of(Process.myUid())

    private fun requireInstalls() = check(access == WorkerAccess.SHELL) { ROOT_INSTALLS }

    /** [script] in the game's data directory: as the game through `run-as`, or as root in that directory. */
    private fun inGame(script: String): List<String> = when (access) {
        WorkerAccess.SHELL -> listOf("/system/bin/run-as", dataPackage, "/system/bin/sh", "-c", script)
        WorkerAccess.ROOT -> listOf("/system/bin/sh", "-c", "cd '/data/user/0/$dataPackage' || exit 1; $script")
    }

    private fun requireShell() {
        check(installerPackage in setOf(GAME, FIXTURE) && dataPackage in setOf(GAME, FIXTURE)) { "Unsupported fixed device target" }
        access
        check(command(listOf("/system/bin/am", "get-current-user")).trim() == "0") {
            "Only the primary Android user is supported"
        }
    }

    private fun command(args: List<String>, input: ByteArray? = null, timeoutSeconds: Long = 30): String =
        String(binaryCommand(args, input, timeoutSeconds = timeoutSeconds), Charsets.UTF_8)

    private fun binaryCommand(args: List<String>, input: ByteArray? = null, inputFile: File? = null,
                              descriptor: ParcelFileDescriptor? = null, timeoutSeconds: Long = 30): ByteArray {
        val process = ProcessBuilder(args).start()
        val pool = Executors.newFixedThreadPool(3)
        try {
            fun drain(stream: java.io.InputStream): ByteArray {
                val result = ByteArrayOutputStream()
                val buffer = ByteArray(4096)
                stream.use {
                    while (true) {
                        val count = it.read(buffer)
                        if (count < 0) break
                        // Continue draining even after the diagnostic limit.
                        result.write(buffer, 0, minOf(count, MAX_DIAGNOSTIC - result.size()))
                    }
                }
                return result.toByteArray()
            }
            val out = pool.submit<ByteArray> { drain(process.inputStream) }
            val err = pool.submit<ByteArray> { drain(process.errorStream) }
            val writer = pool.submit {
                process.outputStream.use { output ->
                    if (input != null) output.write(input)
                    if (inputFile != null) inputFile.inputStream().use { it.copyTo(output) }
                    if (descriptor != null) ParcelFileDescriptor.AutoCloseInputStream(descriptor)
                        .use { it.copyTo(output) }
                }
            }
            check(process.waitFor(timeoutSeconds, TimeUnit.SECONDS)) {
                "Device command ${args.getOrNull(1)} timed out (${timeoutSeconds}s)"
            }
            val stderr = String(err.get(5, TimeUnit.SECONDS), Charsets.UTF_8)
            val stdout = out.get(5, TimeUnit.SECONDS)
            check(process.exitValue() == 0) {
                "Device command failed (${process.exitValue()}): $stderr\n${String(stdout, Charsets.UTF_8)}".trim()
            }
            writer.get(5, TimeUnit.SECONDS)
            return stdout
        } finally {
            process.destroyForcibly()
            pool.shutdownNow()
        }
    }

    private fun gameApk(): File {
        requireShell()
        val listing = try { command(listOf("/system/bin/pm", "path", "--user", "0", installerPackage)) }
        catch (error: IllegalStateException) {
            // `pm path` exits 1 and prints nothing when the package is not installed for that user.
            if (error.message == "Device command failed (1):") {
                val states = runCatching { FirstSetupPackagePolicy.userStates(gameDump()) }.getOrElse { "states unreadable" }
                error("$GAME_MISSING ($installerPackage; $states)")
            }
            throw error
        }
        val paths = listing.lineSequence().filter { it.isNotBlank() }.toList()
        check(paths.size == 1 && paths[0].startsWith("package:/data/app/") &&
            paths[0].endsWith("/base.apk")) { "Game is absent or uses unsupported split APKs" }
        return File(paths.single().removePrefix("package:"))
    }

    @Synchronized override fun diagnostics(): String {
        requireShell()
        return JSONObject().put("uid", Process.myUid()).put("access", access.name.lowercase())
            .put("selinux", command(listOf("/system/bin/id", "-Z")).trim())
            .put("user", 0).put("apk_package", installerPackage).put("data_package", dataPackage)
            .put("run_as_policy", runAsPolicy()).toString()
    }

    /**
     * What decides whether run-as may enter the game: SELinux enforcement, each rule file's run-as lines
     * (numbered, since the first matching line wins), and any `su` on shell's path. A refused read is named.
     */
    private fun runAsPolicy(): JSONObject {
        val rules = JSONObject()
        for (path in SEAPP_CONTEXTS) {
            val file = File(path)
            rules.put(path, if (!file.exists()) "absent" else runCatching {
                JSONArray(file.readLines().withIndex().filter { it.value.contains("runas", ignoreCase = true) }
                    .take(POLICY_LINES).map { "${it.index + 1}: ${it.value.take(300)}" })
            }.getOrElse { "unreadable (${it.javaClass.simpleName})" })
        }
        val su = System.getenv("PATH").orEmpty().split(':').filter { it.isNotEmpty() && File(it, "su").exists() }
        return JSONObject()
            .put("enforce", runCatching { command(listOf("/system/bin/getenforce")).trim() }
                .getOrElse { "unreadable (${it.message})" })
            .put("seapp_contexts", rules).put("su", JSONArray(su.map { "$it/su" }))
    }

    @Synchronized override fun gameApkInfo(): String {
        val apk = gameApk()
        return JSONObject().put("path", apk.path).put("bytes", apk.length()).put("package", installerPackage).toString()
    }

    @Synchronized override fun copyGameApk(destination: ParcelFileDescriptor): String {
        val apk = gameApk()
        val beforeLength = apk.length()
        val beforeTime = apk.lastModified()
        val hash = MessageDigest.getInstance("SHA-256")
        var size = 0L
        ParcelFileDescriptor.AutoCloseOutputStream(destination).use { output ->
            apk.inputStream().use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    size += count
                    check(size <= beforeLength) { "APK changed during streaming" }
                    output.write(buffer, 0, count)
                    hash.update(buffer, 0, count)
                }
            }
        }
        check(size == beforeLength && apk.length() == beforeLength &&
            apk.lastModified() == beforeTime && gameApk().path == apk.path) { "APK changed during streaming" }
        return JSONObject().put("bytes", size)
            .put("sha256", hash.digest().joinToString("") { "%02x".format(it) }).toString()
    }

    @Synchronized override fun probeFixture(payload: ByteArray): ByteArray {
        requireShell()
        require(payload.size in 1..4096) { "Probe payload must be 1–4096 bytes" }
        // Fixed disposable package, exclusive scratch directory, trap removes it on failure too.
        val script = "mkdir -p files && d=\$(mktemp -d files/hok-probe.XXXXXX) || exit 1; " +
            "trap 'rm -rf \"\$d\"' EXIT; cat > \"\$d/payload\" && cat \"\$d/payload\""
        val result = binaryCommand(listOf("/system/bin/run-as", FIXTURE, "/system/bin/sh", "-c", script), payload)
        check(result.contentEquals(payload)) { "Fixture binary read-back differs" }
        return result
    }

    /**
     * The home app keeps each replaced game APK (~2.4 GB) on storage until it restarts: one measured
     * force-stop of the launcher freed 9.45 GiB after a few patch runs. Restarting it is the only release
     * shell has. Skipped when no single default home app resolves.
     */
    @Synchronized override fun releaseReplacedGameApks(): String {
        requireShell()
        val resolved = command(listOf("/system/bin/cmd", "package", "resolve-activity", "--brief", "--user", "0",
            "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")).trim().lines().last().trim()
        val home = resolved.substringBefore('/', "")
        val result = JSONObject().put("home", home)
        if (!Regex("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+").matches(home) || home in NEVER_STOPPED) {
            return result.put("released", false).put("freed_bytes", 0L).toString()
        }
        val before = android.os.StatFs("/data").availableBytes
        command(listOf("/system/bin/am", "force-stop", "--user", "0", home))
        // Only a measurement for the log: the space returns once the last holder of the old APK is gone.
        var freed = 0L
        for (attempt in 0 until 5) {
            freed = maxOf(0L, android.os.StatFs("/data").availableBytes - before)
            if (freed > 0) break
            Thread.sleep(200)
        }
        android.util.Log.i("HokAceDevice", "Home app $home restarted; $freed bytes freed")
        return result.put("released", true).put("freed_bytes", freed).toString()
    }

    @Synchronized override fun forceStopGame() {
        requireShell()
        command(listOf("/system/bin/am", "force-stop", "--user", "0", installerPackage))
    }

    @Synchronized override fun reinstallFixture(abandonAfterWrite: Boolean): String {
        requireShell()
        requireInstalls()
        // Replay only the fixture's own currently installed APK. No caller-supplied APK/path.
        val paths = command(listOf("/system/bin/pm", "path", "--user", "0", FIXTURE))
            .lineSequence().filter { it.isNotBlank() }.toList()
        check(paths.size == 1 && paths[0].startsWith("package:/data/app/") &&
            paths[0].endsWith("/base.apk")) { "Install the unsplit disposable fixture first" }
        val apk = File(paths.single().removePrefix("package:"))
        check(apk.length() in 1..(16L * 1024 * 1024)) { "Unexpected fixture size" }
        fun hash(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { stream ->
                val buffer = ByteArray(65536)
                while (true) {
                    val count = stream.read(buffer)
                    if (count < 0) break
                    digest.update(buffer, 0, count)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }
        val size = apk.length()
        val digest = hash(apk)
        val created = command(listOf("/system/bin/pm", "install-create", "-r", "-t",
            "--user", "0", "-S", size.toString())).trim()
        val session = Regex("Success: created install session \\[([0-9]+)\\]")
            .matchEntire(created)?.groupValues?.get(1)
            ?: error("Fixture session creation failed: $created")
        var committed = false
        var abandoned = false
        try {
            val written = String(binaryCommand(listOf("/system/bin/pm", "install-write", "-S",
                size.toString(), session, "base.apk", "-"), inputFile = apk), Charsets.UTF_8)
            check(written.trim().startsWith("Success")) { "Fixture session write failed: $written" }
            check(apk.length() == size && hash(apk) == digest) { "Fixture source changed" }
            if (abandonAfterWrite) {
                check(command(listOf("/system/bin/pm", "install-abandon", session)).trim() == "Success") {
                    "Fixture session abandon failed"
                }
                abandoned = true
                check(runCatching { command(listOf("/system/bin/pm", "install-commit", session)) }.isFailure) {
                    "Abandoned fixture session was still committable"
                }
                val current = command(listOf("/system/bin/pm", "path", "--user", "0", FIXTURE)).trim()
                check(current == paths.single() && hash(apk) == digest) { "Abandon changed the installed fixture" }
                return JSONObject().put("session", session).put("abandoned", true)
                    .put("installed_sha256", digest).put("commit_rejected", true).toString()
            }
            val result = command(listOf("/system/bin/pm", "install-commit", session)).trim()
            check(result == "Success") { "Fixture session commit failed: $result" }
            committed = true
            val installed = command(listOf("/system/bin/pm", "path", "--user", "0", FIXTURE)).trim()
            check(installed.startsWith("package:/data/app/") && installed.endsWith("/base.apk") &&
                !installed.contains('\n')) { "Unexpected fixture installed path" }
            check(hash(File(installed.removePrefix("package:"))) == digest) { "Fixture installed hash differs" }
            return JSONObject().put("session", session).put("sha256", digest)
                .put("bytes", size).put("installed_readback", true).toString()
        } finally {
            if (!committed && !abandoned) {
                try { command(listOf("/system/bin/pm", "install-abandon", session)) }
                catch (_: Exception) { /* Preserve the original diagnostic. */ }
            }
        }
    }

    @Synchronized override fun replaceGameApk(source: ParcelFileDescriptor, length: Long): String {
        try {
            requireShell()
            requireInstalls()
            gameApk() // Require an existing unsplit installation; this endpoint cannot uninstall it.
            return installGame(source, length, true)
        } finally { runCatching { source.close() } }
    }

    @Synchronized override fun firstSetupGameAbsent(): Boolean {
        requireShell()
        // Include retained/uninstalled package records: a signer-changing install needs true absence.
        return FirstSetupPackagePolicy.gameAbsent(installerPackage) { command(it) }
    }

    private fun requireNoOtherGameUsers() =
        FirstSetupPackagePolicy.requireNoOtherUsers(installerPackage, { command(it) }, ::gameDump)

    /** The game's `dumpsys package` record cut to the lines [FirstSetupPackagePolicy] reads; empty when there is none. */
    private fun gameDump(): String {
        // `exit 0`: grep finds nothing when the package is gone, which each caller then decides.
        val script = "/system/bin/dumpsys package $installerPackage | " +
            "/system/bin/grep -E '${FirstSetupPackagePolicy.DUMPSYS_FILTER}'; exit 0"
        return command(listOf("/system/bin/sh", "-c", script), timeoutSeconds = 60)
    }

    /** Read-only: the first-setup profile refusal, run before preparation spends minutes copying the game. */
    @Synchronized override fun checkGameProfiles() {
        requireShell()
        requireNoOtherGameUsers()
    }

    @Synchronized override fun validateFirstSetupSource(expectedSourceSha256: String) {
        require(expectedSourceSha256.matches(Regex("[0-9a-f]{64}"))) { "Invalid first setup source identity" }
        requireShell()
        requireNoOtherGameUsers()
        val apk = gameApk()
        val size = apk.length()
        check(size in 1..(3L * 1024 * 1024 * 1024)) { "Unsupported first setup source size" }
        val modified = apk.lastModified()
        check(ApkIdentity.digest(apk) == expectedSourceSha256 && apk.length() == size &&
            apk.lastModified() == modified && gameApk().path == apk.path) { "Installed game changed before first setup" }
    }

    @Synchronized override fun removeGameForFirstSetup(expectedSourceSha256: String) {
        requireInstalls()
        validateFirstSetupSource(expectedSourceSha256)
        requireNoOtherGameUsers()
        // No -k: the confirmed signature conversion deliberately removes local game data.
        check(command(listOf("/system/bin/pm", "uninstall", installerPackage), timeoutSeconds = 180).trim() == "Success") {
            "First setup uninstall failed"
        }
        check(firstSetupGameAbsent()) { "Game package remains after first setup uninstall" }
    }

    @Synchronized override fun installFirstSetupGame(source: ParcelFileDescriptor, length: Long): String {
        try {
            requireShell()
            requireInstalls()
            requireNoOtherGameUsers()
            check(firstSetupGameAbsent()) { "First setup cannot replace an installed game" }
            return installGame(source, length, false)
        } finally { runCatching { source.close() } }
    }

    private fun installGame(source: ParcelFileDescriptor, length: Long, replace: Boolean): String {
        require(length in 1..(3L * 1024 * 1024 * 1024)) { "Unsupported game APK length" }
        val args = mutableListOf("/system/bin/pm", "install-create")
        // Android's shell defaults to replacement; omitting -r does not disable it.
        args.add(if (replace) "-r" else "-R")
        args.addAll(listOf("--user", "0", "--pkg", installerPackage, "-S", length.toString()))
        val created = command(args).trim()
        val session = Regex("Success: created install session \\[([0-9]+)\\]")
            .matchEntire(created)?.groupValues?.get(1)
            ?: error("Game session creation failed: $created")
        var committed = false
        try {
            android.util.Log.i("HokAceDevice", "Game install session $session created")
            val written = String(binaryCommand(listOf("/system/bin/pm", "install-write", "-S",
                length.toString(), session, "base.apk", "-"), descriptor = source,
                timeoutSeconds = 180), Charsets.UTF_8)
            check(written.trim().startsWith("Success")) { "Game session write failed: $written" }
            android.util.Log.i("HokAceDevice", "Game install session $session written")
            val result = command(listOf("/system/bin/pm", "install-commit", session), timeoutSeconds = 180).trim()
            check(result == "Success") { "Game session commit failed: $result" }
            android.util.Log.i("HokAceDevice", "Game install session $session committed")
            committed = true
            // Never fails the install: the space is only held until the home app restarts anyway.
            runCatching { releaseReplacedGameApks() }
                .onFailure { android.util.Log.w("HokAceDevice", "Home app restart skipped", it) }
            return JSONObject().put("session", session).put("bytes", length).toString()
        } finally {
            try { source.close() } catch (_: Exception) { }
            if (!committed) {
                try { command(listOf("/system/bin/pm", "install-abandon", session)) }
                catch (_: Exception) { }
            }
        }
    }

    @Synchronized override fun probeGame(payload: ByteArray): String {
        requireShell()
        require(payload.size in 1..4096) { "Probe payload must be 1–4096 bytes" }
        val info = command(inGame("cat files/QtsVFSCache/packages/1/1.info"))
        val script = "mkdir -p files && d=\$(mktemp -d files/hok-shizuku-probe.XXXXXX) || exit 1; " +
            "trap 'rm -rf \"\$d\"' EXIT; cat > \"\$d/payload\" && cat \"\$d/payload\""
        val result = binaryCommand(inGame(script), payload)
        check(result.contentEquals(payload)) { "Game binary read-back differs" }
        return JSONObject().put("data_info", info).put("roundtrip_bytes", result.size).toString()
    }

    private fun boundedRead(descriptor: ParcelFileDescriptor, maximum: Int): ByteArray {
        val result = ByteArrayOutputStream()
        ParcelFileDescriptor.AutoCloseInputStream(descriptor).use { input ->
            val buffer = ByteArray(4096)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                check(result.size() + count <= maximum) { "Descriptor payload is oversized" }
                result.write(buffer, 0, count)
            }
        }
        return result.toByteArray()
    }

    private fun lockedGameScript(body: String): String = GameFileLock.script(body, access == WorkerAccess.ROOT)

    @Synchronized override fun estimateGameSnapshot(): String {
        requireShell()
        val script = """cd files/QtsVFSCache || exit 1; sizes=@D@(find packages Watchdog -exec stat -c %s {} +) || exit 1; printf '%s\n' "@D@sizes" | awk 'NF { if (@D@0 !~ /^[0-9]+$/) exit 1; bytes += @D@0; count++ } END { printf "%.0f %.0f\n", bytes, count }'""".replace("@D@", "${'$'}")
        val fields = command(inGame(lockedGameScript(script)), timeoutSeconds = 120).trim().split(Regex("\\s+"))
        check(fields.size == 2) { "Cannot measure game snapshot" }
        val bytes = fields[0].toLong(); val count = fields[1].toLong()
        check(bytes > 0 && count in 1..8192) { "Unsupported game snapshot size/file count" }
        // At most 1024 bytes rounding/header per file, plus bounded directory headers/end padding.
        val archive = Math.addExact(Math.addExact(bytes, Math.multiplyExact(count, 1024L)), 16L * 1024 * 1024)
        check(archive <= 8L * 1024 * 1024 * 1024) { "Game snapshot exceeds supported size" }
        return JSONObject().put("bytes", bytes).put("files", count).put("archive_budget", archive).toString()
    }

    @Synchronized override fun snapshotGame(destination: ParcelFileDescriptor, maximumBytes: Long): String {
        requireShell()
        require(maximumBytes in 1..(8L * 1024 * 1024 * 1024)) { "Unsupported snapshot budget" }
        val process = ProcessBuilder(inGame(lockedGameScript("tar -cf - -C files/QtsVFSCache packages Watchdog"))).start()
        val pool = Executors.newFixedThreadPool(2)
        try {
            process.outputStream.close()
            val errors = pool.submit<String> {
                val result = ByteArrayOutputStream()
                process.errorStream.use { input ->
                    val buffer = ByteArray(4096)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        result.write(buffer, 0, minOf(count, MAX_DIAGNOSTIC - result.size()))
                    }
                }
                result.toString("UTF-8")
            }
            val transfer = pool.submit<String> {
                var bytes = 0L
                val hash = MessageDigest.getInstance("SHA-256")
                ParcelFileDescriptor.AutoCloseOutputStream(destination).use { output ->
                    process.inputStream.use { input ->
                        val buffer = ByteArray(1024 * 1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            bytes += count
                            check(bytes <= maximumBytes) { "Game snapshot exceeds its storage budget" }
                            output.write(buffer, 0, count)
                            hash.update(buffer, 0, count)
                        }
                    }
                }
                JSONObject().put("bytes", bytes)
                    .put("sha256", hash.digest().joinToString("") { "%02x".format(it) }).toString()
            }
            check(process.waitFor(900, TimeUnit.SECONDS)) { "Game snapshot timed out" }
            check(process.exitValue() == 0) { "Game snapshot failed: ${errors.get(5, TimeUnit.SECONDS)}" }
            errors.get(5, TimeUnit.SECONDS)
            return transfer.get(15, TimeUnit.SECONDS)
        } finally {
            process.destroyForcibly()
            pool.shutdownNow()
            try { destination.close() } catch (_: Exception) { }
        }
    }

    @Synchronized override fun validateGameSnapshot(manifest: ParcelFileDescriptor): String {
        requireShell()
        val value = JSONObject(String(boundedRead(manifest, 1024 * 1024), Charsets.UTF_8))
        check(value.getInt("schema") == 1) { "Unsupported snapshot manifest" }
        val files = value.getJSONObject("files")
        check(files.length() in 1..8192) { "Unsupported snapshot file count" }
        val rows = mutableListOf<String>()
        for (relative in files.keys()) {
            GameFilePolicy.validate(relative)
            val hash = files.getJSONObject(relative).getString("sha256")
            check(hash.matches(Regex("[0-9a-f]{64}"))) { "Invalid source hash" }
            rows += "$hash $relative"
        }
        val script = "cd files/QtsVFSCache || exit 1; " +
            "[ ! -L packages ] && [ ! -L Watchdog ] || exit 1; " +
            "[ -z \"\$(find packages Watchdog -type l -print)\" ] || exit 1; " +
            "count=\$(find packages Watchdog -type f | wc -l); " +
            "[ \"\$count\" -eq ${files.length()} ] || { echo 'Game file set changed' >&2; exit 1; }; " +
            "while read -r expected path; do " +
            "actual=\$(sha256sum \"\$path\") || exit 1; actual=\${actual%% *}; " +
            "[ \"\$actual\" = \"\$expected\" ] || { echo \"Game file changed: \$path\" >&2; exit 1; }; " +
            "done; printf 'verified'"
        check(command(inGame(lockedGameScript(script)),
            (rows.joinToString("\n") + "\n").toByteArray(Charsets.UTF_8), timeoutSeconds = 900) == "verified")
        return JSONObject().put("verified_files", files.length()).toString()
    }

    @Synchronized override fun writeGameFile(session: String, relative: String,
        source: ParcelFileDescriptor, length: Long, sha256: String): String {
        requireShell()
        GameFilePolicy.session(session)
        GameFilePolicy.validate(relative, writable = true)
        require(length in 0..(3L * 1024 * 1024 * 1024) && source.statSize == length) { "Invalid source length" }
        require(sha256.matches(Regex("[0-9a-f]{64}"))) { "Invalid staged hash" }
        val target = "files/QtsVFSCache/$relative"
        val parent = target.substringBeforeLast('/')
        val temp = "$parent/.${target.substringAfterLast('/')}.hok-$session.tmp"
        val script = GameFilePolicy.parentChecks(relative) + " && [ -d '$parent' ] || exit 1; " +
            "[ ! -e '$temp' ] && [ ! -L '$temp' ] || { echo 'Unresolved session temporary file' >&2; exit 1; }; " +
            "trap 'rm -f \"$temp\"' EXIT; cat > '$temp' && own '$temp' || exit 1; " +
            "[ \"\$(stat -c %s '$temp')\" -eq $length ] || exit 1; " +
            "actual=\$(sha256sum '$temp'); actual=\${actual%% *}; " +
            "[ \"\$actual\" = '$sha256' ] || { echo 'Staged file hash differs' >&2; exit 1; }; " +
            "sync '$temp' && mv -f '$temp' '$target' && sync '$parent' || exit 1; " +
            "sha256sum '$target'"
        try {
            val result = String(binaryCommand(inGame(lockedGameScript(script)),
                descriptor = source, timeoutSeconds = 900), Charsets.UTF_8)
            check(result.substringBefore(' ') == sha256) { "Installed file read-back differs" }
            return JSONObject().put("relative", relative).put("sha256", sha256).put("bytes", length).toString()
        } finally { try { source.close() } catch (_: Exception) { } }
    }

    /**
     * Delete one package file so the game downloads it again. It must still hold <sha256>, the snapshot's
     * bytes, so rollback can write it back; a file already gone counts as deleted.
     */
    @Synchronized override fun deleteGameFile(session: String, relative: String, sha256: String) {
        requireShell()
        GameFilePolicy.session(session)
        GameFilePolicy.validate(relative, writable = true)
        require(sha256.matches(Regex("[0-9a-f]{64}"))) { "Invalid original hash" }
        val target = "files/QtsVFSCache/$relative"
        val parent = target.substringBeforeLast('/')
        val script = GameFilePolicy.parentChecks(relative) + " && [ -d '$parent' ] || exit 1; " +
            "if [ -e '$target' ]; then actual=\$(sha256sum '$target') || exit 1; actual=\${actual%% *}; " +
            "[ \"\$actual\" = '$sha256' ] || { echo 'Game file changed before deletion' >&2; exit 1; }; " +
            "rm -f '$target' && sync '$parent' || exit 1; fi; " +
            "[ ! -e '$target' ] && printf 'deleted'"
        check(command(inGame(lockedGameScript(script)),
            timeoutSeconds = 900) == "deleted") { "Game file deletion was not confirmed" }
    }

    @Synchronized override fun clearSessionTemp(session: String, relative: String) {
        requireShell()
        GameFilePolicy.session(session)
        GameFilePolicy.validate(relative, writable = true)
        val target = "files/QtsVFSCache/$relative"
        val temp = "${target.substringBeforeLast('/')}/.${target.substringAfterLast('/')}.hok-$session.tmp"
        command(inGame(lockedGameScript(GameFilePolicy.parentChecks(relative) + " && rm -f '$temp'")), timeoutSeconds = 900)
    }

    @Synchronized override fun clearGameWatchdog() {
        requireShell()
        command(inGame(lockedGameScript(
            "[ ! -L files/QtsVFSCache/Watchdog ] && " +
                "rm -rf files/QtsVFSCache/Watchdog && mkdir files/QtsVFSCache/Watchdog && own files/QtsVFSCache/Watchdog && " +
                "sync files/QtsVFSCache/Watchdog && sync files/QtsVFSCache")), timeoutSeconds = 900)
    }

    @Synchronized override fun restoreWatchdogDirectory(relative: String) {
        requireShell()
        GameFilePolicy.watchdogDirectory(relative)
        val parts = relative.split('/')
        var path = "files/QtsVFSCache"
        val checks = mutableListOf("[ ! -L files ]", "[ ! -L '$path' ]")
        val directories = mutableListOf(path)
        for (part in parts) {
            path += "/$part"
            checks += "[ ! -L '$path' ]"
            directories += path
        }
        command(inGame(lockedGameScript(
            checks.joinToString(" && ") + " && mkdir -p '$path' && " +
                directories.drop(1).joinToString(" && ") { "own '$it'" } + " && " +
                directories.asReversed().joinToString(" && ") { "sync '$it'" })), timeoutSeconds = 900)
    }

    override fun destroy() { kotlin.system.exitProcess(0) }
}
