package dev.halixm.hokacepatcher

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.ComponentName
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.IBinder
import android.os.Handler
import android.os.Looper
import android.util.AtomicFile
import android.net.Uri
import android.provider.Settings
import android.os.ParcelFileDescriptor
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.CheckBox
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import rikka.shizuku.Shizuku
import java.io.File
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import org.json.JSONObject
import java.text.DateFormat
import java.util.Date

/** Feasibility UI: independent engine checks and explicit, fixed device probes. */
class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var home: GuidedHome
    private val actions = mutableMapOf<String, () -> Unit>()
    private lateinit var output: TextView
    private lateinit var workerStatus: TextView
    private val statusHandler = Handler(Looper.getMainLooper())
    private val refreshStatus = object : Runnable {
        override fun run() {
            val file = File(filesDir, "worker-state.json")
            workerStatus.text = if (!file.isFile) "No saved worker result." else runCatching {
                WorkerStatus.describe(JSONObject(String(AtomicFile(file).readFully(), Charsets.UTF_8)))
            }.getOrElse { "Saved worker result cannot be read. Inspect recovery before opening the game." }
            val emergency = runCatching { EmergencyRestoreStore(this@MainActivity).describe() }
                .getOrElse { "Emergency restore record cannot be read. Keep the game closed and inspect recovery." }
            if (emergency.isNotEmpty()) workerStatus.append("\n$emergency")
            advanceAutomatic()
            refreshHome()
            statusHandler.postDelayed(this, 1000)
        }
    }
    private val buttons = mutableListOf<Button>()
    @Volatile private var service: IPrivilegedDeviceService? = null
    /** Raw text of the newest `ERROR:` an on-screen task logged; cleared when the next task starts. */
    private var lastTaskError = ""
    @Volatile private var destroyed = false
    private var busy = false
    private var automatic = false
    private var awaitingToken: String? = null
    private var awaitingAction: String? = null
    private var permissionRequested = false
    private var waitingForShizuku = false
    private var awaitingSince = 0L
    private var waitingForDownloads: String? = null
    private val args by lazy {
        Shizuku.UserServiceArgs(ComponentName(this, PrivilegedDeviceService::class.java))
            .daemon(false).processNameSuffix("device").tag("hokace-feasibility").version(PrivilegedDeviceService.PROTOCOL_VERSION)
    }
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, binder: IBinder) {
            service = IPrivilegedDeviceService.Stub.asInterface(binder)
            log("Shizuku UserService connected")
        }
        override fun onServiceDisconnected(name: ComponentName) {
            service = null
            log("UserService disconnected; device operations stopped")
        }
    }
    private val received = Shizuku.OnBinderReceivedListener {
        log("Shizuku available")
        runOnUiThread { ensurePermission() }
    }
    private val died = Shizuku.OnBinderDeadListener {
        service = null
        log("Shizuku stopped; device operations unavailable")
    }
    private val permission = Shizuku.OnRequestPermissionResultListener { code, result ->
        DiagnosticTrace.event("ui", "Shizuku permission result $result for request $code")
        runOnUiThread {
            if (result == PackageManager.PERMISSION_GRANTED) {
                connect()
                if (automatic && awaitingToken == null) routeAutomatic()
            } else {
                stopAutomatic()
                home.message("Access was not allowed. Tap Start to try again.")
            }
        }
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        DiagnosticTrace.init(this)
        DiagnosticTrace.event("ui", "Activity created; restored ${state != null}, worker running ${PatchWorkerService.isWorking}")
        permissionRequested = state?.getBoolean("permission-requested") ?: false
        awaitingToken = state?.getString("automatic-token")
        awaitingAction = state?.getString("automatic-action")
        awaitingSince = state?.getLong("automatic-since") ?: 0L
        waitingForShizuku = state?.getBoolean("waiting-shizuku") ?: false
        waitingForDownloads = state?.getString("waiting-downloads")
        automatic = (awaitingToken != null || waitingForShizuku || waitingForDownloads != null) && state?.getBoolean("automatic") == true
        home = GuidedHome(this) { key ->
            DiagnosticTrace.event("ui", "Tap $key; busy $busy automatic $automatic shizuku ${Shizuku.pingBinder()}")
            when (key) {
                "start" -> beginAutomatic()
                "stop" -> AlertDialog.Builder(this).setTitle(ui("Stop safely?"))
                    .setMessage(ui("Keep the game closed. Any unfinished changes must be restored before you open it."))
                    .setNegativeButton(ui("Keep going"), null).setPositiveButton(ui("Stop and recover")) { _, _ ->
                        val hadWorker = awaitingToken != null || PatchWorkerService.isWorking
                        stopAutomatic()
                        if (hadWorker) startService(Intent(this, PatchWorkerService::class.java).setAction("cancel"))
                    }.show()
                "shizuku" -> {
                    if (!Shizuku.pingBinder()) {
                        openShizuku()
                    } else actions["Authorize Shizuku"]?.let { runTask(it) }
                }
                "recovery_options" -> home.showRecovery()
                "language:en", "language:id" -> {
                    val code = key.removePrefix("language:")
                    if (busy || automatic || PatchWorkerService.isWorking) home.language(PatchLanguage.current(this))
                    else runCatching { PatchLanguage.set(this, code) }
                        .onSuccess { log("Language: ${PatchLanguage.name(code)}"); recreate() }
                        .onFailure { log("ERROR: ${it.message}"); home.language(PatchLanguage.current(this)) }
                }
                "game" -> {
                    val launch = packageManager.getLaunchIntentForPackage("com.tencent.tmgp.osgame")
                    if (launch != null) startActivity(launch)
                    else home.message("The game is not installed. Install it before preparing files.")
                }
                else -> actions[when (key) {
                    "prepare" -> "Prepare game files (no installation)"
                    "patch" -> "Patch after the game update finishes"
                    "setup" -> "First setup (deletes local game data)"
                    "setup_recover" -> "Recover or finish game setup"
                    "recover" -> "Recover interrupted patch"
                    "installer" -> "Emergency normal APK installer"
                    "verify" -> "Verify installed normal APK with foreground worker"
                    "export" -> "Export diagnostic logs"
                    else -> key
                }]?.let { runTask(it) }
            }
        }
        home.language(PatchLanguage.current(this))
        workerStatus = TextView(this).apply { tag = "worker-status"; setTextIsSelectable(true) }
        home.advanced.addView(workerStatus)
        fun action(label: String, task: () -> Unit) {
            actions[label] = task
            buttons += home.technicalButton(label) { runTask(task) }
        }
        action("Authorize Shizuku") {
            runOnUiThread {
                try {
                    check(Shizuku.pingBinder()) { "Install and start Shizuku first" }
                    check(!Shizuku.isPreV11()) { "Shizuku API 11+ required" }
                    if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) connect()
                    else Shizuku.requestPermission(1)
                } catch (error: Exception) { log("ERROR: ${error.message}") }
            }
        }
        action("Check Python and codecs") {
            val root = EngineAssets.prepare(this)
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            log(Python.getInstance().getModule("android_bridge").callAttr("diagnostics", root.path).toString())
        }
        action("Prepare game files (no installation)") {
            runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java).setAction("prepare")) }
        }
        action("First setup (deletes local game data)") { chooseFirstSetup() }
        action("Recover or finish game setup") { chooseSetupRecovery() }
        action("Recover interrupted patch") { chooseRecovery() }
        action("Patch after the game update finishes") { choosePreparedPatch() }
        action("Check shell and game APK path") {
            log(device().diagnostics())
            log(device().gameApkInfo())
        }
        action("Copy and verify installed APK (about 2 GB)") { copyApk() }
        action("Round-trip disposable fixture") {
            val bytes = ByteArray(4096).also { SecureRandom().nextBytes(it) }
            check(device().probeFixture(bytes).contentEquals(bytes)) { "Binary fixture differs" }
            log("PASS: shell binary fixture read/write")
            log(NormalRunAsProbe.run())
        }
        action("Force-stop game") { device().forceStopGame(); log("Game force-stopped") }
        action("Verify retained normal recovery APK") {
            val id = recoveryId()
            log("Verified normal recovery: ${RecoveryStore(this).verify(id).json()}")
        }
        action("Emergency normal APK installer") { openRecoveryInstaller() }
        action("Verify installed normal APK with foreground worker") {
            val emergency = EmergencyRestoreStore(this).snapshot()
                ?.takeIf { it.getString("status") == "verification_pending" }
            val id = emergency?.getString("normal") ?: recoveryId()
            runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                .setAction("verify").putExtra("normal", id).also {
                    if (emergency != null) it.putExtra("emergency", emergency.getString("id"))
                }) }
        }
        action("Read worker result") {
            val result = File(filesDir, "worker-state.json")
            log(if (result.isFile) result.readText() else "No worker result yet")
        }
        action("Export diagnostic logs") {
            runOnUiThread { startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE).setType("text/plain")
                .putExtra(Intent.EXTRA_TITLE, "hok-ace-recovery-log.txt"), 1402) }
        }
        output = TextView(this).apply { setTextIsSelectable(true); text = state?.getString("log") ?: "Ready\n" }
        home.addDiagnosticLog(output)
        Shizuku.addBinderReceivedListenerSticky(received)
        Shizuku.addBinderDeadListener(died)
        Shizuku.addRequestPermissionResultListener(permission)
        ensurePermission()
    }

    private fun ensurePermission(): Boolean {
        return try {
            if (!Shizuku.pingBinder()) return false
            if (Shizuku.isPreV11()) { stopAutomatic(); home.message("Update Shizuku before starting."); return false }
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) return true
            if (!permissionRequested) {
                permissionRequested = true
                Shizuku.requestPermission(1)
            }
            false
        } catch (error: Exception) { stopAutomatic(); log("ERROR: ${error.message}"); false }
    }

    private fun beginAutomatic() {
        if (busy || PatchWorkerService.isWorking || awaitingToken != null) return
        automatic = true
        permissionRequested = false
        if (!Shizuku.pingBinder()) {
            waitingForShizuku = true
            openShizuku()
            return
        }
        if (ensurePermission()) routeAutomatic()
    }

    private fun stopAutomatic() { automatic = false; awaitingToken = null; awaitingAction = null; waitingForShizuku = false; waitingForDownloads = null }

    private fun openShizuku() {
        if (!ShizukuLauncher.open(this)) {
            stopAutomatic()
            home.message("Cannot open Shizuku or Google Play. Install Shizuku from play.google.com, start it, then return here.")
        }
    }

    /** Only the Start action arms continuation; opening the app never starts game changes. */
    private fun routeAutomatic() {
        if (!automatic || busy || destroyed || awaitingToken != null || PatchWorkerService.isWorking) return
        if (!Shizuku.pingBinder()) { waitingForShizuku = true; return }
        if (!ensurePermission()) return
        waitingForShizuku = false
        runTask {
            val emergency = EmergencyRestoreStore(this).snapshot()?.takeIf {
                it.getString("status") == "verification_pending"
            }
            val patches = SessionJournal.pending(File(filesDir, "sessions"))
            val setups = FirstSetupJournal.pending(this)
            val decision = AutomaticRoute.choose(emergency?.getString("id"), patches.map { it.id },
                setups.map { AutomaticRoute.Setup(it.id, it.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE) })
            runOnUiThread {
                if (!automatic || destroyed) return@runOnUiThread
                when (decision.step) {
                    AutomaticRoute.Step.VERIFY -> startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction("verify").putExtra("normal", emergency!!.getString("normal"))
                        .putExtra("emergency", decision.id))
                    AutomaticRoute.Step.RECOVER_PATCH -> startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction("recover").putExtra("session", decision.id))
                    AutomaticRoute.Step.RECOVER_SETUP -> startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction("setup_recover").putExtra("setup", decision.id))
                    AutomaticRoute.Step.WAIT_FOR_DOWNLOADS -> showSetupUpdateConfirmation(decision.id!!)
                    AutomaticRoute.Step.PREPARE -> startWorker(Intent(this, PatchWorkerService::class.java).setAction("prepare"))
                    AutomaticRoute.Step.MANUAL -> {
                        stopAutomatic()
                        home.message("More than one unfinished run was found. Choose the correct run in recovery options.")
                        home.showRecovery()
                    }
                }
            }
        }
    }

    private fun startWorker(intent: Intent) {
        if (destroyed) return
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

    private fun savedWorker(): JSONObject? {
        val file = File(filesDir, "worker-state.json")
        return if (!file.exists() && !File(file.path + ".bak").exists()) null
            else JSONObject(String(AtomicFile(file).readFully(), Charsets.UTF_8))
    }

    private fun advanceAutomatic() {
        if (!automatic || busy || destroyed) return
        if (awaitingToken != null && PatchWorkerService.isWorking) return
        val result = runCatching { savedWorker() }.getOrElse {
            stopAutomatic(); home.message("Saved progress cannot be read. Keep the game closed and save a log for help."); return
        }
        if (awaitingToken == null) {
            if (waitingForDownloads != null) { waitingForDownloads = null; routeAutomatic(); return }
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
                stopAutomatic(); home.message("Work could not start. Check Shizuku, then tap Start again.")
                return
            }
            if (!PatchWorkerService.isWorking && result?.optString("flow") == awaitingToken &&
                result?.optString("status") == "running") {
                val latest = runCatching { savedWorker() }.getOrNull()
                if (latest?.optString("status") != "running" || PatchWorkerService.isWorking) return
                stopAutomatic(); home.message("Work was interrupted. Tap Start to check and restore unfinished work.")
            }
            return
        }
        awaitingToken = null; awaitingAction = null
        when (result!!.getString("status")) {
            "prepared" -> {
                runTask {
                    val prepared = ApkPreparation(this).load(result.getString("preparation"))
                    runOnUiThread {
                        if (!automatic || destroyed) return@runOnUiThread
                        if (prepared.requiresSignatureConversion) showFirstSetupConfirmation(prepared)
                        else showPatchConfirmation(prepared)
                    }
                }
            }
            "verified", "recovered", "setup_ready", "setup_waiting" -> routeAutomatic()
            "complete" -> stopAutomatic()
            else -> { stopAutomatic(); log("ERROR: " + WorkerStatus.describe(result)) }
        }
    }

    private fun refreshHome() {
        if (!::home.isInitialized) return
        val state = runCatching { savedWorker() }.getOrNull()
        val pending = runCatching {
            SessionJournal.pending(File(filesDir, "sessions")).isNotEmpty() ||
                FirstSetupJournal.pending(this).isNotEmpty() ||
                EmergencyRestoreStore(this).snapshot()?.optString("status") == "verification_pending"
        }
        val messages = state?.optJSONArray("messages")
        home.logs(if (messages == null) emptyList() else
            (0 until messages.length()).map { messages.optString(it) })
        val live = PatchWorkerService.isWorking || awaitingToken != null
        when {
            live -> home.show("Working on your game", UiText.progress(this, state?.optString("progress", "Checking and preparing files…")
                ?: "Checking and preparing files…"), "Please wait", "start", false)
            busy && automatic -> home.show("Checking game files", "Please wait. We are checking the saved game app and recovery files.", "Please wait", "start", false)
            pending.isFailure -> home.show("Recovery needs attention", "Keep the game closed. Save a log for help.", "Save log for help", "export", true)
            !Shizuku.pingBinder() && !ShizukuLauncher.isInstalled(this) -> home.show("Install Shizuku", "Shizuku is required. Install it from Google Play, start it, then return here.", "Get Shizuku", "start", pending.getOrDefault(false))
            !Shizuku.pingBinder() -> home.show("Start Shizuku", "Shizuku must be running. Start it, then return here. We will continue automatically.", "Open Shizuku", "start", pending.getOrDefault(false))
            state?.optString("status") == "complete" && !pending.getOrThrow() -> home.show("Translation added", UiText.completed(this, state), "Start another patch", "start", false)
            state?.optString("status") in setOf("error", "recovery_required") -> home.show("Work stopped", friendlyFailure(state?.optString("error").orEmpty()), "Try again", "start", true)
            pending.getOrThrow() -> home.show("Finish your game safely", "We will check unfinished work and recover it before patching.", "Continue", "start", true)
            else -> home.show("Ready when you are", "Tap Start. We will check your game and prepare everything. Keep the game closed while we work.", "Start", "start", false)
        }
        home.working(busy || live || (automatic && !waitingForShizuku))
        home.languageEnabled(!busy && !live && !automatic)
        home.progress(live || (busy && automatic))
        buttons.forEach { it.isEnabled = !busy && !live && !automatic }
        home.resultMessage(if (!automatic && state?.optString("status") in setOf("error", "recovery_required"))
            friendlyFailure(state?.optString("error").orEmpty()) else "")
        home.errorDetails(when {
            live -> ""
            // The worker's own raw error first: the automatic flow also logs it, already explained, as an ERROR.
            state?.optString("status") in setOf("error", "recovery_required") -> state?.optString("error").orEmpty()
            else -> lastTaskError
        })
    }

    private fun friendlyFailure(message: String): String {
        StorageBudget.explainFailure(message, filesDir.usableSpace)?.let { return UiText.storage(this, it) }
        if (message.contains("GB free for this step")) return UiText.storage(this, message.removePrefix("ERROR: "))
        return when {
            message.contains("space", true) || message.contains("storage", true) ->
                ui("Free now:") + " ${StorageBudget.freeSpaceLabel(filesDir.usableSpace)}.\n" +
                    ui("The phone did not report how much more space is needed. Free space elsewhere and retry. Keep saved recovery files.")
            message.contains("Shizuku worker connection timed out") ->
                "Shizuku is running, but the patcher's helper did not start. Open Shizuku, stop it and start it again, then return here and tap Try again. If it happens again, save a log for help. Keep the game closed."
            message.contains(FirstSetupPackagePolicy.OTHER_PROFILE) ->
                "The game is also installed in another Android profile, such as Dual App or a work profile. Remove it from that profile, then tap Try again. Keep the game closed."
            message.contains(FirstSetupPackagePolicy.UNCHECKED_PROFILE) ->
                "This phone has another Android profile, such as Dual App, that could not be checked for the game. Remove the game from Dual App, then tap Try again. If it happens again, save a log for help. Keep the game closed."
            message.contains(InstalledGameVerifier.DIFFERENT_APP) ->
                "The installed game app is not the saved app this check looks for. It is a different app, not a damaged one. If no patch was started, tap Try again. Otherwise check recovery options below, or save a log for help. Keep the game closed."
            message.contains("USER_RESTRICTED", true) ->
                "The phone blocked installation. Unlock it and accept the install prompt. Open Technical tools for the full error."
            // The command ran, so Shizuku is working; the phone itself refused the step.
            message.contains("Device command failed") ->
                "The phone refused a step, although Shizuku is working. Keep the game closed. Check recovery options below, or save a log for help."
            message.contains("Shizuku", true) || message.contains("permission", true) ->
                "Open Shizuku. Start it and allow HOK ACE. Return here and retry. Keep the game closed."
            else -> "Work stopped. Keep the game closed. Check recovery options below, or save a log for help."
        }
    }

    private fun ui(value: String) = UiText.text(this, value)

    private fun device(): IPrivilegedDeviceService = checkNotNull(service) { "Authorize and connect Shizuku first" }

    private fun choosePreparedPatch() {
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
                        runOnUiThread { showPatchConfirmation(prepared) }
                    }
                }.setNegativeButton(ui("Cancel"), null).show()
        }
    }

    private fun chooseFirstSetup() {
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

    private fun showFirstSetupConfirmation(prepared: ApkPreparation.Prepared): AlertDialog {
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
                    val request = FirstSetupRequestStore(this).confirm(prepared, loss.isChecked, login.isChecked)
                    runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction("first_setup").putExtra("request", request)) }
                }
            }
        }
        return dialog
    }

    private fun chooseSetupRecovery() {
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

    private fun showSetupUpdateConfirmation(id: String): AlertDialog {
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
                        if (launch != null) startActivity(launch) else home.message("The game cannot be opened. Use recovery.")
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

    private fun showPatchConfirmation(prepared: ApkPreparation.Prepared): AlertDialog {
        val confirmation = CheckBox(this).apply {
            tag = "update-confirmation"; text = ui("All in-game updates finished, and I closed the game")
        }
        val dialog = AlertDialog.Builder(this).setTitle(ui("Start translation"))
            .setMessage(UiText.patchConfirmation(this))
            .setView(confirmation).setNegativeButton(ui("Cancel")) { _, _ -> stopAutomatic() }.setOnCancelListener { stopAutomatic() }.setPositiveButton(ui("Start patch"), null).create()
        dialog.show()
        run {
            val start = dialog.getButton(AlertDialog.BUTTON_POSITIVE); start.isEnabled = false
            confirmation.setOnCheckedChangeListener { _, checked -> start.isEnabled = checked }
            start.setOnClickListener {
                if (!busy) {
                    dialog.dismiss()
                    runTask {
                        val request = PatchRequestStore(this).confirm(prepared, confirmation.isChecked)
                        runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                            .setAction("patch").putExtra("request", request)) }
                    }
                }
            }
        }
        return dialog
    }

    private fun chooseRecovery() {
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

    override fun onResume() { super.onResume(); DiagnosticTrace.event("ui", "Activity resumed"); statusHandler.post(refreshStatus) }
    override fun onPause() { DiagnosticTrace.event("ui", "Activity paused"); statusHandler.removeCallbacks(refreshStatus); super.onPause() }

    private fun recoveryId(): String {
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

    private fun openRecoveryInstaller() {
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

    private fun openRecoveryInstaller(id: String) {
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

    @Deprecated("Activity result API retained for the minimal diagnostic UI")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 1402 || resultCode != RESULT_OK || data?.data == null) return
        val uri = data.data!!
        runTask {
            checkNotNull(contentResolver.openOutputStream(uri, "wt")).bufferedWriter().use { output ->
                DiagnosticLogExport(this).write(output)
            }
            log("Diagnostic logs exported to the selected document")
        }
    }
    private fun connect() {
        DiagnosticTrace.event("ui", "Binding activity UserService")
        try { Shizuku.bindUserService(args, connection) }
        catch (error: Exception) { DiagnosticTrace.error("ui", "bindUserService refused", error); log("Cannot bind UserService: ${error.message}") }
    }

    private fun copyApk() {
        val info = org.json.JSONObject(device().gameApkInfo())
        val needed = info.getLong("bytes") + 256L * 1024 * 1024
        val available = filesDir.usableSpace
        check(available >= needed) { "Insufficient storage for APK copy: $needed bytes required, $available available; keep recovery material" }
        val target = File(filesDir, "probe-installed.apk.partial")
        try {
            val result = ParcelFileDescriptor.open(target, ParcelFileDescriptor.MODE_CREATE or
                ParcelFileDescriptor.MODE_TRUNCATE or ParcelFileDescriptor.MODE_WRITE_ONLY).use {
                org.json.JSONObject(device().copyGameApk(it))
            }
            val hash = MessageDigest.getInstance("SHA-256")
            target.inputStream().use { stream ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = stream.read(buffer)
                    if (count < 0) break
                    hash.update(buffer, 0, count)
                }
            }
            val digest = hash.digest().joinToString("") { "%02x".format(it) }
            check(target.length() == result.getLong("bytes") && digest == result.getString("sha256")) {
                "APK stream read-back mismatch"
            }
            // A probe copy is not accepted as a recovery/normal APK without manifest/certificate checks.
            log("PASS: streamed ${target.length()} bytes, SHA-256 $digest")
        } finally { target.delete() }
    }

    private fun runTask(task: () -> Unit) {
        if (busy) return
        busy = true
        lastTaskError = ""
        home.working(true)
        buttons.forEach { it.isEnabled = false }
        worker.execute {
            try { task() } catch (error: Exception) {
                DiagnosticTrace.error("ui", "Task failed", error)
                runOnUiThread { stopAutomatic() }; log("ERROR: ${error.message}")
            }
            finally {
                runOnUiThread {
                    busy = false
                    if (!destroyed) refreshHome()
                }
            }
        }
    }
    private fun log(message: String) {
        DiagnosticTrace.event("ui", "Log: $message")
        runOnUiThread {
            if (!destroyed) {
                if (message.startsWith("ERROR:")) lastTaskError = message.removePrefix("ERROR:").trim()
                if (message.startsWith("ERROR:") || message.startsWith("Cannot ") || message.startsWith("Prepare game") || message.startsWith("No ")) home.message(if (message.startsWith("ERROR:") || message.startsWith("Cannot ")) friendlyFailure(message) else message)
                output.append(message + "\n")
                if (output.text.length > 32768) output.text = output.text.takeLast(32768)
                File(filesDir, "feasibility.log").appendText(message + "\n")
            }
        }
    }
    override fun onSaveInstanceState(state: Bundle) {
        state.putString("log", output.text.toString())
        state.putBoolean("permission-requested", permissionRequested)
        state.putBoolean("waiting-shizuku", waitingForShizuku)
        state.putString("waiting-downloads", waitingForDownloads)
        state.putBoolean("automatic", automatic)
        state.putString("automatic-token", awaitingToken)
        state.putString("automatic-action", awaitingAction)
        state.putLong("automatic-since", awaitingSince)
        super.onSaveInstanceState(state)
    }
    override fun onDestroy() {
        DiagnosticTrace.event("ui", "Activity destroyed; changing configuration $isChangingConfigurations")
        destroyed = true
        statusHandler.removeCallbacks(refreshStatus)
        Shizuku.removeBinderReceivedListener(received)
        Shizuku.removeBinderDeadListener(died)
        Shizuku.removeRequestPermissionResultListener(permission)
        if (Shizuku.pingBinder()) {
            try { Shizuku.unbindUserService(args, connection, true) } catch (_: Exception) { }
        }
        service = null
        worker.shutdownNow()
        super.onDestroy()
    }
}
