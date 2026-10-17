package dev.halixm.hokacepatcher

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL

/** Release policy and transport failures run offline; no GitHub account or device needed. */
class AppUpdateCheckerTest {
    private val current = "1.6.0.1.1"
    private val newer = "1.6.0.1.10"
    private fun release(version: String = newer, assets: Boolean = true): String = """
        {"tag_name":"android-v$version","draft":false,"prerelease":false,"assets":[
        ${if (assets) """{"name":"hok-ace-patch.apk","state":"uploaded","size":42,
        "browser_download_url":"https://github.com/halixm-dev/hok-ace-patch/releases/download/android-v$version/hok-ace-patch.apk"}""" else ""}]}
    """.trimIndent()

    @Test fun versionsCompareEveryComponentNumerically() {
        assertTrue(AppUpdateChecker.compareVersions(newer, current) > 0)
        assertTrue(AppUpdateChecker.compareVersions("1.10.0.0.0", "1.9.99.99.99") > 0)
        assertEquals(0, AppUpdateChecker.compareVersions("01.6.0.1.1", current))
        assertTrue(AppUpdateChecker.compareVersions("1.6.0.1.999999999999999999999", current) > 0)
        assertTrue(AppUpdateChecker.compareVersions("1.5.99.99.99", current) < 0)
    }

    @Test fun onlyNewerStableAndroidReleaseOffersDownload() {
        val result = AppUpdateChecker.parse(current, release())
        assertEquals(newer, result.version)
        assertTrue(result.downloadUrl!!.endsWith("android-v$newer/hok-ace-patch.apk"))
        assertEquals("You have the latest patcher version.", AppUpdateChecker.parse(current, release(current)).message)
        assertEquals("Your patcher version is newer than the latest release.",
            AppUpdateChecker.parse(newer, release(current)).message)
        assertNull(AppUpdateChecker.parse(current, release().replace("\"prerelease\":false", "\"prerelease\":true")).downloadUrl)
        assertNull(AppUpdateChecker.parse(current, release().replace("\"draft\":false", "\"draft\":true")).downloadUrl)
    }

    @Test fun malformedVersionsAndBodiesNeverOfferAnUpdate() {
        listOf("1.2.3", "1.6.0.1.2-beta", "1.6.0.1.-1", "1.6.0.1.2.3", "").forEach {
            assertNull(AppUpdateChecker.parse(current, release(it)).downloadUrl)
        }
        listOf("garbage", "{}", "[]", release().replace("android-v", "v")).forEach {
            assertNull(AppUpdateChecker.parse(current, it).downloadUrl)
        }
        assertNull(AppUpdateChecker.parse("bad installed version", release()).downloadUrl)
    }

    @Test fun missingUnreadyEmptyOrForeignApkDoesNotOfferDownload() {
        assertTrue(AppUpdateChecker.parse(current, release(assets = false)).message.contains("no downloadable"))
        listOf(
            release().replace("github.com/", "example.com/"),
            release().replace("\"uploaded\"", "\"new\""),
            release().replace("\"size\":42", "\"size\":0"),
            release().replace("hok-ace-patch.apk", "other.apk")
        ).forEach { assertNull(AppUpdateChecker.parse(current, it).downloadUrl) }
    }

    private class Connection(private val status: Int, private val body: String = "", private val failure: IOException? = null)
        : HttpURLConnection(URL(AppUpdateChecker.API_URL)) {
        var closed = false
        override fun connect() = Unit
        override fun disconnect() { closed = true }
        override fun usingProxy() = false
        override fun getResponseCode(): Int { failure?.let { throw it }; return status }
        override fun getInputStream() = ByteArrayInputStream(body.toByteArray(Charsets.UTF_8))
    }

    @Test fun successfulTransportHasTimeoutsHeadersAndClosesConnection() {
        val connection = Connection(200, release())
        assertNotNull(AppUpdateChecker { connection }.check(current).downloadUrl)
        assertEquals(10_000, connection.connectTimeout)
        assertEquals(10_000, connection.readTimeout)
        assertEquals("application/vnd.github+json", connection.getRequestProperty("Accept"))
        assertNull(connection.getRequestProperty("Authorization"))
        assertFalse(connection.instanceFollowRedirects)
        assertTrue(connection.closed)
    }

    @Test fun apiFailuresAndOversizedResponseAreRecoverable() {
        listOf(403, 429, 404, 500, 302).forEach { status ->
            val connection = Connection(status)
            val result = AppUpdateChecker { connection }.check(current)
            assertNull(result.downloadUrl)
            assertTrue(result.message.contains("later"))
            assertTrue(connection.closed)
        }
        assertNull(AppUpdateChecker { Connection(200, " ".repeat(1_048_577)) }.check(current).downloadUrl)
    }

    @Test fun offlineAndTimeoutAreRecoverableAndCloseConnection() {
        listOf(IOException("offline"), SocketTimeoutException()).forEach { failure ->
            val connection = Connection(200, failure = failure)
            val result = AppUpdateChecker { connection }.check(current)
            assertNull(result.downloadUrl)
            assertTrue(result.message.contains(if (failure is SocketTimeoutException) "timed out" else "internet"))
            assertTrue(connection.closed)
        }
        assertNull(AppUpdateChecker { throw IOException("DNS failed") }.check(current).downloadUrl)
    }

    @Test fun allResultMessagesHaveIndonesianTranslations() {
        val messages = listOf(
            AppUpdateChecker.parse(current, release()).message,
            AppUpdateChecker.parse(current, release(current)).message,
            AppUpdateChecker.parse(newer, release(current)).message,
            AppUpdateChecker.parse(current, release(assets = false)).message,
            AppUpdateChecker.parse(current, "invalid").message,
            AppUpdateChecker { throw IOException() }.check(current).message,
            AppUpdateChecker { throw SocketTimeoutException() }.check(current).message
        ) + listOf(403, 404, 500).map { status -> AppUpdateChecker { Connection(status) }.check(current).message }
        messages.forEach { message ->
            assertEquals(message, UiText.translate("en", message))
            assertNotEquals(message, UiText.translate("id", message))
        }
    }
}
