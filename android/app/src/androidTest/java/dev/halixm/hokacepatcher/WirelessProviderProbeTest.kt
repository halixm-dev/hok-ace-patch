package dev.halixm.hokacepatcher

import androidx.test.platform.app.InstrumentationRegistry
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * The wireless debugging provider against this phone's own `adbd`; Wi-Fi and wireless debugging must be on.
 * Pair first with `-e pairingCode <code>` while Settings shows *Pair device with pairing code*; the other
 * probes skip until the patcher is paired.
 */
class WirelessProviderProbeTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun pairsWithTheCodeSettingsShows() {
        val code = InstrumentationRegistry.getArguments().getString("pairingCode")
        assumeTrue("No pairingCode argument", code != null)
        WirelessDebugging.pair(context, code!!)
        assertTrue("Pairing failed; see the diagnostic trace", WirelessDebugging.paired(context))
    }

    @Test fun theWorkerStartsAsShellOverAdbAndClosesCleanly() {
        assumeTrue("Not paired", WirelessDebugging.paired(context))
        val lost = AtomicInteger()
        WorkerDeviceConnection.open(context, ShellProvider.WIRELESS) { lost.incrementAndGet() }.use { connection ->
            assertEquals(2000, JSONObject(connection.await().diagnostics()).getInt("uid"))
        }
        Thread.sleep(500)
        assertEquals(0, lost.get())
    }

    @Test fun losingTheConnectionIsAWorkerLoss() {
        assumeTrue("Not paired", WirelessDebugging.paired(context))
        val died = CountDownLatch(1)
        WorkerDeviceConnection.open(context, ShellProvider.WIRELESS) { died.countDown() }.use { connection ->
            val service = connection.await()
            assertEquals(2000, JSONObject(service.diagnostics()).getInt("uid"))
            // What switching wireless debugging off does: the ADB connection drops under the run.
            val starter = WorkerDeviceConnection::class.java.getDeclaredField("starter").apply { isAccessible = true }
                .get(connection) as WirelessWorkerStarter
            val client = WirelessWorkerStarter::class.java.getDeclaredField("client").apply { isAccessible = true }
                .get(starter) as AdbClient
            client.close()
            assertTrue("No worker loss after the connection dropped", died.await(15, TimeUnit.SECONDS))
            assertTrue("The worker outlived its ADB connection", runCatching {
                repeat(30) { if (!service.asBinder().isBinderAlive) return@runCatching true; Thread.sleep(200) }
                false
            }.getOrDefault(true))
        }
    }
}
