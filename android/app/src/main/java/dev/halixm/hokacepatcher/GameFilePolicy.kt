package dev.halixm.hokacepatcher

/** Fixed game-data scope. Snapshot-only metadata is never writable through the patch adapter. */
object GameFilePolicy {
    fun validate(relative: String, writable: Boolean = false) {
        require(relative.length <= 512 && !relative.startsWith("/")) { "Invalid game data path" }
        val parts = relative.split('/')
        require(parts.none { it.isEmpty() || it == "." || it == ".." }) { "Invalid game data path" }
        if (!writable && relative == "packages/builtin/Globalindex/GlobalIndexPrime.data") return
        if (parts.first() == "Watchdog") {
            require(parts.size in 2..5 && parts.drop(1).all {
                it.matches(Regex("[A-Za-z0-9_.-]{1,128}"))
            }) { "Unsupported Watchdog filename" }
            return
        }
        require(parts.size == 3 && parts[0] == "packages") { "Unsupported game data path" }
        val id = parts[1]
        require(id.matches(Regex("[0-9]{1,10}")) && id.toLong() <= 0xFFFFFFFFL) { "Invalid package ID" }
        val database = parts[2].matches(Regex("${Regex.escape(id)}(?:_[0-9]{1,3})?[.]db"))
        require(database || (!writable && parts[2] == "$id.info")) { "Unsupported package filename" }
    }

    fun session(value: String) {
        require(value.matches(Regex("[0-9a-f-]{36}")) &&
            java.util.UUID.fromString(value).toString() == value) { "Invalid patch session" }
    }

    fun watchdogDirectory(relative: String) {
        if (relative == "Watchdog") return
        validate(relative, writable = true)
        require(relative.startsWith("Watchdog/")) { "Only Watchdog directories may be restored" }
    }

    fun parentChecks(relative: String): String {
        validate(relative)
        val parts = relative.split('/')
        val paths = mutableListOf("files", "files/QtsVFSCache")
        var path = "files/QtsVFSCache"
        for (part in parts) {
            path += "/$part"
            paths += path
        }
        return paths.joinToString(" && ") { "[ ! -L '$it' ]" }
    }
}
