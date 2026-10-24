package dev.halixm.hokacepatcher

/**
 * Fixed private lock; explicit descriptor redirections preserve it across Android mksh execs.
 *
 * Every locked script may call `own <path>…` on what it creates. Under `run-as` it does nothing: the files
 * are the game's already. Under root it gives them the game's owner and SELinux label, copied from
 * `files/QtsVFSCache`, and the umask matches `run-as`'s, so either provider leaves the same files (ADR 0007).
 */
object GameFileLock {
    private const val SHELL_OWN = "own() { :; }; "
    private const val ROOT_OWN = "umask 000; o=\$(stat -c %u:%g files/QtsVFSCache) && c=\$(stat -c %C files/QtsVFSCache) || exit 1; " +
        "case \"\$o\" in 0:*|*:0) echo 'Game files owned by root' >&2; exit 1;; esac; " +
        "own() { chown \"\$o\" \"\$@\" && chcon \"\$c\" \"\$@\"; }; "

    @JvmOverloads fun script(body: String, root: Boolean = false): String {
        val lock = "files/QtsVFSCache/.hok-ace-patcher.lock"
        val prologue = if (root) ROOT_OWN else SHELL_OWN
        val quoted = "'" + (prologue + body).replace("'", "'\\''") + "'"
        return "[ ! -L files ] && [ ! -L files/QtsVFSCache ] && [ ! -L '$lock' ] || exit 1; " +
            "{ [ ! -e '$lock' ] || [ -f '$lock' ]; } || exit 1; " + prologue +
            "exec 9>> '$lock' || exit 1; own '$lock' || exit 1; /system/bin/flock -x 9 9>&9 || exit 1; " +
            "exec /system/bin/sh -c $quoted 9>&9"
    }
}
