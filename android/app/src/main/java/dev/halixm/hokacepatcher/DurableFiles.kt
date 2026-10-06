package dev.halixm.hokacepatcher

import android.system.Os
import android.system.OsConstants
import java.io.File
import java.io.IOException
import java.nio.file.FileVisitResult
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.SimpleFileVisitor
import java.nio.file.attribute.BasicFileAttributes

/** Persist directory entries as well as file contents before recording a mutation checkpoint. */
object DurableFiles {
    fun syncDirectory(directory: File) {
        val descriptor = Os.open(directory.path, OsConstants.O_RDONLY, 0)
        try {
            check(OsConstants.S_ISDIR(Os.fstat(descriptor).st_mode)) { "Expected a private directory" }
            Os.fsync(descriptor)
        } finally { Os.close(descriptor) }
    }

    /** Delete <path> without following links; returns the bytes this actually frees. */
    fun deleteTree(path: File): Long {
        val start = path.toPath()
        if (!Files.exists(start, LinkOption.NOFOLLOW_LINKS)) return 0L
        var freed = 0L
        Files.walkFileTree(start, object : SimpleFileVisitor<Path>() {
            override fun visitFile(file: Path, attributes: BasicFileAttributes): FileVisitResult {
                if (attributes.isRegularFile && Os.lstat(file.toString()).st_nlink == 1L) freed += attributes.size()
                Files.delete(file)
                return FileVisitResult.CONTINUE
            }
            override fun postVisitDirectory(directory: Path, error: IOException?): FileVisitResult {
                if (error != null) throw error
                Files.delete(directory)
                return FileVisitResult.CONTINUE
            }
        })
        return freed
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
