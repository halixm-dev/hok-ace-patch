package dev.halixm.hokacepatcher

import android.content.Context
import java.io.File
import java.security.MessageDigest
import org.json.JSONObject

/** Verify the consumed resource manifest before making a runtime directory visible. */
object EngineAssets {
    fun prepare(context: Context): File {
        val manifestBytes = context.assets.open("engine/manifest.json").use { it.readBytes() }
        val digest = MessageDigest.getInstance("SHA-256").digest(manifestBytes)
            .joinToString("") { "%02x".format(it) }
        val root = File(context.filesDir, "engine/$digest")
        val files = JSONObject(String(manifestBytes, Charsets.UTF_8)).getJSONObject("files")
        root.mkdirs()
        for (name in files.keys()) {
            check(!name.startsWith("/") && name.split('/').none { it == ".." }) { "Invalid resource path" }
            val target = File(root, name)
            val expected = files.getString(name)
            fun hash(file: File): String {
                val md = MessageDigest.getInstance("SHA-256")
                file.inputStream().use { stream ->
                    val buffer = ByteArray(1024 * 1024)
                    while (true) {
                        val count = stream.read(buffer)
                        if (count < 0) break
                        md.update(buffer, 0, count)
                    }
                }
                return md.digest().joinToString("") { "%02x".format(it) }
            }
            if (target.isFile && hash(target) == expected) continue
            target.parentFile!!.mkdirs()
            val temp = File(target.parentFile, target.name + ".partial")
            context.assets.open("engine/$name.payload").use { source -> temp.outputStream().use { source.copyTo(it) } }
            check(hash(temp) == expected) { "Resource digest mismatch: $name" }
            if (target.exists()) check(target.delete()) { "Cannot replace invalid resource: $name" }
            check(temp.renameTo(target)) { "Cannot install resource: $name" }
            check(target.setReadOnly()) { "Cannot protect resource: $name" }
        }
        return root
    }
}
