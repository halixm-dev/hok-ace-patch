package dev.halixm.hokacepatcher

import java.io.Closeable
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.PipedInputStream
import java.io.PipedOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import javax.net.ssl.SSLSocket
import org.conscrypt.Conscrypt

/** `adbd` did not accept [AdbKey]: the patcher is not paired, or the pairing was forgotten. */
class AdbNotPaired(message: String) : IOException(message)

/**
 * One ADB connection to this phone's own `adbd`, carrying one shell stream.
 *
 * Ported from Shizuku's `AdbClient.kt` (Copyright RikkaW, Apache-2.0; see `android/native/THIRD_PARTY.md`).
 * Wireless debugging always answers CNXN with STLS, so the connection upgrades to TLS presenting
 * [AdbKey]; `adbd` accepts it only for a paired key. The older AUTH exchange is kept for a server that
 * skips STLS. Unlike Shizuku's, the shell stream stays open after [shell] returns: its output arrives on
 * the returned stream until the command exits or the connection is lost, and [close] ends both.
 */
class AdbClient(private val host: String, private val port: Int, private val key: AdbKey) : Closeable {
    private companion object {
        const val CONNECT_MS = 5000
        const val HANDSHAKE_MS = 15000
        const val LOCAL_ID = 1
    }
    private val socket = Socket()
    private var tls: SSLSocket? = null
    private lateinit var input: DataInputStream
    private lateinit var output: DataOutputStream
    private val writeLock = Any()
    @Volatile private var closed = false

    fun connect() {
        socket.connect(InetSocketAddress(host, port), CONNECT_MS)
        socket.tcpNoDelay = true
        socket.soTimeout = HANDSHAKE_MS
        input = DataInputStream(socket.getInputStream())
        output = DataOutputStream(socket.getOutputStream())
        write(AdbMessage(AdbProtocol.A_CNXN, AdbProtocol.A_VERSION, AdbProtocol.A_MAXDATA, "host::"))
        var message = AdbMessage.read(input)
        if (message.command == AdbProtocol.A_STLS) {
            write(AdbMessage(AdbProtocol.A_STLS, AdbProtocol.A_STLS_VERSION, 0))
            val secured = key.sslContext(Conscrypt.newProvider()).socketFactory.createSocket(socket, host, port, true) as SSLSocket
            tls = secured
            try { secured.startHandshake() } catch (error: IOException) {
                throw AdbNotPaired("Wireless debugging refused the patcher's key (${error.message})")
            }
            input = DataInputStream(secured.inputStream)
            output = DataOutputStream(secured.outputStream)
            message = try { AdbMessage.read(input) } catch (error: IOException) {
                // TLS 1.3 reports a refused client certificate on the first read, not in the handshake.
                throw AdbNotPaired("Wireless debugging refused the patcher's key (${error.message})")
            }
        } else if (message.command == AdbProtocol.A_AUTH && message.arg0 == AdbProtocol.ADB_AUTH_TOKEN) {
            write(AdbMessage(AdbProtocol.A_AUTH, AdbProtocol.ADB_AUTH_SIGNATURE, 0, key.sign(message.data)))
            message = AdbMessage.read(input)
            if (message.command != AdbProtocol.A_CNXN) throw AdbNotPaired("ADB did not accept the patcher's key")
        }
        if (message.command != AdbProtocol.A_CNXN) throw IOException("ADB answered ${AdbMessage.name(message.command)}, not CNXN")
        socket.soTimeout = 0
    }

    /**
     * Open `shell:<command>` and pump its output into the returned stream on a daemon thread, which ends the
     * stream when the command exits or the connection drops, then calls <ended> with the reason.
     */
    fun shell(command: String, ended: (String) -> Unit): InputStream {
        write(AdbMessage(AdbProtocol.A_OPEN, LOCAL_ID, 0, "shell:$command"))
        val opened = AdbMessage.read(input)
        if (opened.command != AdbProtocol.A_OKAY) throw IOException("ADB refused the shell stream (${AdbMessage.name(opened.command)})")
        val remote = opened.arg0
        val sink = PipedOutputStream()
        val source = PipedInputStream(sink, 64 * 1024)
        Thread({
            val reason = try {
                pump(remote, sink)
            } catch (error: IOException) {
                if (closed) "closed by the patcher" else "connection lost (${error.message ?: error.javaClass.simpleName})"
            }
            // The reason first: the stream's reader also reports the end, with less to say.
            runCatching { ended(reason) }
            runCatching { sink.close() }
        }, "hokace-adb-shell").apply { isDaemon = true }.start()
        return source
    }

    private fun pump(remote: Int, sink: PipedOutputStream): String {
        while (true) {
            val message = AdbMessage.read(input)
            when (message.command) {
                AdbProtocol.A_WRTE -> {
                    // Output nobody reads must not stall the connection.
                    runCatching { sink.write(message.data); sink.flush() }
                    write(AdbMessage(AdbProtocol.A_OKAY, LOCAL_ID, remote))
                }
                AdbProtocol.A_CLSE -> {
                    runCatching { write(AdbMessage(AdbProtocol.A_CLSE, LOCAL_ID, remote)) }
                    return "shell exited"
                }
                AdbProtocol.A_OKAY -> {}
                else -> throw IOException("Unexpected ADB message ${AdbMessage.name(message.command)}")
            }
        }
    }

    private fun write(message: AdbMessage) = synchronized(writeLock) {
        output.write(message.toByteArray())
        output.flush()
    }

    override fun close() {
        closed = true
        runCatching { tls?.close() }
        runCatching { socket.close() }
    }
}
