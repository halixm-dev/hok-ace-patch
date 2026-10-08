package dev.halixm.hokacepatcher

import org.json.JSONObject
import java.io.File
import java.math.BigDecimal
import java.math.RoundingMode

/** Budget simultaneously live transient files, retaining room for normal-APK recovery. */
object StorageBudget {
    private const val MINIMUM_MARGIN = 256L * 1024 * 1024

    fun required(vararg allocations: Long): Long {
        require(allocations.isNotEmpty() && allocations.all { it >= 0 }) { "Invalid storage allocation" }
        val bytes = allocations.fold(0L) { total, next -> Math.addExact(total, next) }
        return Math.addExact(bytes, maxOf(MINIMUM_MARGIN, bytes / 20))
    }

    /** Decimal GB matches phone storage settings; round conservatively for clearing advice. */
    private fun gb(bytes: Long, rounding: RoundingMode): BigDecimal =
        BigDecimal.valueOf(bytes).divide(BigDecimal.valueOf(1_000_000_000L), 1, rounding)

    fun freeSpaceLabel(bytes: Long): String {
        require(bytes >= 0)
        return gb(bytes, RoundingMode.FLOOR).toPlainString() + " GB"
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

    fun requireAvailable(directory: File, phase: String, vararg allocations: Long): JSONObject {
        val bytes = required(*allocations)
        val available = directory.usableSpace
        check(available >= bytes) {
            "Insufficient storage for $phase: $bytes bytes required, $available available; keep recovery material"
        }
        return JSONObject().put("phase", phase).put("required_bytes", bytes).put("available_bytes", available)
    }
}
