package dev.halixm.hokacepatcher

import java.io.DataInputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * The ADB wire protocol the wireless debugging provider speaks to the phone's own `adbd`.
 *
 * Ported from Shizuku's `AdbProtocol.kt` and `AdbMessage.kt` (Copyright RikkaW, Apache-2.0; see
 * `android/native/THIRD_PARTY.md`), which follow AOSP's `adb/protocol.txt`: a 24-byte little-endian
 * header, then the payload.
 */
object AdbProtocol {
    const val A_CNXN = 0x4e584e43
    const val A_AUTH = 0x48545541
    const val A_OPEN = 0x4e45504f
    const val A_OKAY = 0x59414b4f
    const val A_CLSE = 0x45534c43
    const val A_WRTE = 0x45545257
    const val A_STLS = 0x534C5453

    const val A_VERSION = 0x01000000
    const val A_MAXDATA = 4096
    const val A_STLS_VERSION = 0x01000000

    const val ADB_AUTH_TOKEN = 1
    const val ADB_AUTH_SIGNATURE = 2
    const val ADB_AUTH_RSAPUBLICKEY = 3

    const val HEADER_LENGTH = 24
    /** No message this client accepts is larger; `adbd` sends at most its own max payload (1 MiB). */
    const val MAX_PAYLOAD = 1024 * 1024
}

/** One ADB message; [read] refuses a header whose magic or checksum is wrong. */
class AdbMessage(val command: Int, val arg0: Int, val arg1: Int, val data: ByteArray = ByteArray(0)) {
    constructor(command: Int, arg0: Int, arg1: Int, data: String) : this(command, arg0, arg1, "$data\u0000".toByteArray())

    fun toByteArray(): ByteArray = ByteBuffer.allocate(AdbProtocol.HEADER_LENGTH + data.size).order(ByteOrder.LITTLE_ENDIAN)
        .putInt(command).putInt(arg0).putInt(arg1).putInt(data.size).putInt(checksum(data)).putInt(command.inv())
        .put(data).array()

    override fun toString() = "${name(command)}($arg0, $arg1, ${data.size} bytes)"

    companion object {
        fun read(input: DataInputStream): AdbMessage {
            val header = ByteArray(AdbProtocol.HEADER_LENGTH)
            input.readFully(header)
            val buffer = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
            val command = buffer.int
            val arg0 = buffer.int
            val arg1 = buffer.int
            val length = buffer.int
            val crc = buffer.int
            val magic = buffer.int
            if (magic != command.inv()) throw IOException("Bad ADB message magic for ${name(command)}")
            if (length < 0 || length > AdbProtocol.MAX_PAYLOAD) throw IOException("Bad ADB payload size $length")
            val data = ByteArray(length)
            input.readFully(data)
            // adbd stopped filling the checksum in version 0x01000001; zero means none.
            if (crc != 0 && crc != checksum(data)) throw IOException("Bad ADB payload checksum for ${name(command)}")
            return AdbMessage(command, arg0, arg1, data)
        }

        /** The sum of the payload's unsigned bytes. */
        fun checksum(data: ByteArray): Int = data.sumOf { it.toInt() and 0xff }

        fun name(command: Int) = when (command) {
            AdbProtocol.A_CNXN -> "CNXN"; AdbProtocol.A_AUTH -> "AUTH"; AdbProtocol.A_OPEN -> "OPEN"
            AdbProtocol.A_OKAY -> "OKAY"; AdbProtocol.A_CLSE -> "CLSE"; AdbProtocol.A_WRTE -> "WRTE"
            AdbProtocol.A_STLS -> "STLS"; else -> "0x%08x".format(command)
        }
    }
}
