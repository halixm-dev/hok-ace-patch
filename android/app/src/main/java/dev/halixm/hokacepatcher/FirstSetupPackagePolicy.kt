package dev.halixm.hokacepatcher

/** Refuse ambiguous user/package listings before the fixed game's irreversible removal. */
object FirstSetupPackagePolicy {
    /** Lines `profileStates` reads; the service filters `dumpsys package` to these so the dump stays bounded. */
    const val DUMPSYS_FILTER = "^[[:space:]]*(Package \\[|User [0-9]+: .*installed=)"

    /** Fixed refusal texts. The UI matches on them, so keep them free of "Shizuku" and "permission". */
    const val OTHER_PROFILE = "The game is installed in another Android profile"
    const val UNCHECKED_PROFILE = "Cannot check another Android profile for the game"

    fun users(output: String): List<Int> {
        val lines = output.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.toList()
        check(lines.firstOrNull() == "Users:") { "Cannot verify Android user profiles" }
        val ids = lines.drop(1).map { line ->
            val match = Regex("UserInfo\\{([0-9]+):.*\\}(?: running)?").matchEntire(line)
                ?: error("Unsupported Android user listing")
            match.groupValues[1].toInt()
        }
        check(ids.isNotEmpty() && 0 in ids && ids.distinct().size == ids.size)
        return ids
    }

    fun containsGame(output: String): Boolean = containsPackage(output, PrivilegedDeviceService.GAME)

    fun containsPackage(output: String, target: String): Boolean {
        require(target in setOf(PrivilegedDeviceService.GAME, PrivilegedDeviceService.FIXTURE))
        val lines = output.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.toList()
        check(lines.all { it.matches(Regex("package:[a-zA-Z0-9_]+(?:\\.[a-zA-Z0-9_]+)+")) }) {
            "Cannot verify installed game packages"
        }
        return "package:$target" in lines
    }

    /**
     * True when `pm list packages --user <user>` failed only because shell may not enter that profile.
     * Some ROMs (Infinix XOS's Dual App user 999) refuse shell there although `pm list users` names it.
     */
    fun profileDenied(error: String, user: Int): Boolean =
        error.contains("SecurityException") &&
            Regex("does not have permission to access user $user(?![0-9])").containsMatchIn(error)

    /** Why the main user cannot see an installed game; read back from [userStates] inside an error message. */
    enum class Missing { HIDDEN, OTHER_PROFILE_ONLY, ABSENT }

    private val userLine = Regex("^\\s*User ([0-9]+): (.*)$")
    private val stateField = Regex("\\b(installed|hidden|suspended|enabled)=([^ ;)]+)")

    /** `user N: installed=.. hidden=.. suspended=.. enabled=..` per `User N:` line of a filtered dump, for error text. */
    fun userStates(output: String): String {
        val users = output.lineSequence().mapNotNull { line ->
            val user = userLine.find(line) ?: return@mapNotNull null
            "user ${user.groupValues[1]}: " + stateField.findAll(user.groupValues[2]).joinToString(" ") { it.value }
        }.toList()
        return if (users.isEmpty()) "no package record" else users.joinToString("; ")
    }

    /**
     * Classify a [userStates] summary. Hidden (or disabled until used, `enabled=4`) packages are filtered out of
     * `pm path` and app lookups exactly like absent ones, which is how an installed game reads as missing.
     */
    fun missingReason(summary: String): Missing {
        val users = Regex("user ([0-9]+): ([^;)]*)").findAll(summary).associate { match ->
            match.groupValues[1].toInt() to stateField.findAll(match.groupValues[2]).associate { it.groupValues[1] to it.groupValues[2] }
        }
        val main = users[0]
        return when {
            main?.get("installed") == "true" && (main["hidden"] == "true" || main["enabled"] == "4") -> Missing.HIDDEN
            users.any { (id, fields) -> id != 0 && fields["installed"] == "true" } -> Missing.OTHER_PROFILE_ONLY
            else -> Missing.ABSENT
        }
    }

    /**
     * Per-profile install state from `dumpsys package <target>` filtered by [DUMPSYS_FILTER], or null
     * when the dump has no record of the package. system_server writes it, so it covers profiles shell
     * itself cannot list. Any line outside the expected shape fails rather than being read as absence.
     */
    fun profileStates(output: String, target: String): Map<Int, Boolean>? {
        require(target in setOf(PrivilegedDeviceService.GAME, PrivilegedDeviceService.FIXTURE))
        val states = mutableMapOf<Int, Boolean>()
        var recorded = false
        output.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.forEach { line ->
            val header = Regex("Package \\[([^\\]]+)\\] \\([0-9a-f]+\\):").matchEntire(line)
            if (header != null) {
                check(header.groupValues[1] == target) { "Unexpected package in profile listing" }
                recorded = true
                return@forEach
            }
            val user = Regex("User ([0-9]+): .*\\binstalled=(true|false)\\b.*").matchEntire(line)
                ?: error("Unsupported package profile listing")
            check(recorded) { "Profile state outside the package record" }
            val id = user.groupValues[1].toInt()
            val installed = user.groupValues[2] == "true"
            check((states.put(id, installed) ?: installed) == installed) { "Conflicting profile install states" }
        }
        return if (recorded) states else null
    }
}
