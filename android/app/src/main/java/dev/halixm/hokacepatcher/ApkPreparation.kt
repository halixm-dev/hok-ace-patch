package dev.halixm.hokacepatcher

import android.content.Context
import android.content.pm.PackageManager
import android.os.ParcelFileDescriptor
import android.util.AtomicFile
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.UUID
import java.io.RandomAccessFile
import java.security.MessageDigest
import java.nio.file.Files
import java.nio.file.LinkOption
import org.json.JSONObject

/** Prepare manifest-only stable-key APKs and recovery identity before offering any game mutation. */
class ApkPreparation(private val context: Context) {
    data class Prepared(val directory: File, val source: ApkIdentity, val normal: ApkIdentity, val access: ApkIdentity) {
        val requiresSignatureConversion: Boolean get() = source.certificateSha256 != GameSigner.CERTIFICATE_SHA256
        val accessFile: File get() = File(directory, "apks/access.apk")
    }

    fun prepare(device: IPrivilegedDeviceService, report: (String) -> Unit): Prepared =
        prepare(device, report, {})

    fun prepare(device: IPrivilegedDeviceService, report: (String) -> Unit, checkpoint: () -> Unit): Prepared {
        RandomAccessFile(File(context.filesDir, "preparation.lock"), "rw").use { file ->
            file.channel.use { channel ->
                val lock = checkNotNull(channel.tryLock()) { "Another APK preparation is running" }
                lock.use { return prepareLocked(device, report, checkpoint) }
            }
        }
    }

    /**
     * Free saved APKs the installed game can no longer use, once it is verified as the stable-key normal
     * build <installed>:
     *
     * - every saved official source APK (`original.apk`, about 2 GB). It is read only while deriving the
     *   normal and access APKs; reuse, first setup and recovery go by the receipt's identity, never by the
     *   file, and an official-signature APK cannot be installed again without first setup's uninstall,
     *   which copies the installed app afresh;
     * - every preparation made for another game version (its access APK, about 2 GB). Access is
     *   installed only over a normal build of the same version, so it cannot serve this game again; a new
     *   version prepares its own.
     *
     * <keep> is the preparation a run is using. Skipped while a preparation runs; a folder whose receipt
     * will not read is left alone, and nothing another retained APK path links to is deleted. Recovery
     * APKs live apart (`RecoveryStore`) and are never touched here.
     */
    fun releaseUnneeded(installed: ApkIdentity, keep: File?, report: (String) -> Unit) {
        installed.requireRecovery()
        RandomAccessFile(File(context.filesDir, "preparation.lock"), "rw").use { file ->
            file.channel.use { channel ->
                val lock = try { channel.tryLock() } catch (_: java.nio.channels.OverlappingFileLockException) { null }
                    ?: return
                lock.use { releaseLocked(installed, keep?.canonicalFile, report) }
            }
        }
    }

    private fun releaseLocked(installed: ApkIdentity, keep: File?, report: (String) -> Unit) {
        val root = File(context.filesDir, "preparations")
        val folders = root.listFiles().orEmpty().filter {
            it.isDirectory && !Files.isSymbolicLink(it.toPath()) && File(it, "receipt.json").isFile
        }
        val stale = folders.filter { folder ->
            if (folder.canonicalFile == keep) return@filter false
            val normal = runCatching {
                ApkIdentity.fromJson(JSONObject(String(AtomicFile(File(folder, "receipt.json")).readFully(),
                    Charsets.UTF_8)).getJSONObject("normal"))
            }.getOrNull() ?: return@filter false
            normal.versionCode != installed.versionCode || normal.versionName != installed.versionName
        }.toSet()
        // Deduplication and sessions may point a retained APK path at another file; never pull one from under it.
        val linked = (listOf(File(context.filesDir, "recovery"), File(context.filesDir, "sessions"))
            .flatMap { it.listFiles().orEmpty().toList() } + (folders - stale))
            .flatMap { listOf(File(it, "normal.apk"), File(it, "access.apk"), File(it, "apks/access.apk")) }
            .filter { Files.isSymbolicLink(it.toPath()) }
            .mapNotNull { runCatching { it.canonicalPath }.getOrNull() }
        fun protects(path: File) = path.canonicalPath.let { target ->
            linked.any { it == target || it.startsWith(target + File.separator) }
        }
        var sources = 0L
        var versions = 0L
        for (folder in folders) {
            if (folder in stale && !protects(folder)) {
                runCatching { versions += DurableFiles.deleteTree(folder); DurableFiles.syncDirectory(root) }
                    .onFailure { report("Could not remove saved APKs of an older game version; keeping them") }
                continue
            }
            val source = File(folder, "original.apk")
            if (!Files.exists(source.toPath(), LinkOption.NOFOLLOW_LINKS) || protects(source)) continue
            runCatching { sources += DurableFiles.deleteTree(source); DurableFiles.syncDirectory(folder) }
                .onFailure { report("Could not remove a saved original game APK; keeping it") }
        }
        if (sources > 0) report("Freed ${StorageBudget.freeSpaceLabel(sources)}: removed the saved original game APK, which the installed game no longer needs")
        if (versions > 0) report("Freed ${StorageBudget.freeSpaceLabel(versions)}: removed saved APKs made for an older game version")
    }

    private fun prepareLocked(device: IPrivilegedDeviceService, report: (String) -> Unit, checkpoint: () -> Unit): Prepared {
        checkpoint()
        check(FirstSetupJournal.pending(context).isEmpty()) { "Finish or recover first-time setup before preparing more game files" }
        check(SessionJournal.pending(File(context.filesDir, "sessions")).isEmpty()) {
            "Recover the interrupted patch before preparing more game files"
        }
        val info = JSONObject(device.gameApkInfo())
        val bytes = info.getLong("bytes")
        check(bytes in 1..(3L * 1024 * 1024 * 1024)) { "Unsupported source APK size" }
        // Only first setup cares about other profiles; refuse here rather than after minutes of preparation.
        if (installedCertificate() != GameSigner.CERTIFICATE_SHA256) {
            report("Checking other Android profiles for the game")
            device.checkGameProfiles()
        }
        report("Checking saved normal and access APKs")
        val cached = File(context.filesDir, "preparations").listFiles().orEmpty()
            .filter { File(it, "receipt.json").isFile }.sortedByDescending { it.lastModified() }
        for (folder in cached) {
            checkpoint()
            val saved = runCatching { load(folder.name) }.getOrNull() ?: continue
            val candidates = listOf(saved.normal, saved.source).distinct().filter { it.bytes == bytes }
            for (identity in candidates) {
                if (runCatching { InstalledGameVerifier(context, device).verify(identity) }.isFailure) continue
                checkpoint()
                // Keep historical source identity; bind the next confirmation to the installed identity.
                val receiptFile = AtomicFile(File(folder, "receipt.json"))
                val receipt = JSONObject(String(receiptFile.readFully(), Charsets.UTF_8))
                receipt.put("installed_source", identity.json())
                val stream = receiptFile.startWrite()
                try {
                    stream.write(receipt.toString().toByteArray(Charsets.UTF_8)); stream.fd.sync()
                    receiptFile.finishWrite(stream); DurableFiles.syncDirectory(folder)
                } catch (error: Throwable) { receiptFile.failWrite(stream); throw error }
                report("Reusing verified saved APKs — no new APK copies needed")
                deduplicateApks(report, checkpoint)
                return saved.copy(source = identity)
            }
        }
        // Only a preparation creates these folders, under the lock held here, and it writes the receipt last:
        // a folder without one is an attempt that died before finishing. Earlier builds kept them.
        val preparations = File(context.filesDir, "preparations")
        // Deduplication may have pointed a retained APK at a file inside one by symlink; never pull it from under it.
        val linked = listOf(File(context.filesDir, "recovery"), File(context.filesDir, "sessions"), preparations)
            .flatMap { root -> root.walkTopDown().filter { Files.isSymbolicLink(it.toPath()) }.toList() }
            .mapNotNull { runCatching { it.canonicalPath }.getOrNull() }
        var abandoned = 0L
        for (folder in preparations.listFiles().orEmpty()) {
            if (!folder.isDirectory || Files.isSymbolicLink(folder.toPath()) || File(folder, "receipt.json").exists()) continue
            val prefix = folder.canonicalPath + File.separator
            if (linked.any { it.startsWith(prefix) }) continue
            runCatching { abandoned += DurableFiles.deleteTree(folder) }
                .onFailure { report("Could not remove an unfinished earlier preparation; keeping it") }
        }
        if (abandoned > 0) {
            DurableFiles.syncDirectory(preparations)
            report("Freed ${StorageBudget.freeSpaceLabel(abandoned)} left by unfinished earlier preparations")
        }
        StorageBudget.releaseReplacedGameApks(device, report)
        // Source + signed normal + unsigned access + signed access is the measured implementation's peak.
        StorageBudget.requireAvailable(context.filesDir, "APK preparation", bytes, bytes, bytes, bytes)
        val directory = File(context.filesDir, "preparations/${UUID.randomUUID()}")
        check(!directory.exists())
        DurableFiles.createDirectories(directory)
        try {
            return prepareInto(directory, bytes, device, report, checkpoint)
        } catch (error: Throwable) {
            // Until its receipt exists nothing refers to this folder; a failed or cancelled preparation
            // otherwise leaves ~3 APK copies (measured: 18 GB after three retries on one phone).
            if (!File(directory, "receipt.json").exists()) runCatching {
                val freed = DurableFiles.deleteTree(directory)
                DurableFiles.syncDirectory(directory.parentFile!!)
                if (freed > 0) report("Removed ${StorageBudget.freeSpaceLabel(freed)} left by the failed preparation")
            }
            throw error
        }
    }

    private fun prepareInto(directory: File, bytes: Long, device: IPrivilegedDeviceService,
                            report: (String) -> Unit, checkpoint: () -> Unit): Prepared {
        val source = File(directory, "original.apk")
        report("Copying and verifying the installed source APK")
        ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_CREATE or
            ParcelFileDescriptor.MODE_WRITE_ONLY or ParcelFileDescriptor.MODE_TRUNCATE).use {
            val copied = JSONObject(device.copyGameApk(it))
            check(copied.getLong("bytes") == bytes && source.length() == bytes &&
                copied.getString("sha256") == ApkIdentity.digest(source)) { "Source APK transport changed" }
        }
        checkpoint()
        val original = ApkIdentity.read(context, source)
        check(!original.debuggable) { "A debug access APK cannot become source/recovery material" }
        val root = EngineAssets.prepare(context)
        if (!Python.isStarted()) Python.start(AndroidPlatform(context))
        val bridge = Python.getInstance().getModule("android_bridge")
        DiagnosticTrace.timed("engine", "engine_preflight") { bridge.callAttr("engine_preflight", root.path) }
        checkpoint()
        report("Preparing normal and access APKs using the stable game key")
        val result = JSONObject(DiagnosticTrace.timed("engine", "prepare_game_apks") {
            bridge.callAttr("prepare_game_apks", root.path, source.path, File(directory, "apks").path, GameSigner(root))
        }.toString())
        checkpoint()
        val normalFile = File(directory, "apks/normal.apk")
        val normal = ApkIdentity.read(context, normalFile)
        normal.requireRecovery()
        val accessFile = File(directory, "apks/access.apk")
        val access = ApkIdentity.read(context, accessFile)
        // Name every field that differs: a bare "differs" on one Android 15 phone left the cause unknowable.
        val differences = buildList {
            if (!access.debuggable) add("access not debuggable per Android (its manifest declares debuggable: " +
                "${manifestDeclaresDebuggable(accessFile)}; normal manifest: ${manifestDeclaresDebuggable(normalFile)})")
            if (access.certificateSha256 != normal.certificateSha256)
                add("signer access ${access.certificateSha256.take(16)} vs normal ${normal.certificateSha256.take(16)}")
            if (access.versionCode != original.versionCode || normal.versionCode != original.versionCode)
                add("versionCode source ${original.versionCode}, normal ${normal.versionCode}, access ${access.versionCode}")
            if (access.versionName != original.versionName || normal.versionName != original.versionName)
                add("versionName source ${original.versionName}, normal ${normal.versionName}, access ${access.versionName}")
        }
        check(differences.isEmpty()) {
            "Prepared APK version/signer/debug identity differs: ${differences.joinToString("; ")}"
        }
        check(normal.sha256 == result.getJSONObject("normal").getString("sha256") &&
            access.sha256 == result.getJSONObject("access").getString("sha256")) { "Prepared APK hash differs" }
        RecoveryStore(context).adopt(normalFile)
        check(accessFile.setReadOnly() && source.setReadOnly()) { "Cannot protect prepared APK material" }
        val receipt = JSONObject().put("schema", 1).put("source", original.json()).put("normal", normal.json())
            .put("access", access.json()).put("engine_id", root.name).put("label_warning", result.opt("label_warning"))
        val storage = AtomicFile(File(directory, "receipt.json"))
        val stream = storage.startWrite()
        try {
            stream.write(receipt.toString().toByteArray(Charsets.UTF_8)); stream.fd.sync(); storage.finishWrite(stream)
            DurableFiles.syncDirectory(File(directory, "apks"))
            DurableFiles.syncDirectory(directory)
        } catch (error: Throwable) { storage.failWrite(stream); throw error }
        // The independently rehashed cache now owns normal recovery. Keep source/access and receipt; the
        // source goes once the installed game is the stable-key build (releaseUnneeded).
        check(normalFile.delete()) { "Cannot remove duplicate prepared normal APK" }
        return Prepared(directory, original, normal, access)
    }

    /** The installed game's single signer, or null when Android will not say; null runs the profile check too. */
    private fun installedCertificate(): String? = runCatching {
        val signers = checkNotNull(context.packageManager.getPackageInfo(PrivilegedDeviceService.GAME,
            PackageManager.GET_SIGNING_CERTIFICATES).signingInfo).apkContentsSigners
        MessageDigest.getInstance("SHA-256").digest(signers.single().toByteArray()).joinToString("") { "%02x".format(it) }
    }.getOrNull()

    /** The manifest's own android:debuggable, read by the engine's AXML parser; Android's view is ApkIdentity. */
    private fun manifestDeclaresDebuggable(apk: File): String = runCatching {
        val manifest = java.util.zip.ZipFile(apk).use { zip ->
            zip.getInputStream(checkNotNull(zip.getEntry("AndroidManifest.xml"))).use { it.readBytes() }
        }
        Python.getInstance().getModule("axml_set_debuggable").callAttr("is_debuggable", manifest).toBoolean().toString()
    }.getOrElse { "unknown (${it.javaClass.simpleName})" }

    fun load(id: String): Prepared {
        GameFilePolicy.session(id)
        val directory = File(context.filesDir, "preparations/$id")
        val receipt = JSONObject(String(AtomicFile(File(directory, "receipt.json")).readFully(), Charsets.UTF_8))
        check(receipt.getInt("schema") == 1)
        val original = ApkIdentity.fromJson(receipt.getJSONObject("source"))
        check(!original.debuggable)
        val normal = ApkIdentity.fromJson(receipt.getJSONObject("normal"))
        check(original.packageName == normal.packageName && original.versionCode == normal.versionCode &&
            original.versionName == normal.versionName) { "Source and recovery versions differ" }
        // APK content is independently verified below; snapshot/translation updates must not rebuild it.
        check(receipt.getString("engine_id").matches(Regex("[0-9a-f]{64}"))) { "Invalid preparation provenance" }
        check(RecoveryStore(context).verify(normal.sha256) == normal)
        val access = ApkIdentity.fromJson(receipt.getJSONObject("access"))
        check(access.debuggable && access.certificateSha256 == normal.certificateSha256 &&
            access.versionCode == normal.versionCode && access.versionName == normal.versionName)
        check(ApkIdentity.read(context, File(directory, "apks/access.apk")) == access)
        val selected = receipt.optJSONObject("installed_source")?.let { ApkIdentity.fromJson(it) } ?: original
        check(selected == original || selected == normal) { "Cached installed source is unrelated" }
        return Prepared(directory, selected, normal, access)
    }

    /** Link only byte-identical immutable APKs; every pathname and recovery receipt stays valid. */
    private fun deduplicateApks(report: (String) -> Unit, checkpoint: () -> Unit) {
        val canonical = mutableMapOf<String, File>()
        val roots = listOf(File(context.filesDir, "recovery"), File(context.filesDir, "preparations"))
        var reclaimed = 0L
        for (root in roots) for (file in root.walkTopDown().filter { it.isFile && it.extension == "apk" }) {
            checkpoint()
            if (!android.system.OsConstants.S_ISREG(android.system.Os.lstat(file.path).st_mode) ||
                !file.canonicalPath.startsWith(context.filesDir.canonicalPath + File.separator)) continue
            if (android.system.Os.stat(file.path).st_mode and 146 != 0) continue
            val identity = runCatching { ApkIdentity.read(context, file) }.getOrNull() ?: continue
            val retained = canonical[identity.sha256]
            if (retained == null) { canonical[identity.sha256] = file; continue }
            val before = android.system.Os.stat(file.path)
            val target = android.system.Os.stat(retained.path)
            if (before.st_dev != target.st_dev || before.st_ino == target.st_ino) continue
            val temporary = File(file.parentFile, "${file.name}.dedupe-${UUID.randomUUID()}")
            try {
                try { android.system.Os.link(retained.path, temporary.path) }
                catch (error: android.system.ErrnoException) {
                    // Android SELinux may deny hard links. Point only to a retained immutable private file.
                    android.system.Os.symlink(retained.canonicalPath, temporary.path)
                }
                DurableFiles.syncDirectory(file.parentFile!!)
                check(ApkIdentity.digest(temporary) == identity.sha256) { "Shared APK hash differs" }
                android.system.Os.rename(temporary.path, file.path)
                DurableFiles.syncDirectory(file.parentFile!!)
                if (before.st_nlink == 1L) reclaimed += identity.bytes
            } catch (error: Exception) {
                report("Could not share a duplicate APK; keeping its saved copy (${error.javaClass.simpleName})")
            } finally { if (temporary.exists()) temporary.delete() }
        }
        if (reclaimed > 0) report("Freed ${StorageBudget.freeSpaceLabel(reclaimed)} by sharing identical saved APKs. Recovery copies kept.")
    }
}
