package dev.halixm.hokacepatcher

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.SSLSocket
import org.conscrypt.Conscrypt

/** The six-digit code did not match the one Settings shows; `adbd` answers a wrong code this way. */
class AdbWrongPairingCode : IOException("Wrong wireless debugging pairing code")

/**
 * Pairing with `adbd` once, so it trusts [AdbKey] on every later connection.
 *
 * Ported from Shizuku's `AdbPairingClient.kt` (Copyright RikkaW, Apache-2.0; see
 * `android/native/THIRD_PARTY.md`), which follows AOSP's `adb/pairing_connection`. Over TLS, both sides run
 * SPAKE2 on the pairing code plus 64 bytes exported from the TLS session, derive an AES-128-GCM key from
 * the result, and swap their public keys encrypted under it. A wrong code shows as their peer info failing
 * to decrypt.
 */
class AdbPairingClient(private val host: String, private val port: Int, private val code: String, private val key: AdbKey) {
    companion object {
        private const val HEADER_VERSION: Byte = 1
        private const val SPAKE2_MSG: Byte = 0
        private const val PEER_INFO: Byte = 1
        private const val HEADER_BYTES = 6
        private const val PEER_INFO_BYTES = 8192
        private const val MAX_PAYLOAD = PEER_INFO_BYTES * 2
        private const val EXPORTED_LABEL = "adb-label\u0000"
        private const val EXPORTED_BYTES = 64
        private const val CONNECT_MS = 5000
        private const val READ_MS = 15000

        /** Our peer info: type ADB_RSA_PUB_KEY (0), then the public key, zero-filled to [PEER_INFO_BYTES]. */
        fun peerInfo(adbPublicKey: ByteArray): ByteArray {
            require(adbPublicKey.size < PEER_INFO_BYTES) { "ADB public key too long for pairing" }
            return ByteArray(PEER_INFO_BYTES).also { adbPublicKey.copyInto(it, 1) }
        }
    }

    /** Pair, or throw: [AdbWrongPairingCode] for a wrong code, an [IOException] for anything else. */
    fun pair() {
        Socket().use { plain ->
            plain.connect(InetSocketAddress(host, port), CONNECT_MS)
            plain.soTimeout = READ_MS
            plain.tcpNoDelay = true
            val tls = key.sslContext(Conscrypt.newProvider()).socketFactory.createSocket(plain, host, port, true) as SSLSocket
            tls.use {
                tls.startHandshake()
                val exported = Conscrypt.exportKeyingMaterial(tls, EXPORTED_LABEL, null, EXPORTED_BYTES)
                val input = DataInputStream(tls.inputStream)
                val output = DataOutputStream(tls.outputStream)
                AdbSpake2(code.toByteArray() + exported).use { spake2 ->
                    write(output, SPAKE2_MSG, spake2.message)
                    val material = spake2.process(read(input, SPAKE2_MSG)) ?: throw AdbWrongPairingCode()
                    val cipher = PairingCipher(material)
                    write(output, PEER_INFO, cipher.encrypt(peerInfo(key.adbPublicKey)))
                    val theirs = cipher.decrypt(read(input, PEER_INFO)) ?: throw AdbWrongPairingCode()
                    if (theirs.size != PEER_INFO_BYTES) throw IOException("Pairing peer info has ${theirs.size} bytes")
                }
            }
        }
    }

    private fun write(output: DataOutputStream, type: Byte, payload: ByteArray) {
        output.write(ByteBuffer.allocate(HEADER_BYTES).order(ByteOrder.BIG_ENDIAN).put(HEADER_VERSION).put(type)
            .putInt(payload.size).array())
        output.write(payload)
        output.flush()
    }

    private fun read(input: DataInputStream, expected: Byte): ByteArray {
        val header = ByteArray(HEADER_BYTES)
        input.readFully(header)
        val buffer = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN)
        val version = buffer.get()
        val type = buffer.get()
        val size = buffer.int
        if (version != HEADER_VERSION) throw IOException("Pairing header version $version")
        if (type != expected) throw IOException("Pairing packet type $type, expected $expected")
        if (size <= 0 || size > MAX_PAYLOAD) throw IOException("Pairing payload size $size")
        return ByteArray(size).also { input.readFully(it) }
    }
}

/**
 * AES-128-GCM keyed by HKDF-SHA256 over the SPAKE2 key material, as AOSP's `adb/pairing_auth/aes_128_gcm.cpp`:
 * no salt, info "adb pairing_auth aes-128-gcm key", and a 12-byte nonce holding each direction's message
 * count as a little-endian integer.
 */
class PairingCipher(material: ByteArray) {
    companion object {
        private const val KEY_BYTES = 16
        private const val NONCE_BYTES = 12
        private const val TAG_BITS = 128
        private val INFO = "adb pairing_auth aes-128-gcm key".toByteArray()

        /** RFC 5869 HKDF with SHA-256. */
        fun hkdf(material: ByteArray, salt: ByteArray?, info: ByteArray, length: Int): ByteArray {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(salt?.takeIf { it.isNotEmpty() } ?: ByteArray(32), "HmacSHA256"))
            val prk = mac.doFinal(material)
            mac.init(SecretKeySpec(prk, "HmacSHA256"))
            val out = ByteArray(length)
            var block = ByteArray(0)
            var written = 0
            var counter = 1
            while (written < length) {
                mac.update(block)
                mac.update(info)
                mac.update(counter.toByte())
                block = mac.doFinal()
                val count = minOf(block.size, length - written)
                block.copyInto(out, written, 0, count)
                written += count
                counter++
            }
            return out
        }

        fun nonce(sequence: Long): ByteArray =
            ByteBuffer.allocate(NONCE_BYTES).order(ByteOrder.LITTLE_ENDIAN).putLong(sequence).array()
    }

    private val key = SecretKeySpec(hkdf(material, null, INFO, KEY_BYTES), "AES")
    private var encrypted = 0L
    private var decrypted = 0L

    fun encrypt(plain: ByteArray): ByteArray = Cipher.getInstance("AES/GCM/NoPadding").run {
        init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(TAG_BITS, nonce(encrypted++)))
        doFinal(plain)
    }

    /** The plain bytes, or null when <sealed> does not authenticate: the two sides hold different codes. */
    fun decrypt(sealed: ByteArray): ByteArray? = runCatching {
        Cipher.getInstance("AES/GCM/NoPadding").run {
            init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, nonce(decrypted)))
            doFinal(sealed)
        }
    }.getOrNull()?.also { decrypted++ }
}

/** BoringSSL's SPAKE2 as the pairing client (alice), in `libhokace_adb.so`. */
class AdbSpake2(password: ByteArray) : AutoCloseable {
    private companion object {
        init { System.loadLibrary("hokace_adb") }
        @JvmStatic external fun nativeCreate(password: ByteArray): Long
        @JvmStatic external fun nativeMessage(pointer: Long): ByteArray
        @JvmStatic external fun nativeProcess(pointer: Long, theirs: ByteArray): ByteArray?
        @JvmStatic external fun nativeFree(pointer: Long)
    }
    private var pointer = nativeCreate(password).also { check(it != 0L) { "SPAKE2 could not start" } }

    /** Our SPAKE2 message for the server. */
    val message: ByteArray = nativeMessage(pointer)

    /** The shared key material for the server's message, or null when it does not process. */
    fun process(theirs: ByteArray): ByteArray? = nativeProcess(pointer, theirs)

    override fun close() {
        if (pointer != 0L) nativeFree(pointer)
        pointer = 0L
    }
}
