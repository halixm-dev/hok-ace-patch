package dev.halixm.hokacepatcher

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import java.io.DataInputStream
import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Finds this phone's own wireless debugging ports by mDNS, as Shizuku's `AdbMdns.kt` (Copyright RikkaW,
 * Apache-2.0; see `android/native/THIRD_PARTY.md`). Both ports change whenever wireless debugging is
 * switched on, so each pairing and each run looks again. Other phones on the Wi-Fi advertise the same
 * services: only one that resolves to an address of this phone, on a port something here listens on, counts.
 */
object AdbMdns {
    const val PAIRING = "_adb-tls-pairing._tcp"
    const val CONNECT = "_adb-tls-connect._tcp"
    private const val PROBE_MS = 1000

    /** The port of <type> on this phone, or null when none is advertised within <timeoutMs>. */
    fun find(context: Context, type: String, timeoutMs: Long): Int? {
        val nsd = context.getSystemService(NsdManager::class.java)
        val found = AtomicInteger(-1)
        val done = CountDownLatch(1)
        // NsdManager resolves one service at a time; the rest wait their turn.
        val resolving = java.util.concurrent.Semaphore(1)
        val listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                DiagnosticTrace.event("adb", "mDNS discovery of $type failed to start: $errorCode")
                done.countDown()
            }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onServiceLost(service: NsdServiceInfo) {}
            override fun onServiceFound(service: NsdServiceInfo) {
                Thread({
                    if (!resolving.tryAcquire(timeoutMs, TimeUnit.MILLISECONDS)) return@Thread
                    @Suppress("DEPRECATION")
                    nsd.resolveService(service, object : NsdManager.ResolveListener {
                        override fun onResolveFailed(service: NsdServiceInfo, errorCode: Int) { resolving.release() }
                        override fun onServiceResolved(resolved: NsdServiceInfo) {
                            resolving.release()
                            @Suppress("DEPRECATION")
                            val address = resolved.host?.hostAddress
                            if (address != null && local(address)) {
                                if (listening(resolved.port)) {
                                    found.compareAndSet(-1, resolved.port)
                                    done.countDown()
                                } else DiagnosticTrace.event("adb", "mDNS names port ${resolved.port} for $type on " +
                                    "this phone, but nothing listens there; ignored")
                            } else DiagnosticTrace.event("adb", "mDNS names ${resolved.serviceName} at $address, " +
                                "another device; ignored")
                        }
                    })
                }, "hokace-mdns").apply { isDaemon = true }.start()
            }
        }
        nsd.discoverServices(type, NsdManager.PROTOCOL_DNS_SD, listener)
        try { done.await(timeoutMs, TimeUnit.MILLISECONDS) } finally {
            runCatching { nsd.stopServiceDiscovery(listener) }
        }
        return found.get().takeIf { it > 0 }
    }

    private fun local(address: String) = runCatching {
        NetworkInterface.getNetworkInterfaces().asSequence().any { network ->
            network.inetAddresses.asSequence().any { it.hostAddress == address }
        }
    }.getOrDefault(false)

    /**
     * This phone's wireless debugging port found without mDNS: of <ports>, the first something listens on
     * that answers CNXN with STLS. `adbd` binds its TLS server to a port the kernel picks from the ephemeral
     * range, the default for <ports>. For a phone whose discovery misses its own record: Xiaomi M2007J3SG,
     * Android 12, 2026-10-29, where three runs in four found only another phone's service on the same Wi-Fi
     * and never this one's (`adbd` on 41031).
     */
    fun scan(ports: Iterable<Int> = ephemeralPorts()): Int? = ports.asSequence().filter(::listening).firstOrNull(::answersStls)

    /** The kernel's ephemeral port range, or Linux's default when it cannot be read. */
    private fun ephemeralPorts(): IntRange = runCatching {
        val (first, last) = File("/proc/sys/net/ipv4/ip_local_port_range").readText().trim().split(Regex("\\s+")).map(String::toInt)
        first..last
    }.getOrDefault(32768..60999)

    /** True when 127.0.0.1:<port> answers CNXN with STLS, as only wireless debugging's `adbd` does. */
    fun answersStls(port: Int): Boolean = try {
        Socket().use { socket ->
            socket.connect(InetSocketAddress("127.0.0.1", port), PROBE_MS)
            socket.soTimeout = PROBE_MS
            socket.getOutputStream().apply {
                write(AdbMessage(AdbProtocol.A_CNXN, AdbProtocol.A_VERSION, AdbProtocol.A_MAXDATA, "host::").toByteArray())
                flush()
            }
            AdbMessage.read(DataInputStream(socket.getInputStream())).command == AdbProtocol.A_STLS
        }
    } catch (_: IOException) {
        false
    }

    /** True when something on this phone already holds <port>: binding it here fails. */
    private fun listening(port: Int) = try {
        ServerSocket().use { it.bind(InetSocketAddress("127.0.0.1", port), 1) }
        false
    } catch (_: IOException) {
        true
    }
}
