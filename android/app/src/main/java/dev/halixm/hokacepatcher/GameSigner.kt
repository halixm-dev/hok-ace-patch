package dev.halixm.hokacepatcher

import java.io.File
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.spec.PKCS8EncodedKeySpec

/** RSA operation only: Python retains the measured streaming ZIP and v2 digest implementation. */
class GameSigner(engineRoot: File) {
    companion object {
        const val CERTIFICATE_SHA256 = "a4b22b2385dab6c96768231611a23a9d742779f5a3ddf5c2fc34751b0c7fbc0a"
    }
    val certificateDer = File(engineRoot, "key/cert.der").readBytes()
    private val certificate = CertificateFactory.getInstance("X.509")
        .generateCertificate(certificateDer.inputStream())
    private val key = KeyFactory.getInstance("RSA").generatePrivate(
        PKCS8EncodedKeySpec(File(engineRoot, "key/key.pk8").readBytes()))
    val publicKeyDer: ByteArray = certificate.publicKey.encoded

    init {
        val hash = MessageDigest.getInstance("SHA-256").digest(certificateDer)
            .joinToString("") { "%02x".format(it) }
        check(hash == CERTIFICATE_SHA256) { "Game signing certificate differs from the stable key" }
    }

    fun sign(data: ByteArray): ByteArray {
        require(data.size in 1..65536) { "Unsupported signing payload length" }
        val signature = Signature.getInstance("SHA256withRSA")
        signature.initSign(key)
        signature.update(data)
        val result = signature.sign()
        val verifier = Signature.getInstance("SHA256withRSA")
        verifier.initVerify(certificate.publicKey)
        verifier.update(data)
        check(verifier.verify(result)) { "Game key and certificate do not match" }
        return result
    }
}
