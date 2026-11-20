package dev.halixm.hokacepatcher

import android.content.Intent
import android.content.pm.PackageManager
import rikka.shizuku.Shizuku
import java.io.File
import org.json.JSONObject

// The automatic route: Start and Try again, the provider waits, worker dispatch and what follows each worker
// result, moved verbatim from MainActivity (tech-debt ticket 02). AutomaticRoute stays the one decision function.

/**
 * <explicit> is a tap on Start or Try again: it re-arms the saved action's safe automatic retries (never Stop,
 * consent or an uninstall). A saved action whose provider is not ready waits for it while the app is open.
 */
internal fun MainActivity.beginAutomatic(explicit: Boolean = false) {
    if (busy || PatchWorkerService.isWorking || awaitingToken != null) return
    loadSavedRun()
    if (explicit) savedRun?.let { run ->
        runCatching {
            if (run.mayContinue && !stopping) RunStore(this).rearm(run.id)
            else RunStore(this).rearmSafety(run.id)
        }.onFailure { DiagnosticTrace.error("ui", "Retry could not re-arm", it) }
    }
    // A Start that finds an approved saved action continues it (reusing its valid work) rather than starting fresh.
    if (savedRun?.mayContinue == true) continuing = true
    automatic = true
    permissionRequested = false
    val provider = provider()
    val waits = savedRun != null
    if (!provider.available) {
        stopAutomatic(); home.message(notReady(provider), failure = true); return
    }
    if (provider == ShellProvider.WIRELESS) wirelessRefusal()?.let {
        // The saved provider is never swapped for another: wait for it, showing what it needs.
        if (waits) { waitForAccess(); return }
        stopAutomatic(); home.message(it, failure = true); return
    }
    if (provider != ShellProvider.SHIZUKU) { routeAutomatic(); return }
    if (!Shizuku.pingBinder()) {
        waitingForShizuku = true
        openShizuku()
        return
    }
    if (shizukuAsRoot()) { stopAutomatic(); home.message(ShellProvider.SHIZUKU_AS_ROOT, failure = true); return }
    if (ensurePermission()) routeAutomatic()
}

/** Why wireless debugging cannot start a run now, or null; the starter checks the same again. */
internal fun MainActivity.wirelessRefusal(): String? = when {
    !WirelessDebugging.onWifi(this) -> WirelessDebugging.NO_WIFI
    !WirelessDebugging.paired(this) -> WirelessDebugging.NOT_PAIRED
    !WirelessDebugging.switchedOn(this) -> WirelessDebugging.SWITCHED_OFF
    else -> null
}

/** ③ while Wireless debugging is off: open its Settings row, as Pair does; coming back re-reads the switch. */
internal fun MainActivity.openWirelessDebugging() {
    DiagnosticTrace.event("ui", "Opening Wireless debugging to turn it on")
    if (!WirelessDebugging.openSettings(this))
        home.message("Open Settings, then Developer options, then Wireless debugging.", failure = true)
}

/** Post the notification that takes the pairing code, then open Wireless debugging for its code. */
internal fun MainActivity.pairWireless() {
    if (busy || (automatic && !waitingForAccess) || PatchWorkerService.isWorking) return
    if (!WirelessDebugging.onWifi(this)) { home.message(WirelessDebugging.NO_WIFI, failure = true); return }
    if (android.os.Build.VERSION.SDK_INT >= 33 &&
        checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
        requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), PAIRING_NOTIFICATIONS)
        home.message("Allow notifications: you type the pairing code into one. Then tap Pair again.")
        return
    }
    if (!WirelessDebugging.askForCode(this)) {
        home.message("Notifications are off for HOK ACE. Turn them on in Android Settings: you type the pairing code into one.", failure = true)
        return
    }
    DiagnosticTrace.event("ui", "Pairing notification posted; opening Wireless debugging")
    if (!WirelessDebugging.openSettings(this))
        home.message("Open Settings, then Developer options, then Wireless debugging.", failure = true)
}

/** The guide's line for a provider this build cannot start yet. */
internal fun MainActivity.notReady(provider: ShellProvider) = FailureText.notReady(this, provider)

internal fun MainActivity.stopAutomatic() { automatic = false; removing = false; awaitingToken = null; awaitingAction = null; waitingForShizuku = false; waitingForDownloads = null; waitingForAccess = false; stopping = false; continuing = false; recoveryOnly = false }

internal fun MainActivity.openShizuku() {
    if (!ShizukuLauncher.open(this)) {
        stopAutomatic()
        home.message("Cannot open Shizuku or Google Play. Install Shizuku from play.google.com, start it, then return here.", failure = true)
    }
}

/** Only the Start action arms continuation; opening the app never starts game changes. */
internal fun MainActivity.routeAutomatic() {
    if (!automatic || busy || destroyed || awaitingToken != null || PatchWorkerService.isWorking) return
    if (usesShizuku()) {
        if (!Shizuku.pingBinder()) { waitingForShizuku = true; return }
        if (!ensurePermission()) return
    }
    waitingForShizuku = false
    var emergency: JSONObject? = null
    var continued: RunStore.Run? = null
    fun chooseRoute(): AutomaticRoute.Decision {
        emergency = EmergencyRestoreStore(this).snapshot()?.takeIf {
            it.getString("status") == "verification_pending"
        }
        val patches = SessionJournal.pending(File(filesDir, "sessions"))
        val setups = FirstSetupJournal.pending(this)
        val runs = RunStore(this).pending().map { AutomaticRoute.Run(it.id, it.lifecycle, it.mayContinue, it.sessionId) }
        val decision = AutomaticRoute.choose(emergency?.getString("id"), patches.map { it.id },
            setups.map { AutomaticRoute.Setup(it.id, it.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE) }, runs)
        continued = decision.id?.takeIf { decision.step == AutomaticRoute.Step.CONTINUE_RUN }
            ?.let { RunStore(this).load(it) }
        return decision
    }
    AutomaticRouteTask.run(task = ::runTask, postUi = { runOnUiThread(it) }, choose = ::chooseRoute,
        resolve = { id -> RunStore.coordinator(this) {
            // Routing was only a snapshot. Re-read safety and durable Stop under the mutation lock.
            check(chooseRoute() == AutomaticRoute.Decision(AutomaticRoute.Step.RESOLVE_STOPPED, id)) {
                "Stopped action now needs recovery attention"
            }
            RunStore(this).resolve(id)
        } }, deliver = delivery@{ decision, resolved ->
            val continued = continued
            if (!automatic || destroyed) return@delivery
            // After Stop safely: safety recovery and closing the record only, then the action stays stopped.
            if (stopping && !AutomaticRoute.allowedWhileStopping(decision.step)) { finishStop(); return@delivery }
            // Recovery's own button never turns into a fresh patch: with nothing left to recover or continue it ends.
            if (recoveryOnly && decision.step == AutomaticRoute.Step.PREPARE && decision.id == null) {
                stopAutomatic(); home.message(UiText.string(this, "nothing_left_to_recover")); refreshHome()
                return@delivery
            }
            when (decision.step) {
                AutomaticRoute.Step.VERIFY -> startWorker(Intent(this, PatchWorkerService::class.java)
                    .setAction("verify").putExtra("normal", emergency!!.getString("normal"))
                    .putExtra("emergency", decision.id))
                AutomaticRoute.Step.RECOVER_PATCH -> startWorker(Intent(this, PatchWorkerService::class.java)
                    .setAction("recover").putExtra("session", decision.id))
                AutomaticRoute.Step.RECOVER_SETUP -> startWorker(Intent(this, PatchWorkerService::class.java)
                    .setAction("setup_recover").putExtra("setup", decision.id))
                AutomaticRoute.Step.WAIT_FOR_DOWNLOADS -> showSetupUpdateConfirmation(decision.id!!)
                AutomaticRoute.Step.PREPARE -> startWorker(Intent(this, PatchWorkerService::class.java).setAction("prepare")
                    .apply { decision.id?.let { putExtra("run", it) } })
                // A confirmed Start continues from its checkpoints; its dispatch restores consistency first.
                AutomaticRoute.Step.CONTINUE_RUN -> when (continued?.action) {
                    // A Re-download plan waits for its own answer, or the game's download, before the action goes on.
                    "translate", "remove" -> if (!redownloadWaits(continued)) startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction(if (continued.action == "remove") "remove" else "patch").putExtra("request", decision.id))
                    // Re-download and first setup continue only under their own scoped consent (tickets 12/13).
                    else -> { stopAutomatic(); home.message("This saved action needs its own confirmation. " +
                        "Choose it again from recovery options.", failure = true); home.showRecovery() }
                }
                // Stop was saved and nothing is mid-change: close the record without device work.
                AutomaticRoute.Step.RESOLVE_STOPPED -> {
                    loadSavedRun()
                    if (resolved!!.isFailure) {
                        stopAutomatic()
                        home.message("The stopped action cannot be closed yet. Keep the game closed and save a log for help.", failure = true)
                    } else if (stopping) finishStop() else routeAutomatic()
                }
                AutomaticRoute.Step.MANUAL -> {
                    stopAutomatic()
                    home.message("More than one unfinished run was found. Choose the correct run in recovery options.", failure = true)
                    home.showRecovery()
                }
            }
    })
}

internal fun MainActivity.startWorker(intent: Intent) {
    if (destroyed) return
    // A Stop in flight never starts new work; the worker's own durable checks refuse it as well.
    if (stopping && intent.action in setOf("prepare", "patch", "remove", "redownload", "first_setup", "setup_update")) {
        finishStop(); return
    }
    if (intent.action == "prepare") {
        val store = RunStore(this)
        val action = if (removing) "remove" else "translate"
        val pending = store.pending()
        check(pending.size <= 1) { "Multiple pending Start records need attention" }
        val saved = intent.getStringExtra("run")
        val run = pending.singleOrNull() ?: store.start(action, PatchLanguage.current(this), provider(), RunStore.Target.local(this))
        // A routed saved Start keeps its own choices; a new tap must match the one already saved.
        if (saved != null) check(run.id == saved && run.mayContinue && run.provider == provider()) {
            "Stop or finish the saved action before changing choices"
        } else check(run.mayContinue && run.action == action && run.language == PatchLanguage.current(this) &&
            run.provider == provider()) {
            "Stop or finish the saved action before changing choices"
        }
        removing = run.action == "remove"
        intent.putExtra("run", run.id)
        savedRun = run
    }
    if (automatic) {
        val token = java.util.UUID.randomUUID().toString()
        awaitingToken = token; awaitingAction = intent.action
        awaitingSince = android.os.SystemClock.elapsedRealtime()
        intent.putExtra("flow", token)
    }
    DiagnosticTrace.event("ui", "Starting worker ${intent.action} flow ${intent.getStringExtra("flow")}")
    try { startForegroundService(intent) }
    catch (error: Exception) { DiagnosticTrace.error("ui", "Worker did not start", error); stopAutomatic(); log("ERROR: ${error.message}") }
}

internal fun MainActivity.savedWorker(): JSONObject? {
    val file = File(filesDir, "worker-state.json")
    return if (!file.exists() && !File(file.path + ".bak").exists()) null
        else JSONObject(String(DurableFiles.readCommitted(file), Charsets.UTF_8))
}

/** Recheck only free bytes, with bounded polling. The coordinator rechecks before opening access. */
internal fun MainActivity.resumeStorageWait() {
    val now = android.os.SystemClock.elapsedRealtime()
    if (now < nextStorageCheck || automatic || busy || destroyed || PatchWorkerService.isWorking) return
    nextStorageCheck = now + 5_000
    val run = savedRun?.takeIf { it.mayContinue && !it.retryExhausted && it.waiting == "storage" } ?: return
    val result = runCatching { savedWorker() }.getOrNull() ?: return
    if (result.optString("run") != run.id || result.optString("reason") != "storage") return
    val needed = result.optJSONObject("storage_wait")?.optLong("required_bytes", -1) ?: return
    if (needed > 0 && filesDir.usableSpace >= needed) beginAutomatic()
}

internal fun MainActivity.advanceAutomatic() {
    if (!automatic || busy || destroyed) return
    if (awaitingToken != null && PatchWorkerService.isWorking) return
    val result = runCatching { savedWorker() }.getOrElse {
        stopAutomatic(); home.message("Saved progress cannot be read. Keep the game closed and save a log for help.", failure = true); return
    }
    if (awaitingToken == null) {
        // A Stop sent to a worker this flow did not start: once it ends, finish the Stop's safety recovery.
        if (stopping && !PatchWorkerService.isWorking && !waitingForShizuku && !waitingForAccess) { routeAutomatic(); return }
        if (waitingForDownloads != null) { waitingForDownloads = null; routeAutomatic(); return }
        // The saved provider came back while the app is open: continue (waiting is never an attempt).
        if (waitingForAccess && provider().available &&
            (provider() != ShellProvider.WIRELESS || wirelessRefusal() == null)) {
            waitingForAccess = false; savedWaiting(null); routeAutomatic(); return
        }
        // Resume after the user starts Shizuku outside this app; dialogs remain user-controlled.
        if (waitingForShizuku && Shizuku.pingBinder()) {
            if (ensurePermission()) routeAutomatic()
        }
        return
    }
    if (!AutomaticRoute.finished(result, awaitingToken, PatchWorkerService.isWorking)) {
        if (!PatchWorkerService.isWorking && result?.optString("flow") != awaitingToken &&
            (android.os.SystemClock.elapsedRealtime() < awaitingSince ||
                android.os.SystemClock.elapsedRealtime() - awaitingSince > 30_000)) {
            stopAutomatic()
            home.message(UiText.string(this, "work_could_not_start_check_provider", "provider" to ui(provider().label)), failure = true)
            return
        }
        if (!PatchWorkerService.isWorking && result?.optString("flow") == awaitingToken &&
            result?.optString("status") == "running") {
            val latest = runCatching { savedWorker() }.getOrNull()
            if (latest?.optString("status") != "running" || PatchWorkerService.isWorking) return
            awaitingToken = null; awaitingAction = null
            if (stopping) { routeAutomatic(); return } // Finish the Stop's safety recovery.
            if (retryAutomatically(latest)) return
            stopAutomatic(); home.message("Work was interrupted. Tap Start to check and restore unfinished work.", failure = true)
        }
        return
    }
    awaitingToken = null; awaitingAction = null
    if (stopping) { continueStop(result!!); return }
    when (result!!.getString("status")) {
        // The explicit Start (or Remove) saved the action before preparation, so the prepared files are bound to
        // it and the work goes on: no routine checkbox or dialog (spec Q7). The finish-updates and closed-game
        // instruction is on ③ before Start. Only first setup's data-loss consent still asks.
        "prepared" -> if (result.optBoolean("root")) {
            // Root installs no APK: no first setup, and the binding covers only the saved copy of the game app.
            runTask {
                val prepared = ApkPreparation(this).loadRoot(result.getString("preparation"))
                val request = PatchRequestStore(this).authorizeRoot(result.getString("run"), prepared)
                runOnUiThread { if (automatic && !destroyed) dispatchAuthorized(request) }
            }
        } else {
            runTask {
                val run = result.getString("run")
                val prepared = ApkPreparation(this).load(result.getString("preparation"))
                val setupReady = !removing && !prepared.requiresSignatureConversion && FirstSetupJournal.readyFor(this, run)
                // Setup already asked whether downloads finished and bound its own Start.
                val request = if (prepared.requiresSignatureConversion || setupReady) run
                    else PatchRequestStore(this).authorize(run, prepared)
                runOnUiThread {
                    if (!automatic || destroyed) return@runOnUiThread
                    if (removing && prepared.requiresSignatureConversion) {
                        stopAutomatic()
                        home.message("The game on this phone is the official build, which this patcher never translated, so there is nothing to remove.")
                    } else if (prepared.requiresSignatureConversion) showFirstSetupConfirmation(prepared, run)
                    else dispatchAuthorized(request)
                }
            }
        }
        "verified", "recovered", "setup_ready", "setup_waiting" -> routeAutomatic()
        // The original app is still installed after an uncertain uninstall: this attempt's consent is used,
        // so the saved Start waits for a fresh data-loss approval on the same verified preparation.
        "setup_cancelled" -> freshSetupConsent(result)
        // The translation is on the phone; patching again is the user's call, not automatic.
        "recovered_unconfirmed" -> stopAutomatic()
        "complete" -> stopAutomatic()
        // The saved action waits for the game's download, or for a Re-download review the loop guard held back
        // (ticket 12); the review card's Delete and re-download tap alone approves that one.
        "waiting" -> {
            stopAutomatic(); log(WorkerStatus.describe(result))
            loadSavedRun()
            refreshHome()
        }
        // Stop was honoured and the game files and app are consistent; the saved action is closed.
        "stopped_consistent" -> stopAutomatic()
        // The provider dropped the worker during prepare: nothing was written, so its own line says so and leads back to Start.
        // A saved action that lost its provider waits for that same provider, within its retry budget.
        "cancelled" -> if (retryAutomatically(result)) Unit
        else if (result.optString("error").contains("disconnected", true)) {
            stopAutomatic()
            log(WorkerStatus.describe(result))
            home.message(when (provider()) {
                ShellProvider.WIRELESS -> "Wireless debugging disconnected. No game files changed. Turn Wi-Fi and Wireless debugging back on, then tap Start."
                ShellProvider.ROOT -> "Root access stopped. No game files changed. Check HOK ACE in your root manager, then tap Start."
                else -> friendlyFailure(result.optString("error"), recoverable = false)
            }, failure = true)
        } else { stopAutomatic(); log("ERROR: " + WorkerStatus.describe(result)) }
        else -> if (!retryAutomatically(result)) { stopAutomatic(); log("ERROR: " + WorkerStatus.describe(result)) }
    }
}

/**
 * A Stop flow's worker ended. Consistency results route on (more safety recovery, or closing the record,
 * after which [routeAutomatic] finishes the Stop). A failure ends the flow with its own next action; the
 * saved Stop stays, so the next open finishes the recovery and the action never continues.
 */
internal fun MainActivity.continueStop(result: JSONObject) {
    when (result.optString("status")) {
        "error", "recovery_required" -> { stopAutomatic(); log("ERROR: " + WorkerStatus.describe(result)) }
        // The action finished before the Stop reached a boundary; its own result card says so.
        // Also when the Stop landed after the translation was verified and finalized ([WorkerStatus.afterStop]).
        "complete", "recovered_unconfirmed" -> stopAutomatic()
        else -> routeAutomatic()
    }
}

/**
 * The saved action failed (or lost its provider). The failure is charged to the logical operation it was in
 * (the last one the worker began, see [RunStore.recordFailure]); within that operation's one persisted
 * automatic retry, try again: at once when the provider is ready, otherwise once it returns. False when the
 * action is stopped, unsaved or the same operation already failed on its retry; that pause survives reopen
 * until an explicit Retry.
 */
internal fun MainActivity.retryAutomatically(result: JSONObject?): Boolean {
    if (result?.optString("reason") == "storage") return false
    val id = result?.optString("run").orEmpty().ifEmpty { return false }
    val retry = runCatching { RunStore(this).load(id).mayContinue && RunStore(this).recordFailure(id, failureClass(result)) }
        .onFailure { DiagnosticTrace.error("ui", "Failure could not be recorded", it) }.getOrDefault(false)
    loadSavedRun()
    if (!retry) return false
    DiagnosticTrace.event("ui", "Automatic retry of the saved action after: ${result?.optString("error")}")
    log(UiText.string(this, "retrying_saved_action"))
    continuing = true
    val provider = provider()
    if (!provider.available || (provider == ShellProvider.WIRELESS && wirelessRefusal() != null)) waitForAccess()
    else if (provider == ShellProvider.SHIZUKU && !Shizuku.pingBinder()) waitingForShizuku = true
    else routeAutomatic()
    return true
}

/** The persisted class of a failed worker result; provider loss is charged to the operation it interrupted. */
internal fun MainActivity.failureClass(result: JSONObject?): String = when {
    result?.optString("error").orEmpty().contains("disconnected", true) -> "provider_lost"
    result?.optString("status") == "running" -> "interrupted"
    result?.optString("status") == "recovery_required" -> "recovery_required"
    result?.optString("status") == "cancelled" -> "cancelled"
    else -> "error"
}

/** Wait for the saved provider while the app is open; the reason is saved, and waiting is never an attempt. */
internal fun MainActivity.waitForAccess() { waitingForAccess = true; savedWaiting("provider") }

internal fun MainActivity.savedWaiting(reason: String?) {
    val run = savedRun?.takeIf { it.mayContinue && it.waiting != reason } ?: return
    runCatching { RunStore(this).waitFor(run.id, reason) }.onFailure { DiagnosticTrace.error("ui", "Waiting reason not saved", it) }
    loadSavedRun()
}

/** Ask again for data-loss consent on the same preparation, but only for a saved Start that may continue. */
internal fun MainActivity.freshSetupConsent(result: JSONObject) {
    val run = savedRun?.takeIf { it.mayContinue && it.action == "translate" }
    val preparation = result.optString("preparation")
    if (run == null || preparation.isEmpty()) { stopAutomatic(); log(WorkerStatus.describe(result)); return }
    runTask {
        val prepared = ApkPreparation(this).load(preparation)
        check(prepared.requiresSignatureConversion) { "This game is already converted; use the patch update checkpoint" }
        runOnUiThread { if (automatic && !destroyed) showFirstSetupConfirmation(prepared, run.id) }
    }
}
