package dev.halixm.hokacepatcher

import org.json.JSONObject
import java.io.IOException
import java.io.ByteArrayOutputStream
import java.math.BigInteger
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL

/** Read-only, unauthenticated release lookup, independent of the patch worker. */
class AppUpdateChecker(
    private val openConnection: () -> HttpURLConnection = {
        URL(API_URL).openConnection() as HttpURLConnection
    }
) {
    data class Result(val message: String, val version: String? = null, val downloadUrl: String? = null)

    fun check(installed: String): Result {
        var connection: HttpURLConnection? = null
        return try {
            connection = openConnection()
            connection.connectTimeout = 10_000
            connection.readTimeout = 10_000
            connection.instanceFollowRedirects = false
            connection.useCaches = false
            connection.setRequestProperty("Accept", "application/vnd.github+json")
            connection.setRequestProperty("X-GitHub-Api-Version", "2026-03-10")
            connection.setRequestProperty("User-Agent", "HOK-ACE-Language-Patcher/$installed")
            when (connection.responseCode) {
                200 -> {
                    val bytes = connection.inputStream.use { stream ->
                        val output = ByteArrayOutputStream()
                        val buffer = ByteArray(8192)
                        while (output.size() <= MAX_RESPONSE_BYTES) {
                            if (Thread.currentThread().isInterrupted) throw IOException("Check cancelled")
                            val count = stream.read(buffer, 0, minOf(buffer.size, MAX_RESPONSE_BYTES + 1 - output.size()))
                            if (count < 0) break
                            output.write(buffer, 0, count)
                        }
                        output.toByteArray()
                    }
                    if (bytes.size > MAX_RESPONSE_BYTES) Result(INVALID_RELEASE)
                    else parse(installed, String(bytes, Charsets.UTF_8))
                }
                403, 429 -> Result("GitHub is limiting update checks. Try again later.")
                404 -> Result("No published patcher release was found. Try again later.")
                else -> Result("GitHub could not check for updates. Try again later.")
            }
        } catch (_: SocketTimeoutException) {
            Result("Update check timed out. Try again.")
        } catch (_: IOException) {
            Result("Cannot reach GitHub. Check your internet connection and try again.")
        } catch (_: Exception) {
            Result(INVALID_RELEASE)
        } finally {
            connection?.disconnect()
        }
    }

    companion object {
        const val API_URL = "https://api.github.com/repos/halixm-dev/hok-ace-patch/releases/latest"
        private const val RELEASE_ROOT = "https://github.com/halixm-dev/hok-ace-patch/releases/download/"
        private const val MAX_RESPONSE_BYTES = 1_048_576
        private const val INVALID_RELEASE = "The release information could not be read. Try again later."
        private val VERSION = Regex("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")

        /** The five components are numeric; no lexicographic comparison or integer overflow. */
        fun compareVersions(left: String, right: String): Int {
            require(VERSION.matches(left) && VERSION.matches(right)) { "Invalid patcher version" }
            left.split('.').zip(right.split('.')).forEach { (a, b) ->
                val order = BigInteger(a).compareTo(BigInteger(b))
                if (order != 0) return order
            }
            return 0
        }

        fun parse(installed: String, body: String): Result = try {
            val release = JSONObject(body)
            val tag = release.getString("tag_name")
            require(tag.startsWith("android-v"))
            require(!release.getBoolean("draft") && !release.getBoolean("prerelease"))
            val version = tag.removePrefix("android-v")
            when (compareVersions(version, installed)) {
                0 -> Result("You have the latest patcher version.")
                -1 -> Result("Your patcher version is newer than the latest release.")
                else -> {
                    val expectedUrl = "$RELEASE_ROOT$tag/hok-ace-patch.apk"
                    val assets = release.getJSONArray("assets")
                    val available = (0 until assets.length()).any { index ->
                        val asset = assets.getJSONObject(index)
                        asset.optString("name") == "hok-ace-patch.apk" &&
                            asset.optString("state") == "uploaded" && asset.optLong("size") > 0 &&
                            asset.optString("browser_download_url") == expectedUrl
                    }
                    if (available) Result("A newer patcher version is available.", version, expectedUrl)
                    else Result("A newer release has no downloadable Android APK yet. Try again later.")
                }
            }
        } catch (_: Exception) {
            Result(INVALID_RELEASE)
        }
    }
}
