package dev.halixm.hokacepatcher

import org.json.JSONObject

/** Bounded before/after/explicit-absence states, checked again inside each mutation's game lock. */
object RecoveryFilePolicy {
    fun parse(value: JSONObject): JSONObject {
        check(value.keys().asSequence().toSet() == setOf("schema", "watchdog_absent", "files") && (value.get("schema") is Int || value.get("schema") is Long) && value.getInt("schema") == 1)
        check(value.get("watchdog_absent") is Boolean)
        val files = value.getJSONObject("files")
        check(files.length() in 1..8192)
        for (name in files.keys()) {
            GameFilePolicy.validate(name)
            val item = files.getJSONObject(name)
            check(item.keys().asSequence().toSet() == setOf("absent", "states"))
            check(item.get("absent") is Boolean)
            val states = item.getJSONArray("states")
            check(states.length() in 0..2 && (states.length() > 0 || item.getBoolean("absent")))
            for (i in 0 until states.length()) {
                val state = states.getJSONObject(i)
                check(state.keys().asSequence().toSet() == setOf("sha256", "bytes"))
                check(state.get("sha256") is String && state.getString("sha256").matches(Regex("[0-9a-f]{64}")))
                check((state.get("bytes") is Int || state.get("bytes") is Long) && state.getLong("bytes") in 0..(3L * 1024 * 1024 * 1024))
            }
        }
        return files
    }

    fun rows(files: JSONObject, watchdog: Boolean): ByteArray = files.keys().asSequence()
        .filter { !watchdog || it.startsWith("Watchdog/") }.sorted().joinToString("\n", postfix = "\n") { name ->
            val entry = files.getJSONObject(name); val states = entry.getJSONArray("states")
            fun field(index: Int, key: String): String = states.optJSONObject(index)?.get(key)?.toString() ?: "-"
            "$name ${if (entry.getBoolean("absent")) 1 else 0} ${field(0, "sha256")} ${field(0, "bytes")} ${field(1, "sha256")} ${field(1, "bytes")}"
        }.let { if (it == "\n") ByteArray(0) else it.toByteArray(Charsets.UTF_8) }

    /** Invoked from files/QtsVFSCache. No path or hash from this schema permits shell metacharacters. */
    fun script(files: JSONObject, only: String? = null, watchdog: Boolean = false, watchdogAbsent: Boolean = false): String {
        val names = files.keys().asSequence().filter { only == null || it == only }
            .filter { !watchdog || it.startsWith("Watchdog/") }.sorted().toList()
        if (only != null) check(files.has(only)) { "Target is outside recovery plan" }
        val body = StringBuilder("[ ! -L packages ] && [ ! -L Watchdog ] || exit 1; ")
        if (only == null) {
            val roots = "\$roots"
            val rootSetup = if (watchdog) "roots=''; " else "[ -d packages ] || exit 1; roots=packages; "
            val missing = if (watchdogAbsent) ":" else "exit 1"
            return "[ ! -L packages ] && [ ! -L Watchdog ] || exit 1; " + rootSetup +
                "if [ -d Watchdog ]; then roots=\"\$roots Watchdog\"; else $missing; fi; " +

                "links=''; if [ -n \"\$roots\" ]; then links=\$(find $roots -type l -print) || exit 1; fi; [ -z \"\$links\" ] || exit 1; " +
                "present=0; while read -r path absent h1 n1 h2 n2; do " +
                "if [ -e \"\$path\" ]; then [ -f \"\$path\" ] || exit 1; " +
                "h=\$(sha256sum \"\$path\") || exit 1; h=\${h%% *}; n=\$(stat -c %s \"\$path\") || exit 1; " +
                "{ [ \"\$h\" = \"\$h1\" ] && [ \"\$n\" = \"\$n1\" ]; } || " +
                "{ [ \"\$h\" = \"\$h2\" ] && [ \"\$n\" = \"\$n2\" ]; } || { echo 'Unexpected live bytes' >&2; exit 1; }; " +
                "present=\$((present + 1)); else [ \"\$absent\" = 1 ] || { echo 'Unexpected missing file' >&2; exit 1; }; fi; done; " +
                "actual=0; if [ -n \"\$roots\" ]; then actual=\$(find $roots -type f -exec echo x \\; | wc -l); fi; " +
                "[ \"\$actual\" -eq \"\$present\" ] || { echo 'Unexpected live file set' >&2; exit 1; }; "
        }
        for (name in names) {
            val item = files.getJSONObject(name)
            val states = item.getJSONArray("states")
            body.append("[ ! -L '$name' ] || exit 1; if [ -e '$name' ]; then [ -f '$name' ] || exit 1; ")
            body.append("h=\$(sha256sum '$name') || exit 1; h=\${h%% *}; n=\$(stat -c %s '$name') || exit 1; ")
            val checks = (0 until states.length()).joinToString(" || ") { i ->
                val s = states.getJSONObject(i)
                "{ [ \"\$h\" = '${s.getString("sha256")}' ] && [ \"\$n\" -eq ${s.getLong("bytes")} ]; }"
            }.ifEmpty { "false" }
            body.append("$checks || { echo 'Unexpected live bytes: $name' >&2; exit 1; }; else ")
            body.append(if (item.getBoolean("absent")) ":; " else "echo 'Unexpected missing file: $name' >&2; exit 1; ")
            body.append("fi; ")
        }
        return body.toString()
    }
}
