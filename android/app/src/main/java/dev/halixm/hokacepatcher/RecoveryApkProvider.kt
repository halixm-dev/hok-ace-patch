package dev.halixm.hokacepatcher

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import java.io.File

/** Grant read access only to immutable verified normal recovery APKs, never access APKs or keys. */
class RecoveryApkProvider : ContentProvider() {
    override fun onCreate(): Boolean = true

    private fun file(uri: Uri, verifyContent: Boolean = false): File {
        check(uri.authority == "${checkNotNull(context).packageName}.recovery") { "Unsupported recovery authority" }
        val parts = uri.pathSegments
        require(parts.size == 2 && parts[0].matches(Regex("[0-9a-f]{64}")) && parts[1] == "normal.apk") {
            "Unsupported recovery URI"
        }
        val store = RecoveryStore(checkNotNull(context))
        val expected = if (verifyContent) store.verify(parts[0]) else store.expected(parts[0])
        return store.normal(parts[0]).also {
            check(it.isFile && it.length() == expected.bytes) { "Recovery file differs" }
        }
    }

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        require(mode == "r") { "Recovery material is read-only" }
        return ParcelFileDescriptor.open(file(uri, verifyContent = true), ParcelFileDescriptor.MODE_READ_ONLY)
    }

    override fun getType(uri: Uri): String { file(uri); return "application/vnd.android.package-archive" }

    override fun query(uri: Uri, projection: Array<out String>?, selection: String?,
                       selectionArgs: Array<out String>?, sortOrder: String?): Cursor {
        val apk = file(uri)
        val columns = projection ?: arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)
        require(columns.all { it == OpenableColumns.DISPLAY_NAME || it == OpenableColumns.SIZE })
        return MatrixCursor(columns).apply {
            addRow(columns.map { if (it == OpenableColumns.DISPLAY_NAME) "HOK-ACE-normal-recovery.apk" else apk.length() })
        }
    }

    override fun insert(uri: Uri, values: ContentValues?): Uri? = throw UnsupportedOperationException()
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int =
        throw UnsupportedOperationException()
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int =
        throw UnsupportedOperationException()
}
