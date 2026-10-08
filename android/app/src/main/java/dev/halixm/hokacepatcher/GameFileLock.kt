package dev.halixm.hokacepatcher

/** Fixed private lock; explicit descriptor redirections preserve it across Android mksh execs. */
object GameFileLock {
    fun script(body: String): String {
        val lock = "files/QtsVFSCache/.hok-ace-patcher.lock"
        val quoted = "'" + body.replace("'", "'\\''") + "'"
        return "[ ! -L files ] && [ ! -L files/QtsVFSCache ] && [ ! -L '$lock' ] || exit 1; " +
            "{ [ ! -e '$lock' ] || [ -f '$lock' ]; } || exit 1; " +
            "exec 9>> '$lock' || exit 1; /system/bin/flock -x 9 9>&9 || exit 1; " +
            "exec /system/bin/sh -c $quoted 9>&9"
    }
}
