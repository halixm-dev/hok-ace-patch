package dev.halixm.hokacepatcher

import android.app.AlertDialog
import android.content.Intent
import android.widget.LinearLayout
import android.widget.CheckBox
import java.io.File
import java.text.DateFormat
import java.util.Date

// The patcher's setup, recovery, free-space and Remove translation dialogs, moved verbatim from MainActivity
// (tech-debt ticket 02). Each still starts its work through MainActivity.startWorker; routing stays there.

internal fun MainActivity.choosePreparedPatch() {
    val choices = File(filesDir, "preparations").listFiles().orEmpty().filter {
        it.isDirectory && File(it, "receipt.json").isFile
    }.sortedByDescending { it.lastModified() }
    if (choices.isEmpty()) { log("Prepare game files first"); return }
    runOnUiThread {
        AlertDialog.Builder(this).setTitle(ui("Choose prepared game files"))
            .setItems(choices.map { DateFormat.getDateTimeInstance().format(Date(it.lastModified())) }.toTypedArray()) { _, index ->
                runTask {
                    log("Checking prepared game files")
                    val prepared = ApkPreparation(this).load(choices[index].name)
                    check(!prepared.requiresSignatureConversion) { "Use First setup and confirm its separate data-loss warning first" }
                    val run = RunStore(this).start("translate", PatchLanguage.current(this), provider(), RunStore.Target.local(this))
                    // Choosing the files is the explicit action; no routine confirmation follows (ticket 13).
                    val request = PatchRequestStore(this).authorize(run.id, prepared)
                    runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction("patch").putExtra("request", request)) }
                }
            }.setNegativeButton(ui("Cancel"), null).show()
    }
}

internal fun MainActivity.chooseFirstSetup() {
    check(FirstSetupJournal.pending(this).isEmpty()) { "Use Recover or finish game setup first" }
    val choices = File(filesDir, "preparations").listFiles().orEmpty().filter {
        it.isDirectory && File(it, "receipt.json").isFile
    }.sortedByDescending { it.lastModified() }
    if (choices.isEmpty()) { log("Prepare game files first"); return }
    runOnUiThread {
        AlertDialog.Builder(this).setTitle(ui("Choose game files for first setup"))
            .setItems(choices.map { DateFormat.getDateTimeInstance().format(Date(it.lastModified())) }.toTypedArray()) { _, index ->
                runTask {
                    val prepared = ApkPreparation(this).load(choices[index].name)
                    check(prepared.requiresSignatureConversion) { "This game is already converted; use the patch update checkpoint" }
                    runOnUiThread { showFirstSetupConfirmation(prepared) }
                }
            }.setNegativeButton(ui("Cancel"), null).show()
    }
}

/** <parentRun> is the saved translate Start that found the official build; setup keeps it for the translation after. */
internal fun MainActivity.showFirstSetupConfirmation(prepared: ApkPreparation.Prepared, parentRun: String? = null): AlertDialog {
    val loss = CheckBox(this).apply { tag = "setup-data-loss"; text = ui("I accept deletion of the game's local data") }
    val login = CheckBox(this).apply { tag = "setup-scan-login"; text = ui("I will use Scan to login") }
    val checks = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; addView(loss); addView(login) }
    val dialog = AlertDialog.Builder(this).setTitle(ui("First setup deletes local game data"))
        .setMessage(UiText.firstSetup(this))
        .setView(checks).setNegativeButton(ui("Cancel")) { _, _ -> stopAutomatic() }.setOnCancelListener { stopAutomatic() }.setPositiveButton(ui("Delete data and set up"), null).create()
    dialog.show()
    val start = dialog.getButton(AlertDialog.BUTTON_POSITIVE); start.isEnabled = false
    val refresh = { start.isEnabled = loss.isChecked && login.isChecked }
    loss.setOnCheckedChangeListener { _, _ -> refresh() }
    login.setOnCheckedChangeListener { _, _ -> refresh() }
    start.setOnClickListener {
        if (!busy) {
            dialog.dismiss()
            runTask {
                val request = FirstSetupRequestStore(this).confirm(prepared, loss.isChecked, login.isChecked, parentRun)
                runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                    .setAction("first_setup").putExtra("request", request)) }
            }
        }
    }
    return dialog
}

internal fun MainActivity.chooseSetupRecovery() {
    val pending = FirstSetupJournal.pending(this)
    if (pending.isEmpty()) { log("No pending game setup"); return }
    runOnUiThread {
        AlertDialog.Builder(this).setTitle(ui("Recover or finish game setup"))
            .setItems(pending.map { DateFormat.getDateTimeInstance().format(Date(it.snapshot().getLong("updated_ms"))) }.toTypedArray()) { _, index ->
                val journal = pending[index]
                if (journal.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE) showSetupUpdateConfirmation(journal.id)
                else AlertDialog.Builder(this).setTitle(ui("Recover game installation"))
                    .setMessage(ui("Check the installed app and restore the verified normal game app if it is absent. " +
                        "Recovery will not repeat removal. Deleted local game data cannot be restored by this step."))
                    .setNegativeButton(ui("Cancel"), null).setPositiveButton(ui("Recover")) { _, _ ->
                        startWorker(Intent(this, PatchWorkerService::class.java)
                            .setAction("setup_recover").putExtra("setup", journal.id))
                    }.show()
            }.setNegativeButton(ui("Cancel"), null).show()
    }
}

internal fun MainActivity.showSetupUpdateConfirmation(id: String): AlertDialog {
    val check = CheckBox(this).apply { tag = "setup-update-confirmation";
        text = ui("Every fresh game update finished, and I closed the game") }
    val dialog = AlertDialog.Builder(this).setTitle(ui("Finish game setup"))
        .setMessage(UiText.setupUpdate(this))
        .setNeutralButton(ui("Open game")) { _, _ ->
            if (automatic) waitingForDownloads = id
            runTask {
                val setup = FirstSetupJournal.pending(this).single { it.id == id }
                check(setup.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE && setup.normalVerified)
                check(SessionJournal.pending(File(filesDir, "sessions")).isEmpty())
                EmergencyRestoreStore(this).requireResolved()
                runOnUiThread {
                    val launch = packageManager.getLaunchIntentForPackage("com.tencent.tmgp.osgame")
                    if (launch != null) startActivity(launch) else home.message("The game cannot be opened. Use recovery.", failure = true)
                }
            }
        }.setView(check).setNegativeButton(ui("Cancel")) { _, _ -> stopAutomatic() }.setOnCancelListener { stopAutomatic() }.setPositiveButton(ui("Confirm updates"), null).create()
    dialog.show()
    val finish = dialog.getButton(AlertDialog.BUTTON_POSITIVE); finish.isEnabled = false
    check.setOnCheckedChangeListener { _, checked -> finish.isEnabled = checked }
    finish.setOnClickListener {
        dialog.dismiss()
        startWorker(Intent(this, PatchWorkerService::class.java).setAction("setup_update")
            .putExtra("setup", id).putExtra("confirmed", check.isChecked))
    }
    return dialog
}

/** The opt-in starts unchecked and is offered only while saved game apps exist. */
internal fun MainActivity.showFreeSpaceConfirmation() {
    val saved = listOf("preparations", "recovery").sumOf { name ->
        File(filesDir, name).walkTopDown().filter { it.isFile }.sumOf { it.length() }
    }
    val apk = File(filesDir, "recovery").walkTopDown().filter { it.name == "normal.apk" }
        .maxOfOrNull { it.length() } ?: 0L
    val remove = CheckBox(this).apply {
        tag = "free-space-remove-apks"
        text = UiText.removeSavedApks(this@showFreeSpaceConfirmation, saved, StorageBudget.required(apk, apk, apk, apk))
    }
    AlertDialog.Builder(this).setTitle(ui("Free up space?"))
        .setMessage(ui("Removes leftovers from earlier or interrupted runs, and saved game apps this game version no longer needs.\n\nThe original game files the patcher changed are always kept, so you can still remove the translation or switch languages without clearing game data.\n\nKeep the game closed while this runs."))
        .also { if (saved > 0 && apk > 0) it.setView(remove) }
        .setNegativeButton(ui("Cancel"), null).setPositiveButton(ui("Free space")) { _, _ ->
            if (!busy && !automatic && !PatchWorkerService.isWorking)
                startWorker(Intent(this, PatchWorkerService::class.java).setAction("free_space")
                    .putExtra("remove_saved_apks", remove.isChecked))
        }.show().also(PanelDialog::style)
}

/**
 * Remove translation, at the tap: one plain dialog (DESIGN.md, Dialogs), no checkbox. It deletes no game data,
 * so the tap plus this answer is the whole authorization; preparation and continuation never ask again.
 * Cancel or dismissing it starts nothing.
 */
internal fun MainActivity.showRemoveConfirmation(): AlertDialog {
    val dialog = AlertDialog.Builder(this).setTitle(ui("Remove translation"))
        .setMessage(UiText.removeConfirmation(this, provider() == ShellProvider.ROOT))
        .setNegativeButton(ui("Cancel"), null)
        .setPositiveButton(ui("Remove the translation")) { _, _ ->
            if (!busy && !automatic && !PatchWorkerService.isWorking && savedRun == null) {
                removing = true
                beginAutomatic()
            }
        }.create()
    dialog.show()
    PanelDialog.style(dialog)
    return dialog
}

internal fun MainActivity.chooseRecovery() {
    val pending = SessionJournal.pending(File(filesDir, "sessions"))
    if (pending.isEmpty()) { log("No interrupted patch to recover"); return }
    runOnUiThread {
        AlertDialog.Builder(this).setTitle(ui("Recover interrupted patch"))
            .setItems(pending.map { DateFormat.getDateTimeInstance().format(
                Date(it.snapshot().getLong("created_ms"))) + " — " + ui("Interrupted run") }.toTypedArray()) { _, index ->
                startWorker(Intent(this, PatchWorkerService::class.java).setAction("recover")
                    .putExtra("session", pending[index].id))
            }.setNegativeButton(ui("Cancel"), null).show()
    }
}
