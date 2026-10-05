package dev.halixm.hokacepatcher

import android.system.Os
import android.system.OsConstants
import java.io.File

/** Persist directory entries as well as file contents before recording a mutation checkpoint. */
object DurableFiles {
    fun syncDirectory(directory: File) {
        val descriptor = Os.open(directory.path, OsConstants.O_RDONLY, 0)
        try {
            check(OsConstants.S_ISDIR(Os.fstat(descriptor).st_mode)) { "Expected a private directory" }
            Os.fsync(descriptor)
        } finally { Os.close(descriptor) }
    }

    fun createDirectories(directory: File) {
        val missing = mutableListOf<File>()
        var current: File? = directory
        while (current != null && !current.exists()) { missing += current; current = current.parentFile }
        check(directory.isDirectory || directory.mkdirs()) { "Cannot create private durable directory" }
        for (created in missing.asReversed()) {
            syncDirectory(checkNotNull(created.parentFile))
            syncDirectory(created)
        }
    }
}
