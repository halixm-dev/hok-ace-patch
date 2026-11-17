package dev.halixm.hokacepatcher

import java.io.File
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

/** Schema-1 read-only counterpart of run_artifacts.py. Never grants mutation authorization.
 * Callers canonicalize a trusted platform root once (e.g. context.filesDir); descendants
 * must remain unlinked. Reconcile live inputs separately and hold attempt ownership.
 */
object ArtifactReceipts {
    const val NAME = "build-receipt.json"
    const val MAX_JSON = 16 * 1024 * 1024
    private const val MAX_INTEGER = 9007199254740991L
    private val stages = setOf("prepared", "snapshot", "pristine", "staged", "installed")
    private val references = setOf("summary", "delta", "manifest")
    private val hash = Regex("[0-9a-f]{64}")

    /**
     * Reads a file's hard-link count; anything but exactly 1 refuses. Production reads `unix:nlink`,
     * and a host without that view throws, so an unreadable count fails closed and is never taken as 1.
     * Internal seam only so JVM unit tests on hosts without the unix view can supply a count.
     */
    internal var linkCount: (java.nio.file.Path) -> Long = { path -> (Files.getAttribute(path, "unix:nlink") as Number).toLong() }

    private fun keys(value: JSONObject) = value.keys().asSequence().toSet()
    private fun schema(value: JSONObject): Boolean {
        val number = value.opt("schema")
        return (number is Int || number is Long) && (number as Number).toLong() == 1L
    }

    fun canonical(value: Any?): String {
        fun encode(item: Any?, depth: Int): String {
            require(depth <= 32) { "Identity nesting exceeds limit" }
            return when (item) {
                null, JSONObject.NULL -> "null"
                is Boolean -> item.toString()
                is Byte, is Short, is Int, is Long -> {
                    val number = (item as Number).toLong()
                    require(number in -MAX_INTEGER..MAX_INTEGER)
                    number.toString()
                }
                is String -> buildString {
                    append('"')
                    var index = 0
                    while (index < item.length) {
                        val char = item[index++]
                        when (char) {
                            '"' -> append("\\\"")
                            '\\' -> append("\\\\")
                            '\b' -> append("\\b")
                            '\u000c' -> append("\\f")
                            '\n' -> append("\\n")
                            '\r' -> append("\\r")
                            '\t' -> append("\\t")
                            else -> {
                                if (char.code < 32) append("\\u%04x".format(char.code))
                                else if (char.isHighSurrogate()) {
                                    require(index < item.length && item[index].isLowSurrogate())
                                    append(char); append(item[index++])
                                } else { require(!char.isLowSurrogate()); append(char) }
                            }
                        }
                    }
                    append('"')
                }
                is JSONObject -> keys(item).sorted().joinToString(",", "{", "}") { key ->
                    require(key.all { it.code < 128 }) { "Identity keys must be ASCII" }
                    encode(key, depth + 1) + ":" + encode(item.get(key), depth + 1)
                }
                is JSONArray -> (0 until item.length()).joinToString(",", "[", "]") {
                    encode(item.get(it), depth + 1)
                }
                else -> error("Unsupported identity value")
            }
        }
        val result = encode(value, 0)
        require(result.toByteArray(Charsets.UTF_8).size <= MAX_JSON)
        return result
    }

    fun identityKey(identity: Any?): String = digest(canonical(JSONObject()
        .put("schema", 1).put("identity", identity ?: JSONObject.NULL)).toByteArray(Charsets.UTF_8))

    fun digest(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it) }

    fun relativePath(name: String): String {
        require(name.length in 1..1024 && name.all { it.code < 128 })
        val reserved = setOf("CON", "PRN", "AUX", "NUL", "CLOCK$") +
            (1..9).flatMap { listOf("COM$it", "LPT$it") }
        name.split('/').forEach { part ->
            require(part.isNotEmpty() && part != "." && part != ".." &&
                !part.endsWith('.') && !part.endsWith(' ') &&
                part.none { it.code < 32 || it in "\\:<>\"|?*" } &&
                part.substringBefore('.').uppercase(java.util.Locale.ROOT) !in reserved)
        }
        return name
    }

    fun safe(file: File, directory: Boolean = false) {
        val path = file.toPath().toAbsolutePath().normalize()
        var current = path
        while (true) {
            require(!Files.isSymbolicLink(current)) { "Linked artifact" }
            current = current.parent ?: break
        }
        require(file.canonicalFile.toPath() == path) { "Artifact path escaped" }
        require(if (directory) file.isDirectory else file.isFile)
    }

    fun fileIdentity(file: File): JSONObject {
        safe(file)
        val md = MessageDigest.getInstance("SHA-256")
        var size = 0L
        file.inputStream().use { stream ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                md.update(buffer, 0, count); size += count
            }
        }
        require(size <= MAX_INTEGER)
        return JSONObject().put("size", size).put("sha256", md.digest().joinToString("") { "%02x".format(it) })
    }

    fun validateManifest(manifest: JSONObject) {
        require(manifest.length() <= 100000)
        val seen = mutableSetOf<String>()
        keys(manifest).forEach { name ->
            relativePath(name)
            require(seen.add(name.lowercase(java.util.Locale.ROOT))) { "Conflicting artifact paths" }
            val item = manifest.getJSONObject(name)
            require(keys(item) == setOf("size", "sha256"))
            val size = item.get("size")
            require((size is Long || size is Int) && (size as Number).toLong() in 0..MAX_INTEGER)
            require(item.get("sha256") is String && hash.matches(item.getString("sha256")))
        }
    }

    fun treeManifest(root: File, excluded: Set<String> = emptySet()): JSONObject {
        safe(root, true)
        val result = JSONObject()
        fun walk(directory: File) {
            safe(directory, true)
            checkNotNull(directory.listFiles()).sortedBy { it.name }.forEach { file ->
                if (file.isDirectory) walk(file) else {
                    safe(file)
                    val name = file.relativeTo(root).invariantSeparatorsPath
                    if (name !in excluded) {
                        relativePath(name)
                        // Reject writable aliases, including hard-linked rollback/build inputs.
                        require(linkCount(file.toPath()) == 1L)
                        result.put(name, fileIdentity(file))
                        require(result.length() <= 100000)
                    }
                }
            }
        }
        walk(root); validateManifest(result)
        return result
    }

    private fun validateInput(value: JSONObject) {
        require(keys(value) == setOf("schema", "target", "request", "game", "apks", "delta", "translation", "producer"))
        require(schema(value))
        val target = value.getJSONObject("target")
        require(keys(target).containsAll(setOf("package", "android_user", "device", "provider")))
        listOf("package", "device", "provider").forEach {
            require(target.get(it) is String && target.getString(it).isNotBlank())
        }
        val user = target.get("android_user")
        require((user is Int || user is Long) && (user as Number).toLong() in 0..MAX_INTEGER)
        val request = value.getJSONObject("request")
        require(request.getString("action") in setOf("translate", "remove", "first_setup", "redownload"))
        require(request.get("language") in setOf("en", "id")); request.getJSONObject("options")
        val game = value.getJSONObject("game")
        require(game.has("readiness")); validateManifest(game.getJSONObject("files"))
        require(value.getJSONObject("translation").length() > 0)
        for (name in listOf("apks", "delta")) if (!value.isNull(name)) require(value.getJSONObject(name).length() > 0)
        val producer = value.getJSONObject("producer")
        require(schema(producer) && producer.get("complete") == true)
        val required = when (producer.getString("kind")) {
            "windows-source" -> setOf("app", "tools", "resources", "python", "dependencies", "native", "executable")
            "windows-frozen" -> setOf("executable", "bundle", "native")
            "android" -> setOf("installed_apks", "engine", "native", "abi")
            else -> error("Unknown producer")
        }
        val components = producer.getJSONObject("components")
        require(keys(components).containsAll(required))
        if (producer.getString("kind").startsWith("windows-")) {
            val executable = components.getJSONObject("executable")
            validateManifest(JSONObject().put("executable", executable)); require(executable.getLong("size") > 0)
            val trees = if (producer.getString("kind") == "windows-source") listOf("app", "tools", "resources", "python") else listOf("bundle")
            trees.forEach {
                val tree = components.getJSONObject(it)
                require(keys(tree) == setOf("manifest_key", "files") && tree.getLong("files") > 0)
            }
        } else {
            val apks = components.getJSONObject("installed_apks"); validateManifest(apks)
            require(apks.length() > 0 && keys(apks).all { apks.getJSONObject(it).getLong("size") > 0 })
            require(keys(components.getJSONObject("engine")) == setOf("manifest_sha256", "files_key"))
        }
        fun evidence(item: Any) {
            when (item) {
                is JSONArray -> (0 until item.length()).forEach { evidence(item.get(it)) }
                is JSONObject -> when (keys(item)) {
                    setOf("size", "sha256") -> validateManifest(JSONObject().put("evidence", item))
                    setOf("manifest_key", "files") -> {
                        require(hash.matches(item.getString("manifest_key")))
                        val count = item.get("files")
                        require((count is Int || count is Long) && (count as Number).toLong() in 0..100000L)
                    }
                    setOf("manifest_sha256", "files_key") -> keys(item).forEach { require(hash.matches(item.getString(it))) }
                    setOf("packaged_in_apks") -> require(item.get("packaged_in_apks") == true)
                    else -> keys(item).forEach { evidence(item.get(it)) }
                }
                else -> error("Producer evidence must identify bytes")
            }
        }
        keys(components).forEach { name ->
            if (name == "abi") {
                val abi = components.getJSONArray(name); require(abi.length() > 0)
                (0 until abi.length()).forEach { require(abi.get(it) is String && abi.getString(it).isNotEmpty()) }
            } else evidence(components.get(name))
        }
        if (producer.getString("kind") != "android") require(components.getJSONObject("native").length() > 0)
        canonical(value)
    }

    /** Strict bounded JSON, rejecting duplicate keys before JSONObject can discard them. */
    fun parse(bytes: ByteArray): JSONObject {
        require(bytes.size <= MAX_JSON)
        val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
        var position = 0
        fun whitespace() { while (position < text.length && text[position] in " \t\r\n") position++ }
        fun string(): String {
            val start = position
            require(text[position++] == '"')
            while (position < text.length) {
                val char = text[position++]
                if (char == '"') return org.json.JSONTokener(text.substring(start, position)).nextValue() as String
                require(char.code >= 32)
                if (char == '\\') {
                    require(position < text.length)
                    val escaped = text[position++]
                    require(escaped in "\"\\/bfnrtu")
                    if (escaped == 'u') {
                        require(position + 4 <= text.length && text.substring(position, position + 4).all { it in "0123456789abcdefABCDEF" })
                        position += 4
                    }
                }
            }
            error("Unterminated JSON string")
        }
        fun value(depth: Int): Any {
            require(depth <= 32); whitespace(); require(position < text.length)
            when (text[position]) {
                '{' -> {
                    position++; whitespace(); val result = JSONObject()
                    if (position < text.length && text[position] == '}') { position++; return result }
                    while (true) {
                        whitespace(); require(position < text.length && text[position] == '"')
                        val key = string(); require(!result.has(key)) { "Duplicate JSON key" }
                        whitespace(); require(position < text.length && text[position++] == ':')
                        result.put(key, value(depth + 1)); whitespace(); require(position < text.length)
                        val delimiter = text[position++]
                        if (delimiter == '}') return result
                        require(delimiter == ',')
                    }
                }
                '[' -> {
                    position++; whitespace(); val result = JSONArray()
                    if (position < text.length && text[position] == ']') { position++; return result }
                    while (true) {
                        result.put(value(depth + 1)); whitespace(); require(position < text.length)
                        val delimiter = text[position++]
                        if (delimiter == ']') return result
                        require(delimiter == ',')
                    }
                }
                '"' -> return string()
                else -> {
                    val start = position
                    while (position < text.length && text[position] !in ",]} \t\r\n") position++
                    val token = text.substring(start, position)
                    return when (token) {
                        "true" -> true
                        "false" -> false
                        "null" -> JSONObject.NULL
                        else -> { require(Regex("-?(0|[1-9][0-9]*)").matches(token)); token.toLong() }
                    }
                }
            }
        }
        val result = value(0) as JSONObject
        whitespace(); require(position == text.length); canonical(result)
        return result
    }

    fun verify(root: File, identity: JSONObject? = null, inputKey: String? = null, stage: String? = null): JSONObject {
        val marker = File(root, NAME); safe(marker)
        require(linkCount(marker.toPath()) == 1L)
        val bytes = marker.inputStream().use { stream ->
            val output = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(65536)
            while (output.size() <= MAX_JSON) {
                val count = stream.read(buffer, 0, minOf(buffer.size, MAX_JSON + 1 - output.size()))
                if (count < 0) break
                output.write(buffer, 0, count)
            }
            output.toByteArray()
        }
        val record = parse(bytes)
        require(keys(record) == setOf("schema", "committed", "run_id", "stage", "input_key", "producer_key", "identity", "artifacts", "references"))
        require(schema(record) && record.get("committed") == true)
        require(record.getString("run_id").length in 1..128 && record.getString("stage") in stages)
        val saved = record.getJSONObject("identity"); validateInput(saved)
        require(record.getString("input_key") == identityKey(saved))
        require(record.getString("producer_key") == identityKey(saved.getJSONObject("producer")))
        if (identity != null) { validateInput(identity); require(record.getString("input_key") == identityKey(identity)) }
        if (inputKey != null) require(record.getString("input_key") == inputKey)
        if (stage != null) require(record.getString("stage") == stage)
        val artifacts = record.getJSONObject("artifacts"); validateManifest(artifacts)
        require(artifacts.length() > 0 && !setOf("device_patch_summary.json", "attempt-owner.json").containsAll(keys(artifacts)))
        require(!artifacts.has(NAME))
        val refs = record.getJSONObject("references"); require(keys(refs) == references)
        references.forEach { name -> if (!refs.isNull(name)) require(artifacts.has(relativePath(refs.getString(name)))) }
        val names = references.filter { !refs.isNull(it) }.map { refs.getString(it) }
        require(names.distinct().size == names.size)
        if (record.getString("stage") == "staged") {
            require(!refs.isNull("summary") && !refs.isNull("manifest"))
            val remove = saved.getJSONObject("request").getString("action") == "remove"
            require(refs.isNull("delta") == remove)
            fun metadata(name: String): JSONObject {
                val file = File(root, refs.getString(name)); safe(file)
                require(file.length() <= MAX_JSON)
                return parse(file.readBytes())
            }
            metadata("summary")
            val manifest = metadata("manifest")
            require(keys(manifest) == setOf("schema", "files") && schema(manifest))
            val files = manifest.getJSONObject("files"); validateManifest(files)
            val expected = JSONObject()
            keys(artifacts).filter { it !in names && it != "attempt-owner.json" }
                .forEach { expected.put(it, artifacts.get(it)) }
            require(canonical(files) == canonical(expected) && (remove || expected.length() > 0))
            if (!remove) require(artifacts.getJSONObject(refs.getString("delta")).getLong("size") > 0)
        }
        require(canonical(treeManifest(root, setOf(NAME))) == canonical(artifacts)) { "Artifact bytes/file set changed" }
        return record
    }
}
