package dev.halixm.hokacepatcher

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.PowerManager
import android.os.SystemClock
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Observe resource use without making a sampled measurement a safety limit. */
class RunMetrics(private val context: Context, private val destination: File) {
    private val started = SystemClock.elapsedRealtime()
    private val initialFree = context.filesDir.usableSpace
    private var minimumFree = initialFree
    private var maximumRssKiB = 0L
    private var maximumProcessHighWaterKiB = 0L
    private var maximumThermalStatus = -1
    private var maximumBatteryTemperatureTenthsC = Int.MIN_VALUE
    private var samples = 0
    private var unavailable = 0
    private val sampler = Executors.newSingleThreadScheduledExecutor()

    init {
        sample()
        sampler.scheduleWithFixedDelay({ sample() }, 1, 1, TimeUnit.SECONDS)
    }

    @Synchronized private fun sample() {
        minimumFree = minOf(minimumFree, context.filesDir.usableSpace)
        samples++
        runCatching {
            val memory = File("/proc/self/status").readLines().associate { line ->
                line.substringBefore(':') to line.substringAfter(':').trim()
            }
            fun number(name: String): Long = checkNotNull(memory[name]).substringBefore(' ').toLong()
            maximumRssKiB = maxOf(maximumRssKiB, number("VmRSS"))
            maximumProcessHighWaterKiB = maxOf(maximumProcessHighWaterKiB, number("VmHWM"))
        }.onFailure { unavailable++ }
        runCatching {
            val power = context.getSystemService(PowerManager::class.java)
            maximumThermalStatus = maxOf(maximumThermalStatus, power.currentThermalStatus)
            val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val temperature = battery?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
                ?: Int.MIN_VALUE
            maximumBatteryTemperatureTenthsC = maxOf(maximumBatteryTemperatureTenthsC, temperature)
        }.onFailure { unavailable++ }
    }

    /** Process high-water RSS is lifetime-wide; free-space changes may include other applications. */
    fun finish(status: String): JSONObject {
        sampler.shutdownNow()
        sampler.awaitTermination(5, TimeUnit.SECONDS)
        sample()
        val result = synchronized(this) {
            JSONObject().put("schema", 1).put("status", status)
                .put("elapsed_seconds", (SystemClock.elapsedRealtime() - started) / 1000.0)
                .put("sample_interval_seconds", 1).put("samples", samples)
                .put("initial_free_bytes", initialFree).put("minimum_free_bytes", minimumFree)
                .put("observed_free_space_decrease_bytes", initialFree - minimumFree)
                .put("maximum_sampled_rss_kib", maximumRssKiB)
                .put("process_lifetime_high_water_rss_kib", maximumProcessHighWaterKiB)
                .put("maximum_thermal_status", maximumThermalStatus)
                .put("maximum_battery_temperature_tenths_c", if (maximumBatteryTemperatureTenthsC == Int.MIN_VALUE)
                    JSONObject.NULL else maximumBatteryTemperatureTenthsC)
                .put("unavailable_readings", unavailable)
        }
        DurableFiles.createDirectories(destination.parentFile!!)
        val storage = AtomicFile(destination)
        val stream = storage.startWrite()
        try {
            stream.write(result.toString(2).toByteArray(Charsets.UTF_8))
            stream.fd.sync()
            storage.finishWrite(stream)
            DurableFiles.syncDirectory(destination.parentFile!!)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
        return result
    }
}
