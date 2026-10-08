package dev.halixm.hokacepatcher

import android.content.Context
import org.json.JSONObject

/** Presentation-only translations. Action keys, engine messages and diagnostic exports stay stable. */
object UiText {
    private val indonesian = mapOf(
        "Free now:" to "Ruang tersedia:",
        "Saved APK" to "APK tersimpan",
        "Interrupted run" to "Proses terhenti",
        "Let's get started" to "Mari mulai",
        "Start Shizuku, then come back here." to "Jalankan Shizuku, lalu kembali ke sini.",
        "Start" to "Mulai",
        "Stop safely" to "Hentikan dengan aman",
        "Patching activity" to "Aktivitas patch",
        "New messages appear here as we work. Scroll to see earlier messages." to "Pesan baru muncul selama proses. Gulir untuk melihat pesan sebelumnya.",
        "Restore interrupted patch" to "Pulihkan patch yang terhenti",
        "Finish or repair first setup" to "Selesaikan atau perbaiki penyiapan awal",
        "Reinstall saved game app" to "Pasang ulang aplikasi game tersimpan",
        "After reinstalling, check the game app below. Unfinished file changes still need recovery." to "Setelah memasang ulang, periksa aplikasi game di bawah. Perubahan file yang belum selesai tetap perlu dipulihkan.",
        "Check restored game app" to "Periksa aplikasi game yang dipulihkan",
        "Save log for help" to "Simpan log untuk bantuan",
        "01  /  YOUR TRANSLATION" to "01  /  BAHASA PILIHAN",
        "Language" to "Bahasa",
        "Switching languages? Clear the game's data and download it again first." to "Mengganti bahasa? Hapus data game dan unduh ulang terlebih dahulu.",
        "02  /  READY TO PLAY" to "02  /  SIAP BERMAIN",
        "Game won't open?" to "Game tidak bisa dibuka?",
        "Keep the game closed. Use recovery first." to "Jangan buka game. Pulihkan terlebih dahulu.",
        "Show recovery options" to "Tampilkan pilihan pemulihan",
        "Technical tools" to "Alat teknis",
        "For testing or support" to "Untuk pengujian atau bantuan",
        "COMMUNITY PATCHER  /  HOK ACE" to "PATCHER KOMUNITAS  /  HOK ACE",
        "Your next move. Your language." to "Langkah berikutnya. Bahasa pilihanmu.",
        "Some game text will stay Chinese.\nUse Scan to login after setup." to "Sebagian teks game tetap berbahasa Mandarin.\nGunakan Scan to login setelah penyiapan.",
        "Stop safely?" to "Hentikan dengan aman?",
        "Keep the game closed. Any unfinished changes must be restored before you open it." to "Jangan buka game. Semua perubahan yang belum selesai harus dipulihkan sebelum game dibuka.",
        "Keep going" to "Lanjutkan",
        "Stop and recover" to "Hentikan dan pulihkan",
        "Access was not allowed. Tap Start to try again." to "Akses tidak diizinkan. Ketuk Mulai untuk mencoba lagi.",
        "The game is not installed. Install it before preparing files." to "Game belum terpasang. Pasang game sebelum menyiapkan file.",
        "Cannot open Shizuku or Google Play. Install Shizuku from play.google.com, start it, then return here." to "Shizuku atau Google Play tidak bisa dibuka. Pasang Shizuku dari play.google.com, jalankan, lalu kembali ke sini.",
        "More than one unfinished run was found. Choose the correct run in recovery options." to "Ada lebih dari satu proses yang belum selesai. Pilih proses yang sesuai di pilihan pemulihan.",
        "Saved progress cannot be read. Keep the game closed and save a log for help." to "Progres tersimpan tidak bisa dibaca. Jangan buka game dan simpan log untuk bantuan.",
        "Work could not start. Check Shizuku, then tap Start again." to "Proses tidak bisa dimulai. Periksa Shizuku, lalu ketuk Mulai lagi.",
        "Work was interrupted. Tap Start to check and restore unfinished work." to "Proses terhenti. Ketuk Mulai untuk memeriksa dan memulihkan proses yang belum selesai.",
        "Working on your game" to "Sedang memproses game",
        "Checking and preparing files…" to "Memeriksa dan menyiapkan file…",
        "Please wait" to "Mohon tunggu",
        "Checking game files" to "Memeriksa file game",
        "Please wait. We are checking the saved game app and recovery files." to "Mohon tunggu. Aplikasi game tersimpan dan file pemulihan sedang diperiksa.",
        "Recovery needs attention" to "Pemulihan perlu ditangani",
        "Keep the game closed. Save a log for help." to "Jangan buka game. Simpan log untuk bantuan.",
        "Start Shizuku" to "Jalankan Shizuku",
        "Shizuku must be running. Start it, then return here. We will continue automatically." to "Shizuku harus berjalan. Jalankan, lalu kembali ke sini. Proses akan dilanjutkan otomatis.",
        "Open Shizuku" to "Buka Shizuku",
        "Install Shizuku" to "Pasang Shizuku",
        "Shizuku is required. Install it from Google Play, start it, then return here." to "Shizuku diperlukan. Pasang dari Google Play, jalankan, lalu kembali ke sini.",
        "Get Shizuku" to "Unduh Shizuku",
        "Translation added" to "Terjemahan diterapkan",
        "Start another patch" to "Mulai patch lagi",
        "Work stopped" to "Proses terhenti",
        "Try again" to "Coba lagi",
        "Finish your game safely" to "Selesaikan dengan aman",
        "We will check unfinished work and recover it before patching." to "Proses yang belum selesai akan diperiksa dan dipulihkan sebelum memasang patch.",
        "Continue" to "Lanjutkan",
        "Ready when you are" to "Siap dimulai",
        "Tap Start. We will check your game and prepare everything. Keep the game closed while we work." to "Ketuk Mulai. Game akan diperiksa dan semua file disiapkan. Jangan buka game selama proses.",
        "Shizuku is running, but the patcher's helper did not start. Open Shizuku, stop it and start it again, then return here and tap Try again. If it happens again, save a log for help. Keep the game closed." to "Shizuku berjalan, tetapi layanan pendukung patcher tidak mulai. Buka Shizuku, hentikan lalu jalankan lagi, kemudian kembali ke sini dan ketuk Coba lagi. Jika terulang, simpan log untuk bantuan. Jangan buka game.",
        "Open Shizuku. Start it and allow HOK ACE. Return here and retry. Keep the game closed." to "Buka dan jalankan Shizuku, lalu izinkan HOK ACE. Kembali ke sini dan coba lagi. Jangan buka game.",
        "The phone blocked installation. Unlock it and accept the install prompt. Open Technical tools for the full error." to "Ponsel memblokir pemasangan. Buka kunci dan setujui permintaan pemasangan. Buka Alat teknis untuk melihat galat lengkap.",
        "Work stopped. Keep the game closed. Check recovery options below, or save a log for help." to "Proses terhenti. Jangan buka game. Periksa pilihan pemulihan di bawah atau simpan log untuk bantuan.",
        "The phone did not report how much more space is needed. Free space elsewhere and retry. Keep saved recovery files." to "Ponsel tidak melaporkan tambahan ruang yang diperlukan. Kosongkan ruang lain lalu coba lagi. Simpan file pemulihan.",
        "Choose prepared game files" to "Pilih file game yang sudah disiapkan",
        "Choose game files for first setup" to "Pilih file game untuk penyiapan awal",
        "Cancel" to "Batal",
        "I accept deletion of the game's local data" to "Saya menyetujui penghapusan data lokal game",
        "I will use Scan to login" to "Saya akan menggunakan Scan to login",
        "First setup deletes local game data" to "Penyiapan awal menghapus data lokal game",
        "Delete data and set up" to "Hapus data dan siapkan",
        "Recover or finish game setup" to "Pulihkan atau selesaikan penyiapan game",
        "Recover game installation" to "Pulihkan pemasangan game",
        "Recover" to "Pulihkan",
        "Check the installed app and restore the verified normal game app if it is absent. Recovery will not repeat removal. Deleted local game data cannot be restored by this step." to "Periksa aplikasi terpasang dan pulihkan aplikasi game normal yang terverifikasi jika tidak ada. Pemulihan tidak akan menghapus ulang. Langkah ini tidak bisa memulihkan data lokal yang sudah dihapus.",
        "Every fresh game update finished, and I closed the game" to "Semua pembaruan game yang baru diunduh sudah selesai dan game sudah saya tutup",
        "Finish game setup" to "Selesaikan penyiapan game",
        "Open game" to "Buka game",
        "The game cannot be opened. Use recovery." to "Game tidak bisa dibuka. Gunakan pemulihan.",
        "Confirm updates" to "Konfirmasi pembaruan",
        "All in-game updates finished, and I closed the game" to "Semua pembaruan dalam game sudah selesai dan game sudah saya tutup",
        "Start translation" to "Mulai penerjemahan",
        "Start patch" to "Mulai patch",
        "Recover interrupted patch" to "Pulihkan patch yang terhenti",
        "Choose emergency normal APK" to "Pilih APK normal untuk pemulihan darurat",
        "Restore normal game APK" to "Pulihkan APK game normal",
        "Open installer" to "Buka pemasang",
        "Authorize Shizuku" to "Izinkan Shizuku",
        "Check Python and codecs" to "Periksa Python dan codec",
        "Prepare game files (no installation)" to "Siapkan file game (tanpa pemasangan)",
        "First setup (deletes local game data)" to "Penyiapan awal (menghapus data lokal game)",
        "Patch after the game update finishes" to "Pasang patch setelah pembaruan game selesai",
        "Check shell and game APK path" to "Periksa shell dan lokasi APK game",
        "Copy and verify installed APK (about 2 GB)" to "Salin dan periksa APK terpasang (sekitar 2 GB)",
        "Round-trip disposable fixture" to "Uji baca/tulis data uji sementara",
        "Force-stop game" to "Paksa berhenti game",
        "Verify retained normal recovery APK" to "Periksa APK pemulihan normal tersimpan",
        "Emergency normal APK installer" to "Pemasang APK normal darurat",
        "Verify installed normal APK with foreground worker" to "Periksa APK normal terpasang dengan proses latar depan",
        "Read worker result" to "Baca hasil proses",
        "Export diagnostic logs" to "Ekspor log diagnostik",
        "Prepare game files first" to "Siapkan file game terlebih dahulu",
        "No pending game setup" to "Tidak ada penyiapan game yang tertunda",
        "No interrupted patch to recover" to "Tidak ada patch terhenti yang perlu dipulihkan",
        "Preparing verified recovery material" to "Menyiapkan file pemulihan terverifikasi",
        "Checking the installed normal game app" to "Memeriksa aplikasi game normal yang terpasang",
        "Game patch progress" to "Progres patch game",
        "Cancel preparation" to "Batalkan persiapan",
        "Stop after safe installation" to "Hentikan setelah pemasangan aman",
        "Cancel and recover" to "Batalkan dan pulihkan"
    )

    fun text(context: Context, source: String): String = translate(PatchLanguage.current(context), source)

    /** Exact matches only: never alter paths, hashes, action keys or raw diagnostic messages. */
    fun translate(code: String, source: String): String = if (code == "id") indonesian[source] ?: source else source

    fun progress(context: Context, source: String): String {
        if (PatchLanguage.current(context) != "id") return source
        return indonesian[source] ?: "Sedang memproses file game. Lihat rincian di log di bawah."
    }

    /** Translate only the measured storage summary, preserving its conservative GB numbers. */
    fun storage(context: Context, source: String): String {
        if (PatchLanguage.current(context) != "id") return source
        val shortage = Regex("Need ([0-9.]+) GB free for this step.\\nFree now: ([0-9.]+) GB.\\nClear at least ([0-9.]+) GB more, then try again.\\nKeep saved recovery files.").matchEntire(source)
        if (shortage != null) {
            val (need, free, more) = shortage.destructured
            return "Langkah ini memerlukan $need GB ruang kosong.\nTersedia: $free GB.\n" +
                "Kosongkan setidaknya $more GB lagi, lalu coba lagi.\nSimpan file pemulihan."
        }
        val enough = Regex("Enough space now for this step.\\nNeeded: ([0-9.]+) GB free \\(rounded up\\).\\nTap Try again. Keep saved recovery files.").matchEntire(source)
        if (enough != null) return "Ruang sekarang cukup untuk langkah ini.\nDiperlukan: ${enough.groupValues[1]} GB (dibulatkan ke atas).\nKetuk Coba lagi. Simpan file pemulihan."
        return source
    }

    fun completed(context: Context, state: JSONObject): String {
        if (PatchLanguage.current(context) != "id") return WorkerStatus.describe(state)
        val counts = state.optJSONObject("counts") ?: return "Patch selesai. Aplikasi game normal terverifikasi; jumlah hasil tidak tersedia."
        return "Patch selesai. Aplikasi game normal terverifikasi.\n" +
            "Tabel teks diterapkan: ${counts.getInt("text_tables")}\n" +
            "Gambar diterapkan: ${counts.getInt("applied_textures")}\n" +
            "Tabel teks dilewati: ${counts.getInt("skipped_tables")}\n" +
            "Gambar dilewati: ${counts.getInt("skipped_textures")}"
    }

    fun firstSetup(context: Context): String = if (PatchLanguage.current(context) == "id")
        "1. Data game, unduhan, dan login tersimpan di ponsel ini akan dihapus.\n\n" +
        "2. Unduh ulang semua pembaruan game.\n\n3. Login langsung WeChat/QQ tidak akan berfungsi. Gunakan Scan to login.\n\n" +
        "4. Terjemahan ditambahkan setelah Anda mengonfirmasi unduhan selesai.\n\nPenyiapan awal belum lulus semua pengujian ponsel."
    else "1. This deletes saved game data, downloads and login on this phone.\n\n" +
        "2. Download all game updates again.\n\n3. Direct WeChat/QQ login stops working. Use Scan to login.\n\n" +
        "4. Translation is added later, after you confirm that downloads finished.\n\nFirst setup has not passed all phone tests."

    fun setupUpdate(context: Context): String = if (PatchLanguage.current(context) == "id")
        "Buka game, selesaikan semua unduhan, lalu tutup game. File baru akan disiapkan otomatis. " +
        "Terjemahan dimulai setelah konfirmasi pembaruan terakhir."
    else "Open the game, complete all downloads, then close it. We will then prepare the new files automatically. " +
        "Translation starts after the final update confirmation."

    fun patchConfirmation(context: Context): String {
        val language = PatchLanguage.name(PatchLanguage.current(context))
        return if (PatchLanguage.current(context) == "id")
            "1. Selesaikan SEMUA unduhan dalam game.\n2. Tutup game.\n\n" +
            "3. Kami akan mengubah file game dan mengganti aplikasi game untuk sementara.\n\n" +
            "4. JANGAN BUKA game sampai proses atau pemulihan selesai.\n\nBahasa: $language\n\n" +
            "Penerapan terjemahan belum lulus semua pengujian ponsel."
        else "1. Finish ALL downloads in the game.\n2. Close the game.\n\n" +
            "3. We change game files and briefly replace the game app.\n\n" +
            "4. Keep the game CLOSED until work or recovery finishes.\n\nLanguage: $language\n\n" +
            "Adding the translation has not passed all phone tests."
    }

    fun restore(context: Context, version: String): String = if (PatchLanguage.current(context) == "id")
        "Pulihkan versi $version tanpa menghapus data. Ini hanya memulihkan APK. " +
        "Penulisan paket yang belum selesai masih harus dipulihkan sebelum game dibuka. " +
        "Membuka pemasang tidak berarti pemulihan sudah terverifikasi."
    else "Restore version $version with data retained. This restores the APK only. " +
        "Unresolved package writes still require rollback before launching the game. " +
        "Opening the installer does not verify a completed restoration."
}
