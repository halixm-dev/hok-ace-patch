package dev.halixm.hokacepatcher

import java.io.IOException
import java.util.concurrent.TimeUnit

/** Measure denial from an ordinary app process; SELinux may deny exec before run-as can start. */
object NormalRunAsProbe {
    fun run(): String {
        val process = try {
            ProcessBuilder("/system/bin/run-as", PrivilegedDeviceService.FIXTURE, "id")
                .redirectErrorStream(true).start()
        } catch (error: IOException) {
            check(error.message?.contains("error=13, Permission denied") == true) {
                "Unexpected normal run-as failure: ${error.message}"
            }
            return "PASS: normal process denied exec of run-as (EACCES)"
        }
        try {
            check(process.waitFor(10, TimeUnit.SECONDS)) { "Normal run-as timed out" }
            val message = process.inputStream.bufferedReader().use { it.readText().take(1024) }
            check(process.exitValue() != 0) { "Unexpected run-as access from normal app" }
            return "PASS: normal process denied run-as: $message"
        } finally { process.destroyForcibly() }
    }
}
