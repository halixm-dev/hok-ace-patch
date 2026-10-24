package dev.halixm.hokacepatcher

import java.io.ByteArrayOutputStream
import java.io.File
import java.math.BigInteger
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.Principal
import java.security.PrivateKey
import java.security.Provider
import java.security.SecureRandom
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.interfaces.RSAPrivateCrtKey
import java.security.interfaces.RSAPublicKey
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.RSAKeyGenParameterSpec
import java.security.spec.RSAPublicKeySpec
import java.util.Base64
import javax.crypto.Cipher
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLEngine
import javax.net.ssl.X509ExtendedKeyManager
import javax.net.ssl.X509ExtendedTrustManager

/**
 * The patcher's ADB key pair: what `adbd` remembers once wireless debugging is paired.
 *
 * Ported from Shizuku's `AdbKey.kt` (Copyright RikkaW, Apache-2.0; see `android/native/THIRD_PARTY.md`).
 * Two changes: the RSA-2048 key is a PKCS#8 file in the app's no-backup storage instead of a preference
 * wrapped by the Android keystore, and the self-signed certificate TLS presents is written here as DER
 * instead of through BouncyCastle. `adbd` checks only the certificate's public key.
 */
class AdbKey(private val privateKey: RSAPrivateCrtKey) {
    companion object {
        /** The name `adbd` lists the key under in Settings' wireless debugging page. */
        const val NAME = "hokace-patcher"
        private const val FILE = "adbkey.pk8"
        private const val MODULUS_BYTES = 2048 / 8
        private const val PUBLIC_KEY_BYTES = 524

        /** RSASSA-PKCS1-v1_5 padding for a SHA-1 digest, which `adbd`'s AUTH token is signed as. */
        private val SHA1_PADDING = ByteArray(MODULUS_BYTES - 20).also { padding ->
            val digestInfo = byteArrayOf(0x00, 0x30, 0x21, 0x30, 0x09, 0x06, 0x05, 0x2b, 0x0e, 0x03, 0x02, 0x1a, 0x05, 0x00,
                0x04, 0x14)
            padding.fill(0xff.toByte())
            padding[0] = 0x00
            padding[1] = 0x01
            digestInfo.copyInto(padding, padding.size - digestInfo.size)
        }

        /** The key in <directory>, made on first use. */
        fun load(directory: File): AdbKey {
            val file = File(directory, FILE)
            if (file.isFile) runCatching {
                return AdbKey(KeyFactory.getInstance("RSA").generatePrivate(PKCS8EncodedKeySpec(file.readBytes())) as RSAPrivateCrtKey)
            }.onFailure { DiagnosticTrace.error("adb", "The saved ADB key cannot be read; making a new one", it) }
            val generator = KeyPairGenerator.getInstance("RSA")
            generator.initialize(RSAKeyGenParameterSpec(2048, RSAKeyGenParameterSpec.F4))
            val key = generator.generateKeyPair().private as RSAPrivateCrtKey
            check(directory.isDirectory || directory.mkdirs()) { "Cannot create the ADB key directory" }
            val partial = File(directory, "$FILE.new")
            partial.writeBytes(key.encoded)
            check(partial.renameTo(file)) { "Cannot save the ADB key" }
            return AdbKey(key)
        }

        /** Whether <directory> holds a key; without one, no pairing has happened. */
        fun exists(directory: File) = File(directory, FILE).isFile

        /** AOSP's `android_pubkey_encode`: the struct `adbd` keeps in `adb_keys`, Base64, then the key's name. */
        fun adbPublicKey(publicKey: RSAPublicKey, name: String = NAME): ByteArray {
            val modulus = publicKey.modulus
            val r32 = BigInteger.ONE.shiftLeft(32)
            val n0inv = modulus.mod(r32).modInverse(r32).negate()
            val rr = BigInteger.ONE.shiftLeft(MODULUS_BYTES * 8).modPow(BigInteger.valueOf(2), modulus)
            val buffer = ByteBuffer.allocate(PUBLIC_KEY_BYTES).order(ByteOrder.LITTLE_ENDIAN)
            buffer.putInt(MODULUS_BYTES / 4)
            buffer.putInt(n0inv.toInt())
            buffer.put(littleEndian(modulus))
            buffer.put(littleEndian(rr))
            buffer.putInt(publicKey.publicExponent.toInt())
            return Base64.getEncoder().encode(buffer.array()) + " $name\u0000".toByteArray()
        }

        private fun littleEndian(value: BigInteger): ByteArray {
            val big = value.toByteArray().dropWhile { it == 0.toByte() }
            require(big.size <= MODULUS_BYTES) { "RSA value wider than 2048 bits" }
            return ByteArray(MODULUS_BYTES).also { out -> big.reversed().toByteArray().copyInto(out) }
        }

        /** A minimal self-signed X.509 v3 certificate for <publicKey>, signed SHA256withRSA by <privateKey>. */
        fun certificate(publicKey: RSAPublicKey, privateKey: PrivateKey): X509Certificate {
            val algorithm = Der.sequence(Der.oid(1, 2, 840, 113549, 1, 1, 11), Der.NULL)
            val name = Der.sequence(Der.set(Der.sequence(Der.oid(2, 5, 4, 3), Der.utf8("00"))))
            // 1970 to 2047, as Shizuku's: adbd ignores the dates.
            val validity = Der.sequence(Der.utcTime("700101000000Z"), Der.generalizedTime("20470101000000Z"))
            val tbs = Der.sequence(Der.explicit(0, Der.integer(BigInteger.valueOf(2))), Der.integer(BigInteger.ONE), algorithm,
                name, validity, name, publicKey.encoded)
            val signature = Signature.getInstance("SHA256withRSA").run { initSign(privateKey); update(tbs); sign() }
            val der = Der.sequence(tbs, algorithm, Der.bitString(signature))
            return CertificateFactory.getInstance("X.509").generateCertificate(der.inputStream()) as X509Certificate
        }
    }

    val publicKey: RSAPublicKey = KeyFactory.getInstance("RSA")
        .generatePublic(RSAPublicKeySpec(privateKey.modulus, privateKey.publicExponent)) as RSAPublicKey
    val adbPublicKey: ByteArray by lazy { adbPublicKey(publicKey) }
    private val certificate by lazy { certificate(publicKey, privateKey) }

    /** The signature for an AUTH token: raw RSA over the SHA-1 padding and the token. */
    fun sign(token: ByteArray): ByteArray = Cipher.getInstance("RSA/ECB/NoPadding").run {
        init(Cipher.ENCRYPT_MODE, privateKey)
        update(SHA1_PADDING)
        doFinal(token)
    }

    /** TLS 1.3 under <provider>, presenting this key, trusting any server: `adbd` on this phone is self-signed. */
    fun sslContext(provider: Provider): SSLContext = SSLContext.getInstance("TLSv1.3", provider).apply {
        init(arrayOf(keyManager), arrayOf(trustAll), SecureRandom())
    }

    private val keyManager = object : X509ExtendedKeyManager() {
        private val alias = "key"
        override fun chooseClientAlias(keyTypes: Array<out String>?, issuers: Array<out Principal>?, socket: Socket?) = alias
        override fun chooseEngineClientAlias(keyTypes: Array<out String>?, issuers: Array<out Principal>?, engine: SSLEngine?) = alias
        override fun getCertificateChain(alias: String?) = if (alias == this.alias) arrayOf(certificate) else null
        override fun getPrivateKey(alias: String?) = if (alias == this.alias) privateKey else null
        override fun getClientAliases(keyType: String?, issuers: Array<out Principal>?) = arrayOf(alias)
        override fun getServerAliases(keyType: String?, issuers: Array<out Principal>?): Array<String>? = null
        override fun chooseServerAlias(keyType: String?, issuers: Array<out Principal>?, socket: Socket?): String? = null
    }

    @Suppress("CustomX509TrustManager", "TrustAllX509TrustManager")
    private val trustAll = object : X509ExtendedTrustManager() {
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?, socket: Socket?) {}
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?, engine: SSLEngine?) {}
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?, socket: Socket?) {}
        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?, engine: SSLEngine?) {}
        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }
}

/** Just enough DER for [AdbKey.certificate]. */
internal object Der {
    val NULL = byteArrayOf(0x05, 0x00)

    fun sequence(vararg parts: ByteArray) = tagged(0x30, *parts)
    fun set(vararg parts: ByteArray) = tagged(0x31, *parts)
    fun explicit(number: Int, part: ByteArray) = tagged(0xa0 or number, part)
    fun integer(value: BigInteger) = tagged(0x02, value.toByteArray())
    fun utf8(value: String) = tagged(0x0c, value.toByteArray())
    fun utcTime(value: String) = tagged(0x17, value.toByteArray())
    fun generalizedTime(value: String) = tagged(0x18, value.toByteArray())
    fun bitString(value: ByteArray) = tagged(0x03, byteArrayOf(0), value)

    fun oid(vararg arcs: Int): ByteArray {
        val body = ByteArrayOutputStream()
        body.write(arcs[0] * 40 + arcs[1])
        for (arc in arcs.drop(2)) {
            val groups = generateSequence(arc) { (it ushr 7).takeIf { rest -> rest > 0 } }.map { it and 0x7f }.toList().reversed()
            groups.forEachIndexed { index, group -> body.write(if (index < groups.lastIndex) group or 0x80 else group) }
        }
        return tagged(0x06, body.toByteArray())
    }

    fun tagged(tag: Int, vararg parts: ByteArray): ByteArray {
        val body = parts.fold(ByteArray(0)) { all, part -> all + part }
        val out = ByteArrayOutputStream()
        out.write(tag)
        if (body.size < 0x80) out.write(body.size) else {
            val length = BigInteger.valueOf(body.size.toLong()).toByteArray().dropWhile { it == 0.toByte() }
            out.write(0x80 or length.size)
            length.forEach { out.write(it.toInt()) }
        }
        out.write(body)
        return out.toByteArray()
    }
}
