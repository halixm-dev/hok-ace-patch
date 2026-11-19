package dev.halixm.hokacepatcher

import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import java.io.File

// The emergency normal APK installer and the recovery APK it picks, moved verbatim from MainActivity
// (tech-debt ticket 02).

internal fun MainActivity.recoveryId(): String {
    EmergencyRestoreStore(this).snapshot()?.takeIf {
        it.getString("status") == "verification_pending"
    }?.let { return it.getString("normal") }
    val pending = SessionJournal.pending(File(filesDir, "sessions")).map { it.recoveryId }.distinct()
    val setupPending = FirstSetupJournal.pending(this).map { it.normal.sha256 }
    if (pending.isNotEmpty() || setupPending.isNotEmpty()) return (pending + setupPending).distinct().single()
    return File(filesDir, "recovery").listFiles().orEmpty().filter {
        it.isDirectory && it.name.matches(Regex("[0-9a-f]{64}"))
    }.maxByOrNull { it.lastModified() }?.name ?: error("No verified normal recovery APK retained")
}

internal fun MainActivity.openRecoveryInstaller() {
    val choices = EmergencyRecoveryChoices(this).resolve { recoveryId() }
    if (choices.needsSelection) {
        log("Recovery records cannot be read. Choose a retained APK; game-data recovery remains unresolved.")
        runOnUiThread {
            AlertDialog.Builder(this).setTitle(ui("Choose emergency normal APK"))
                .setItems(choices.ids.map { ui("Saved APK") + " " + it.take(12) }.toTypedArray()) { _, index ->
                    runTask { openRecoveryInstaller(choices.ids[index]) }
                }.setNegativeButton(ui("Cancel"), null).show()
        }
    } else openRecoveryInstaller(choices.ids.single())
}

internal fun MainActivity.openRecoveryInstaller(id: String) {
    val identity = RecoveryStore(this).verify(id)
    val uri = Uri.parse("content://$packageName.recovery/$id/normal.apk")
    runOnUiThread {
        AlertDialog.Builder(this).setTitle(ui("Restore normal game APK"))
            .setMessage(UiText.restore(this, identity.versionName))
            .setNegativeButton(ui("Cancel"), null)
            .setPositiveButton(ui("Open installer")) { _, _ ->
                if (!packageManager.canRequestPackageInstalls()) {
                    log("Allow this app to install APKs, then press Emergency normal APK installer again.")
                    startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:$packageName")))
                } else {
                    runCatching {
                        EmergencyRestoreStore(this).begin(id)
                        startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri,
                            "application/vnd.android.package-archive")
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                    }.onSuccess { log("Normal APK installer opened; restoration remains unverified.") }
                        .onFailure { log("Cannot open normal APK installer: ${it.message}. Restoration remains unverified.") }
                }
            }.show()
    }
}
