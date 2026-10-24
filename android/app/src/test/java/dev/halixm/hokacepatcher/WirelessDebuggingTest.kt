package dev.halixm.hokacepatcher

import java.io.ByteArrayInputStream
import java.io.DataInputStream
import java.io.IOException
import java.math.BigInteger
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files
import java.util.Base64
import javax.crypto.Cipher
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** The wireless debugging provider's ported ADB client: wire format, key, pairing cipher and shell line. */
class WirelessDebuggingTest {
    private fun hex(value: String) = value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    private val key by lazy { AdbKey.load(Files.createTempDirectory("adbkey").toFile()) }

    @Test fun anAdbMessageReadsBackAndABadMagicIsRefused() {
        val message = AdbMessage(AdbProtocol.A_OPEN, 1, 0, "shell:id")
        val bytes = message.toByteArray()
        assertEquals(AdbProtocol.HEADER_LENGTH + "shell:id".length + 1, bytes.size)
        val back = AdbMessage.read(DataInputStream(ByteArrayInputStream(bytes)))
        assertEquals(AdbProtocol.A_OPEN, back.command)
        assertArrayEquals("shell:id\u0000".toByteArray(), back.data)
        assertEquals("shell:id\u0000".toByteArray().sumOf { it.toInt() }, AdbMessage.checksum(back.data))
        bytes[20] = 0
        assertThrows(IOException::class.java) { AdbMessage.read(DataInputStream(ByteArrayInputStream(bytes))) }
    }

    @Test fun theAdbPublicKeyIsAospsStructInBase64ThenTheName() {
        val encoded = AdbKey.adbPublicKey(key.publicKey)
        val text = String(encoded)
        assertTrue(text.endsWith(" ${AdbKey.NAME}\u0000"))
        val struct = ByteBuffer.wrap(Base64.getDecoder().decode(text.substringBefore(' '))).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(524, struct.capacity())
        assertEquals(64, struct.int)
        val n0inv = struct.int.toLong() and 0xffffffffL
        val modulus = ByteArray(256).also { struct.get(it) }
        assertEquals(key.publicKey.modulus, BigInteger(1, modulus.reversedArray()))
        // n0inv * n mod 2^32 is -1.
        val r32 = BigInteger.ONE.shiftLeft(32)
        assertEquals(r32 - BigInteger.ONE, BigInteger.valueOf(n0inv).multiply(key.publicKey.modulus).mod(r32))
        struct.position(4 + 4 + 256 + 256)
        assertEquals(65537, struct.int)
    }

    @Test fun theCertificateIsSelfSignedForTheKey() {
        val certificate = AdbKey.certificate(key.publicKey, AdbKey::class.java.getDeclaredField("privateKey")
            .apply { isAccessible = true }.get(key) as java.security.PrivateKey)
        certificate.verify(key.publicKey)
        assertEquals(key.publicKey, certificate.publicKey)
        assertEquals(3, certificate.version)
        assertEquals("SHA256withRSA", certificate.sigAlgName)
    }

    @Test fun anAuthSignatureOpensToTheSha1PaddingAndTheToken() {
        val token = ByteArray(20) { it.toByte() }
        val opened = Cipher.getInstance("RSA/ECB/NoPadding").run {
            init(Cipher.DECRYPT_MODE, key.publicKey); doFinal(key.sign(token))
        }
        assertEquals(256, opened.size)
        assertArrayEquals(byteArrayOf(0, 1, -1), opened.copyOfRange(0, 3))
        assertArrayEquals(token, opened.copyOfRange(236, 256))
        assertArrayEquals(hex("3021300906052b0e03021a05000414"), opened.copyOfRange(221, 236))
    }

    @Test fun theKeyIsKeptAndReadBack() {
        val directory = Files.createTempDirectory("adbkey").toFile()
        assertTrue(!AdbKey.exists(directory))
        val first = AdbKey.load(directory)
        assertTrue(AdbKey.exists(directory))
        assertEquals(first.publicKey, AdbKey.load(directory).publicKey)
    }

    @Test fun hkdfMatchesRfc5869() {
        assertArrayEquals(hex("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"),
            PairingCipher.hkdf(ByteArray(22) { 0x0b }, hex("000102030405060708090a0b0c"), hex("f0f1f2f3f4f5f6f7f8f9"), 42))
        assertArrayEquals(hex("8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"),
            PairingCipher.hkdf(ByteArray(22) { 0x0b }, null, ByteArray(0), 42))
    }

    @Test fun eachDirectionCountsItsOwnNoncesAndAWrongCodeDoesNotDecrypt() {
        assertArrayEquals(hex("010000000000000000000000"), PairingCipher.nonce(1))
        val ours = PairingCipher(ByteArray(64) { 7 })
        val theirs = PairingCipher(ByteArray(64) { 7 })
        val first = ours.encrypt("one".toByteArray())
        val second = ours.encrypt("two".toByteArray())
        assertNotEquals(first.toList(), second.toList())
        assertArrayEquals("one".toByteArray(), theirs.decrypt(first))
        assertArrayEquals("two".toByteArray(), theirs.decrypt(second))
        assertNull(PairingCipher(ByteArray(64) { 8 }).decrypt(ours.encrypt("three".toByteArray())))
    }

    @Test fun peerInfoIsTypeZeroThenTheKeyZeroFilled() {
        val info = AdbPairingClient.peerInfo(key.adbPublicKey)
        assertEquals(8192, info.size)
        assertEquals(0.toByte(), info[0])
        assertArrayEquals(key.adbPublicKey, info.copyOfRange(1, 1 + key.adbPublicKey.size))
        assertEquals(0.toByte(), info[8191])
    }

    @Test fun theShellLineQuotesEveryArgument() {
        assertEquals("'/system/bin/sh' '-c' 'exec \"\$1\"' 'it'\\''s'",
            WirelessDebugging.shellLine(arrayOf("/system/bin/sh", "-c", "exec \"\$1\"", "it's")))
    }

    @Test fun everyWirelessRefusalHasIndonesian() {
        (WirelessDebugging.REFUSALS + listOf(
            "Wireless debugging disconnected. Keep the game closed. Turn Wi-Fi and Wireless debugging back on, then tap Try again.",
            "Pairing did not finish. Keep Pair device with pairing code open, then type the code again.",
        )).forEach { assertNotEquals(it, it, UiText.translate("id", it)) }
    }
}
