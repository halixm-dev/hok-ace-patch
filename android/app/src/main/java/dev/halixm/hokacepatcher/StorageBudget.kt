package dev.halixm.hokacepatcher

import org.json.JSONObject
import java.io.File
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.zip.ZipEntry
import java.util.zip.ZipFile

/** Budget simultaneously live transient files, retaining room for normal-APK recovery. */
object StorageBudget {
    private const val MINIMUM_MARGIN = 256L * 1024 * 1024
    private const val GB = 1_000_000_000L
    private const val MB = 1_000_000L
    /** The smallest free-space change [replacedGameApksReport] counts as a released game APK. */
    const val REPLACED_APK_MIN_BYTES = 100L * MB
    /** Android's default cap on the low-storage reserve an install must leave free (500 MiB). */
    const val ANDROID_LOW_STORAGE_BYTES = 500L * 1024 * 1024

    /**
     * What installing <apk> (<bytes> long) holds at once: `pm` stages the whole APK, then refuses unless the
     * installed size, the APK plus every compressed native library it extracts, still fits above Android's
     * low-storage reserve. The game APK (2.03 GB, 0.40 GB of compressed libraries) failed with 4.1 GB free
     * while one APK was budgeted (measured 2026-11-19).
     */
    fun installAllocations(apk: File, bytes: Long): LongArray {
        val libraries = ZipFile(apk).use { zip ->
            zip.entries().asSequence()
                .filter { !it.isDirectory && it.name.startsWith("lib/") && it.method != ZipEntry.STORED }
                .sumOf { maxOf(it.size, 0L) }
        }
        return longArrayOf(bytes, Math.addExact(bytes, libraries), ANDROID_LOW_STORAGE_BYTES)
    }

    fun required(vararg allocations: Long): Long {
        require(allocations.isNotEmpty() && allocations.all { it >= 0 }) { "Invalid storage allocation" }
        val bytes = allocations.fold(0L) { total, next -> Math.addExact(total, next) }
        return Math.addExact(bytes, maxOf(MINIMUM_MARGIN, bytes / 20))
    }

    /** Decimal GB matches phone storage settings; round conservatively for clearing advice. */
    private fun gb(bytes: Long, rounding: RoundingMode): BigDecimal =
        BigDecimal.valueOf(bytes).divide(BigDecimal.valueOf(1_000_000_000L), 1, rounding)

    /**
     * A size for people, rounded down: decimal GB from 1 GB, whole decimal MB below it, so a 38 MB file never
     * reads "0.0 GB"; a size under 1 MB that is not empty reads "<1 MB".
     */
    fun freeSpaceLabel(bytes: Long): String {
        require(bytes >= 0)
        return when {
            bytes >= GB -> gb(bytes, RoundingMode.FLOOR).toPlainString() + " GB"
            bytes in 1 until MB -> "<1 MB"
            else -> "${bytes / MB} MB"
        }
    }

    @JvmOverloads fun explainFailure(message: String, currentAvailable: Long? = null): String? {
        val match = Regex("(\\d+) bytes required, (\\d+) available").findAll(message).lastOrNull() ?: return null
        val needed = match.groupValues[1].toLongOrNull() ?: return null
        val available = currentAvailable ?: match.groupValues[2].toLongOrNull() ?: return null
        if (needed <= 0 || available < 0) return null
        val needGb = gb(needed, RoundingMode.CEILING)
        if (available >= needed) return "Enough space now for this step.\nNeeded: $needGb GB free (rounded up).\n" +
            "Tap Try again. Keep saved recovery files."
        val freeGb = gb(available, RoundingMode.FLOOR)
        val moreGb = needGb.subtract(freeGb)
        return "Need $needGb GB free for this step.\nFree now: $freeGb GB.\n" +
            "Clear at least $moreGb GB more, then try again.\nKeep saved recovery files."
    }

    /**
     * Before a budget: the home app holds every game APK an install replaced until it restarts (several GB
     * after a few runs). Never fails the caller; the worker also releases them after each install.
     */
    fun releaseReplacedGameApks(device: IPrivilegedDeviceService, report: (String) -> Unit) {
        runCatching { JSONObject(device.releaseReplacedGameApks()).optLong("freed_bytes") }
            .onSuccess { freed -> replacedGameApksReport(freed)?.let(report) }
            .onFailure { android.util.Log.w("HokAceStorage", "Replaced game APKs were not released", it) }
    }

    /**
     * The progress line for a home app restart that freed <freed> bytes, or null when it released no replaced
     * game APK. The device measures free space before and after the restart, so other apps' storage moves the
     * figure too; a replaced game APK is about 2 GB, and a change under [REPLACED_APK_MIN_BYTES] is reported
     * as nothing freed rather than as "Freed 0.0 GB".
     */
    fun replacedGameApksReport(freed: Long): String? =
        if (freed < REPLACED_APK_MIN_BYTES) null
        else "Freed ${freeSpaceLabel(freed)} of replaced game files the home screen app held"

    class Shortage(val phase: String, val requiredBytes: Long, val availableBytes: Long) : IllegalStateException(
        "Insufficient storage for $phase: $requiredBytes bytes required, $availableBytes available; keep recovery material") {
        fun json() = JSONObject().put("phase", phase).put("required_bytes", requiredBytes)
            .put("available_bytes", availableBytes)

        /** A space shortage never proves file/APK consistency. */
        fun result(recoveryRequired: Boolean) = JSONObject()
            .put("status", if (recoveryRequired) "recovery_required" else "waiting")
            .put("reason", "storage").put("storage_wait", json()).put("error", message)
            .put("launch_allowed", false)
    }

    /** Recovery may attach its own newer shortage to the original stage error. Bound malformed chains. */
    fun shortage(error: Throwable, depth: Int = 0): Shortage? {
        if (depth >= 8) return null
        for (suppressed in error.suppressed.reversed()) shortage(suppressed, depth + 1)?.let { return it }
        error.cause?.takeIf { it !== error }?.let { shortage(it, depth + 1)?.let { found -> return found } }
        return error as? Shortage
    }

    /** A caller-owned optional cache may be reclaimed once on shortage; the same budget is remeasured. */
    @JvmOverloads fun requireAvailable(directory: File, phase: String, vararg allocations: Long,
                                      reclaim: (() -> Unit)? = null): JSONObject {
        val bytes = required(*allocations)
        var available = directory.usableSpace
        if (available < bytes && reclaim != null) {
            reclaim()
            available = directory.usableSpace
        }
        if (available < bytes) throw Shortage(phase, bytes, available)
        return JSONObject().put("phase", phase).put("required_bytes", bytes).put("available_bytes", available)
    }
}
