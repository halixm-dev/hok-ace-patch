package dev.halixm.hokacepatcher

import android.app.ActivityManager
import android.app.NotificationManager
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import android.util.Base64
import org.json.JSONObject
import rikka.shizuku.Shizuku
import java.io.File
import java.io.RandomAccessFile
import java.io.Writer
import java.nio.file.Files
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.TimeUnit

/** Read-only, bounded raw diagnostics remain exportable when recovery records cannot be loaded. */
class DiagnosticLogExport(private val context: Context) {
    fun write(output: Writer) {
        val root = context.filesDir
        output.write("HOK ACE diagnostics. Raw records below are UNVALIDATED evidence, not recovery authorization.\n")
        section(output, "Environment") { environment(it) }
        section(output, "Previous app process exits") { exits(it) }
        section(output, "App storage") { storage(it) }
        var remaining = TOTAL_BYTES
        val runs = mutableListOf<File>()
        fun record(relative: String, tail: Boolean = false, tailBytes: Int = LOG_BYTES) {
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
            val limit = if (tail) tailBytes else RECORD_BYTES
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
                runs += path.toFile()
                if (!File(path.toFile(), "journal.json").isFile &&
                    !File(path.toFile(), "journal.json.bak").isFile)
                    output.write("Published journal missing: $folder/$name\n")
            }
        }
        record("emergency-restore.json")
        record("emergency-restore.json.bak")
        // After the recovery records, so the shared byte limit never drops a journal for trace lines.
        record(DiagnosticTrace.PREVIOUS, true, TRACE_BYTES)
        record(DiagnosticTrace.FILE, true, TRACE_BYTES)
        for (folder in runs.sortedByDescending { it.lastModified() }.take(RECENT_RUNS)) {
            val relative = "${folder.parentFile!!.name}/${folder.name}"
            record("$relative/build.log", true)
            record("$relative/metrics.json")
        }
        section(output, "App logcat (this app's own lines only)") { logcat(it) }
        output.flush()
    }

    /** Each section is best-effort: a query this phone refuses is named, never fatal to the export. */
    private fun section(output: Writer, title: String, body: (Writer) -> Unit) {
        output.write("== $title ==\n")
        try { body(output) } catch (error: Throwable) {
            output.write("Section failed: ${error.javaClass.name}: ${error.message}\n")
        }
        output.write("\n")
    }

    private fun line(output: Writer, key: String, value: () -> Any?) {
        val text = try { value().toString() } catch (error: Throwable) {
            "unavailable (${error.javaClass.simpleName}: ${error.message})"
        }
        output.write("$key: $text\n")
    }

    private fun environment(output: Writer) {
        val packages = context.packageManager
        val self = packages.getPackageInfo(context.packageName, 0)
        line(output, "exported") { stamp(System.currentTimeMillis()) }
        line(output, "app") { "${context.packageName} ${self.versionName} (${self.longVersionCode}) ${BuildConfig.BUILD_TYPE}" }
        line(output, "app installer") { packages.getInstallSourceInfo(context.packageName).installingPackageName }
        line(output, "app updated") { stamp(self.lastUpdateTime) }
        line(output, "patch language") { PatchLanguage.current(context) }
        line(output, "device") { "${Build.MANUFACTURER} / ${Build.BRAND} / ${Build.MODEL} / ${Build.DEVICE} / ${Build.PRODUCT}" }
        line(output, "android") {
            "${Build.VERSION.RELEASE} API ${Build.VERSION.SDK_INT}, patch ${Build.VERSION.SECURITY_PATCH}, " +
                "incremental ${Build.VERSION.INCREMENTAL}"
        }
        line(output, "abis") { Build.SUPPORTED_ABIS.joinToString() }
        line(output, "fingerprint") { Build.FINGERPRINT }
        line(output, "properties") { properties().joinToString("") { (key, value) -> "\n  $key = $value" } }
        val activity = context.getSystemService(ActivityManager::class.java)
        line(output, "memory") {
            ActivityManager.MemoryInfo().also { activity.getMemoryInfo(it) }.let {
                "total ${it.totalMem}, available ${it.availMem}, low ${it.lowMemory}, threshold ${it.threshold}"
            }
        }
        line(output, "app background restricted") { activity.isBackgroundRestricted }
        line(output, "app standby bucket") { context.getSystemService(UsageStatsManager::class.java).appStandbyBucket }
        val power = context.getSystemService(PowerManager::class.java)
        line(output, "power saver") { power.isPowerSaveMode }
        line(output, "app ignores battery optimization") { power.isIgnoringBatteryOptimizations(context.packageName) }
        line(output, "notifications enabled") { context.getSystemService(NotificationManager::class.java).areNotificationsEnabled() }
        line(output, "can request installs") { packages.canRequestPackageInstalls() }
        line(output, "shizuku app") { packageSummary(SHIZUKU_APP) }
        line(output, "shizuku app ignores battery optimization") { power.isIgnoringBatteryOptimizations(SHIZUKU_APP) }
        line(output, "shizuku ping") { Shizuku.pingBinder() }
        line(output, "shizuku server") {
            "version ${Shizuku.getVersion()} patch ${Shizuku.getServerPatchVersion()} " +
                "(client expects ${Shizuku.getLatestServiceVersion()})"
        }
        line(output, "shizuku uid") { Shizuku.getUid() }
        line(output, "shizuku selinux") { Shizuku.getSELinuxContext() }
        line(output, "shizuku permission") {
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) "granted" else "not granted"
        }
        line(output, "game") { packageSummary(PrivilegedDeviceService.GAME) }
        line(output, "worker running") { PatchWorkerService.isWorking }
    }

    private fun stamp(millis: Long) = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS Z", Locale.US).format(Date(millis))

    private fun packageSummary(name: String): String {
        val packages = context.packageManager
        val info = try { packages.getPackageInfo(name, 0) } catch (_: PackageManager.NameNotFoundException) {
            return "not installed"
        }
        val application = checkNotNull(info.applicationInfo)
        val debuggable = application.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        val installer = runCatching { packages.getInstallSourceInfo(name).installingPackageName }.getOrNull()
        return "${info.versionName} (${info.longVersionCode}), debuggable $debuggable, enabled ${application.enabled}, " +
            "splits ${application.splitSourceDirs?.size ?: 0}, installer $installer, " +
            "installed ${stamp(info.firstInstallTime)}, updated ${stamp(info.lastUpdateTime)}"
    }

    /** Only the named build and ROM properties: never serial numbers or account data. */
    private fun properties(): List<Pair<String, String>> {
        val values = mutableMapOf<String, String>()
        val pattern = Regex("^\\[([^\\]]+)\\]: \\[(.*)\\]$")
        run(listOf("/system/bin/getprop"), 5).lineSequence().forEach { text ->
            pattern.matchEntire(text)?.let { values[it.groupValues[1]] = it.groupValues[2] }
        }
        return PROPERTIES.mapNotNull { key -> values[key]?.takeIf { it.isNotEmpty() }?.let { key to it } }
    }

    private fun exits(output: Writer) {
        val reasons = context.getSystemService(ActivityManager::class.java)
            .getHistoricalProcessExitReasons(null, 0, EXIT_LIMIT)
        if (reasons.isEmpty()) output.write("none recorded\n")
        for (exit in reasons) {
            output.write("${stamp(exit.timestamp)} pid ${exit.pid} ${exit.processName}: " +
                "${EXIT_REASONS[exit.reason] ?: exit.reason} status ${exit.status} importance ${exit.importance} " +
                "pss ${exit.pss} kB rss ${exit.rss} kB ${exit.description.orEmpty()}\n")
        }
    }

    private fun storage(output: Writer) {
        val root = context.filesDir
        line(output, "free") { "${root.usableSpace} of ${root.totalSpace} bytes" }
        for (entry in root.listFiles().orEmpty().sortedBy { it.name }.take(ENTRY_LIMIT)) {
            var files = 0
            var bytes = 0L
            entry.walkTopDown().onEnter { !Files.isSymbolicLink(it.toPath()) }.takeWhile { files < WALK_LIMIT }.forEach {
                if (it.isFile && !Files.isSymbolicLink(it.toPath())) { files++; bytes += it.length() }
            }
            output.write("${entry.name}${if (entry.isDirectory) "/" else ""}: $bytes bytes in $files files" +
                (if (files >= WALK_LIMIT) " (stopped counting)" else "") + "\n")
        }
    }

    private fun logcat(output: Writer) {
        output.write(run(listOf("/system/bin/logcat", "-d", "-v", "threadtime", "-t", LOGCAT_LINES.toString()), 10))
    }

    /** Run a read-only system tool into a private file, so a stalled tool cannot block the export. */
    private fun run(command: List<String>, seconds: Long): String {
        val target = File.createTempFile("diagnostic", ".txt", context.cacheDir)
        try {
            val process = ProcessBuilder(command).redirectErrorStream(true).redirectOutput(target).start()
            if (!process.waitFor(seconds, TimeUnit.SECONDS)) process.destroyForcibly()
            val length = target.length()
            val count = minOf(length, COMMAND_BYTES.toLong()).toInt()
            return RandomAccessFile(target, "r").use { input ->
                input.seek(length - count)
                String(ByteArray(count).also { input.readFully(it) }, Charsets.UTF_8)
            }
        } finally { target.delete() }
    }

    companion object {
        private const val SHIZUKU_APP = "moe.shizuku.privileged.api"
        private const val TRACE_BYTES = 1024 * 1024
        private const val COMMAND_BYTES = 768 * 1024
        private const val LOGCAT_LINES = 5000
        private const val EXIT_LIMIT = 20
        private const val RECENT_RUNS = 3
        private const val WALK_LIMIT = 200_000
        private val PROPERTIES = listOf("ro.build.display.id", "ro.product.cpu.abi", "ro.config.low_ram",
            "ro.debuggable", "ro.miui.ui.version.name", "ro.miui.ui.version.code", "ro.mi.os.version.name",
            "ro.mi.os.version.code", "persist.sys.miui_optimization", "ro.build.version.emui",
            "ro.build.version.opporom", "ro.build.version.oplusrom", "ro.vivo.os.version", "ro.build.version.oneui",
            "ro.build.version.magic", "ro.com.google.gmsversion", "persist.sys.locale", "persist.sys.timezone")
        private val EXIT_REASONS = mapOf(0 to "UNKNOWN", 1 to "EXIT_SELF", 2 to "SIGNALED", 3 to "LOW_MEMORY",
            4 to "CRASH", 5 to "CRASH_NATIVE", 6 to "ANR", 7 to "INITIALIZATION_FAILURE", 8 to "PERMISSION_CHANGE",
            9 to "EXCESSIVE_RESOURCE_USAGE", 10 to "USER_REQUESTED", 11 to "USER_STOPPED", 12 to "DEPENDENCY_DIED",
            13 to "OTHER", 14 to "FREEZER", 15 to "PACKAGE_STATE_CHANGE", 16 to "PACKAGE_UPDATED")
        private const val RECORD_BYTES = 1024 * 1024
        private const val LOG_BYTES = 256 * 1024
        private const val TOTAL_BYTES = 8 * 1024 * 1024
        private const val ENTRY_LIMIT = 256
    }
}
