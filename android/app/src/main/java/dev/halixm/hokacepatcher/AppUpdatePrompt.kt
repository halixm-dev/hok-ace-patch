package dev.halixm.hokacepatcher

import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import java.util.concurrent.Executors

/**
 * The Check for updates action and its dialogs, with the state only it uses: moved verbatim from MainActivity
 * (tech-debt ticket 02). [checkAppUpdate] runs in the activity's scope, so its body reads as it did there.
 */
internal class AppUpdatePrompt(private val activity: MainActivity) {
    private val updateWorker = Executors.newSingleThreadExecutor()
    private var checkingUpdate = false
    private var updateDialog: AlertDialog? = null

    fun checkAppUpdate(): Unit = with(activity) {
        if (checkingUpdate || destroyed) return
        checkingUpdate = true
        home.checkingUpdate(true)
        updateWorker.execute {
            val result = AppUpdateChecker().check(BuildConfig.VERSION_NAME)
            runOnUiThread {
                if (destroyed || isFinishing) return@runOnUiThread
                checkingUpdate = false
                home.checkingUpdate(false)
                updateDialog?.dismiss()
                val dialog = AlertDialog.Builder(this).setTitle(ui("Patcher updates"))
                    .setMessage(ui(result.message) + (result.version?.let { "\n${ui("Available version")}: $it" } ?: ""))
                    .setNegativeButton(ui("Close"), null)
                result.downloadUrl?.let { url ->
                    dialog.setPositiveButton(ui("Download update")) { _, _ ->
                        if (busy || automatic || PatchWorkerService.isWorking) {
                            updateDialog = AlertDialog.Builder(this).setTitle(ui("Patcher updates"))
                                .setMessage(ui("Finish patching or recovery before updating the patcher."))
                                .setPositiveButton(ui("Close"), null).show()
                        } else {
                            try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                            catch (_: android.content.ActivityNotFoundException) {
                                updateDialog = AlertDialog.Builder(this).setTitle(ui("Patcher updates"))
                                    .setMessage(ui("No browser could open the download. Install a browser and try again."))
                                    .setPositiveButton(ui("Close"), null).show()
                            }
                        }
                    }
                }
                updateDialog = dialog.show()
            }
        }
    }

    /** The activity is going away: close the dialog and stop a check in flight. */
    fun close() {
        updateDialog?.dismiss()
        updateWorker.shutdownNow()
    }
}
