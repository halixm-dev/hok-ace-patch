package dev.halixm.hokacepatcher

/** Refuse ambiguous user/package listings before the fixed game's irreversible removal. */
object FirstSetupPackagePolicy {
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
}
