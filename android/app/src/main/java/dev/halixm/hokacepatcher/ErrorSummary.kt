package dev.halixm.hokacepatcher

/** The readable head of a raw error: what failed and why, without the stack trace that buries it on screen. */
object ErrorSummary {
    private const val MAX_LINES = 8
    private const val MAX_CHARS = 1000

    // `\tat a.b.C.m(C.java:12)` and `... 3 more`: stack frames, kept in the trace and the copied error.
    private val frame = Regex("(at [^ ]+\\(.*\\)|\\.\\.\\. [0-9]+ more)")
    // ` a.b.C.m:14469 a.b.D.n:4953`: the caller list Android appends to a SecurityException message.
    private val callers = Regex("([\\w.$<>-]+:[0-9]+)( [\\w.$<>-]+:[0-9]+)*")

    fun cause(raw: String): String {
        val lines = raw.lineSequence().map { it.trimEnd() }
            .filter { line -> line.trim().let { it.isNotEmpty() && !frame.matches(it) && !callers.matches(it) } }
            .toList()
        if (lines.isEmpty()) return raw.trim().take(MAX_CHARS)
        val kept = lines.take(MAX_LINES).joinToString("\n")
        return if (lines.size > MAX_LINES || kept.length > MAX_CHARS) kept.take(MAX_CHARS).trimEnd() + "\n…" else kept
    }
}
