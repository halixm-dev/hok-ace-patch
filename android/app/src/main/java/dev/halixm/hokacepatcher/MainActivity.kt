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

/** A launcher shortcut's Start waits for Shizuku's binder this many times, this long apart (3 s in all). */
private const val SHORTCUT_TRIES = 15
private const val SHORTCUT_WAIT_MS = 200L
private const val EXPORT_BIND_MS = 5000L
private const val PAIRING_NOTIFICATIONS = 1405

/** Feasibility UI: independent engine checks and explicit, fixed device probes. */
class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val updateWorker = Executors.newSingleThreadExecutor()
    private var checkingUpdate = false
    private var updateDialog: AlertDialog? = null
    private lateinit var home: GuidedHome
    private val actions = mutableMapOf<String, () -> Unit>()
    private lateinit var output: TextView
    private lateinit var workerStatus: TextView
    private val statusHandler = Handler(Looper.getMainLooper())
    private val refreshStatus = object : Runnable {
        override fun run() {
            val file = File(filesDir, "worker-state.json")
            workerStatus.text = if (!file.isFile) "No saved worker result." else runCatching {
                WorkerStatus.describe(JSONObject(String(DurableFiles.readCommitted(file), Charsets.UTF_8)))
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
    /** The automatic flow ends in Remove translation rather than a patch. */
    private var removing = false
    /** The automatic flow ends in Re-download damaged files rather than a patch. */
    private var redownloading = false
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
        // Sticky: every new activity hears it, so a recreated screen or a restarted process binds again.
        runOnUiThread { if (ensurePermission()) connect() }
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
                home.message("Access was not allowed. Tap Start to try again.", failure = true)
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
        removing = automatic && state?.getBoolean("removing") == true
        redownloading = automatic && state?.getBoolean("redownloading") == true
        home = GuidedHome(this) { key ->
            DiagnosticTrace.event("ui", "Tap $key; busy $busy automatic $automatic provider ${provider().key} " +
                "shizuku ${Shizuku.pingBinder()}")
            when (key) {
                "check_update" -> checkAppUpdate()
                "start" -> beginAutomatic()
                "remove" -> if (!PristineDelta.held(this)) {
                    home.message("This patcher has no record of a translation on this phone, so there is nothing to remove.")
                } else if (!busy && !automatic && !PatchWorkerService.isWorking) {
                    removing = true
                    beginAutomatic()
                }
                "redownload" -> if (!busy && !automatic && !PatchWorkerService.isWorking) {
                    redownloading = true
                    beginAutomatic()
                }
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
                "pair" -> pairWireless()
                "provider:shizuku", "provider:wireless", "provider:root" -> {
                    val chosen = ShellProvider.of(key.removePrefix("provider:"))
                    if (busy || automatic || PatchWorkerService.isWorking) home.provider(provider())
                    else runCatching { ShellProvider.set(this, chosen) }
                        .onSuccess {
                            log("Shell provider: ${chosen.label}")
                            home.provider(chosen)
                            if (ensurePermission()) connect()
                            refreshHome()
                        }
                        .onFailure { log("ERROR: ${it.message}"); home.provider(provider()) }
                }
                "free_space" -> if (busy || automatic || PatchWorkerService.isWorking) {
                    home.message("Finish the current work before freeing space.")
                } else showFreeSpaceConfirmation()
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
                    else home.message("The game is not installed. Install it before preparing files.", failure = true)
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
        home.provider(provider())
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
        LauncherShortcuts.publish(this)
        // A restored or recreated activity already acted on its shortcut.
        if (state == null) LauncherShortcuts.action(intent)?.let { shortcut(it, SHORTCUT_TRIES) }
    }

    /**
     * Act on launcher shortcut <key> after the screen's first refresh. A cold start reaches here before
     * Shizuku's binder does, so Start waits for it (up to [SHORTCUT_TRIES] checks) rather than sending the
     * player to Shizuku while it is running.
     */
    private fun shortcut(key: String, tries: Int) {
        statusHandler.postDelayed({
            if (destroyed) return@postDelayed
            if (key == "start" && usesShizuku() && !Shizuku.pingBinder() && tries > 1) shortcut(key, tries - 1)
            else home.shortcut(key)
        }, SHORTCUT_WAIT_MS)
    }

    /** The provider a run started now would use; the worker reads the same choice. */
    private fun provider() = ShellProvider.current(this)

    private fun usesShizuku() = provider() == ShellProvider.SHIZUKU

    /** A running Shizuku server whose uid is root: its worker would take the Root provider's write path. */
    private fun shizukuAsRoot() = runCatching { Shizuku.pingBinder() && Shizuku.getUid() == WorkerAccess.ROOT_UID }.getOrDefault(false)

    /** Ask Shizuku for access, only while Shizuku is the chosen provider and runs as shell. */
    private fun ensurePermission(): Boolean {
        return try {
            if (!usesShizuku() || !Shizuku.pingBinder() || shizukuAsRoot()) return false
            if (Shizuku.isPreV11()) { stopAutomatic(); home.message("Update Shizuku before starting.", failure = true); return false }
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) return true
            if (!permissionRequested) {
                permissionRequested = true
                Shizuku.requestPermission(1)
            }
            false
        } catch (error: Exception) { stopAutomatic(); log("ERROR: ${error.message}"); false }
    }

    private fun checkAppUpdate() {
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

    private fun beginAutomatic() {
        if (busy || PatchWorkerService.isWorking || awaitingToken != null) return
        automatic = true
        permissionRequested = false
        val provider = provider()
        if (!provider.available) {
            stopAutomatic(); home.message(notReady(provider), failure = true); return
        }
        if (provider == ShellProvider.WIRELESS) wirelessRefusal()?.let {
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
    private fun wirelessRefusal(): String? = when {
        !WirelessDebugging.onWifi(this) -> WirelessDebugging.NO_WIFI
        !WirelessDebugging.paired(this) -> WirelessDebugging.NOT_PAIRED
        !WirelessDebugging.switchedOn(this) -> WirelessDebugging.SWITCHED_OFF
        else -> null
    }

    /** Post the notification that takes the pairing code, then open Wireless debugging for its code. */
    private fun pairWireless() {
        if (busy || automatic || PatchWorkerService.isWorking) return
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
    private fun notReady(provider: ShellProvider) = UiText.string(this, "provider_not_ready", "provider" to ui(provider.label))

    private fun stopAutomatic() { automatic = false; removing = false; redownloading = false; awaitingToken = null; awaitingAction = null; waitingForShizuku = false; waitingForDownloads = null }

    private fun openShizuku() {
        if (!ShizukuLauncher.open(this)) {
            stopAutomatic()
            home.message("Cannot open Shizuku or Google Play. Install Shizuku from play.google.com, start it, then return here.", failure = true)
        }
    }

    /** Only the Start action arms continuation; opening the app never starts game changes. */
    private fun routeAutomatic() {
        if (!automatic || busy || destroyed || awaitingToken != null || PatchWorkerService.isWorking) return
        if (usesShizuku()) {
            if (!Shizuku.pingBinder()) { waitingForShizuku = true; return }
            if (!ensurePermission()) return
        }
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
                        home.message("More than one unfinished run was found. Choose the correct run in recovery options.", failure = true)
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
            else JSONObject(String(DurableFiles.readCommitted(file), Charsets.UTF_8))
    }

    private fun advanceAutomatic() {
        if (!automatic || busy || destroyed) return
        if (awaitingToken != null && PatchWorkerService.isWorking) return
        val result = runCatching { savedWorker() }.getOrElse {
            stopAutomatic(); home.message("Saved progress cannot be read. Keep the game closed and save a log for help.", failure = true); return
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
                stopAutomatic()
                home.message(UiText.string(this, "work_could_not_start_check_provider", "provider" to ui(provider().label)), failure = true)
                return
            }
            if (!PatchWorkerService.isWorking && result?.optString("flow") == awaitingToken &&
                result?.optString("status") == "running") {
                val latest = runCatching { savedWorker() }.getOrNull()
                if (latest?.optString("status") != "running" || PatchWorkerService.isWorking) return
                stopAutomatic(); home.message("Work was interrupted. Tap Start to check and restore unfinished work.", failure = true)
            }
            return
        }
        awaitingToken = null; awaitingAction = null
        when (result!!.getString("status")) {
            "prepared" -> if (result.optBoolean("root")) {
                // Root installs no APK: no first setup, and the confirmation binds only the saved copy of the game app.
                runTask {
                    val prepared = ApkPreparation(this).loadRoot(result.getString("preparation"))
                    val confirm = { checked: Boolean -> PatchRequestStore(this).confirmRoot(prepared, checked) }
                    runOnUiThread {
                        if (!automatic || destroyed) return@runOnUiThread
                        if (redownloading) showRedownloadConfirmation(confirm)
                        else showPatchConfirmation(confirm, removing, root = true)
                    }
                }
            } else {
                runTask {
                    val prepared = ApkPreparation(this).load(result.getString("preparation"))
                    val confirm = { checked: Boolean -> PatchRequestStore(this).confirm(prepared, checked) }
                    runOnUiThread {
                        if (!automatic || destroyed) return@runOnUiThread
                        if ((removing || redownloading) && prepared.requiresSignatureConversion) {
                            stopAutomatic()
                            home.message("The game on this phone is the official build, which this patcher never translated, so there is nothing to remove.")
                        } else if (prepared.requiresSignatureConversion) showFirstSetupConfirmation(prepared)
                        else if (redownloading) showRedownloadConfirmation(confirm)
                        else showPatchConfirmation(confirm, removing)
                    }
                }
            }
            "verified", "recovered", "setup_ready", "setup_waiting" -> routeAutomatic()
            // The translation is on the phone; patching again is the user's call, not automatic.
            "recovered_unconfirmed" -> stopAutomatic()
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
        // Unreadable records (null) keep every recovery action; a stop with no records offers none.
        val material = runCatching { RecoveryMaterial.read(this) }.getOrNull()
        val recoverable = material?.any ?: true
        home.recoveryActions(material)
        val messages = state?.optJSONArray("messages")
        home.logs(if (messages == null) emptyList() else
            (0 until messages.length()).map { messages.optString(it) })
        val live = PatchWorkerService.isWorking || awaitingToken != null
        val provider = provider()
        val shizuku = provider == ShellProvider.SHIZUKU
        // Once a run is under way, Shizuku's dialog is behind us: ask for notifications now, once.
        if (PatchWorkerService.isWorking && RunNotification.askOnce(this))
            home.message("Allow notifications to see the patch's progress and hear when it is done.")
        val result = state?.let { UiText.result(PatchLanguage.current(this), it) }
        // An older record without a step still shows its line.
        val step = state?.takeIf { live }?.let { UiText.step(PatchLanguage.current(this), it) }
        when {
            // The step names where the run is; its free-text line is in the log.
            live -> home.show("Working on your game", step?.line ?: UiText.progress(this, state?.optString("progress",
                "Checking and preparing files…") ?: "Checking and preparing files…"), "Please wait", "start", false, GuidedHome.Stage.WORKING)
            busy && automatic -> home.show("Checking game files", "Please wait. We are checking the saved game app and recovery files.", "Please wait", "start", false, GuidedHome.Stage.WORKING)
            pending.isFailure -> home.show("Recovery needs attention", "Keep the game closed. Save a log for help.", "Save log for help", "export", true, GuidedHome.Stage.ATTENTION)
            !provider.available -> home.show("Choose a shell provider", notReady(provider), "Start", "start",
                pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            provider == ShellProvider.WIRELESS && !WirelessDebugging.onWifi(this) -> home.show("Connect to Wi-Fi",
                WirelessDebugging.NO_WIFI, "Start", "start", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            provider == ShellProvider.WIRELESS && !WirelessDebugging.paired(this) -> home.show("Pair wireless debugging",
                "Turn on Wireless debugging, tap Pair, then type the pairing code into the patcher's notification.",
                "Pair", "pair", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            shizuku && !Shizuku.pingBinder() && !ShizukuLauncher.isInstalled(this) -> home.show("Install Shizuku", "Shizuku is required. Install it from Google Play, start it, then return here.", "Get Shizuku", "start", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            shizuku && !Shizuku.pingBinder() -> home.show("Start Shizuku", "Shizuku must be running. Start it, then return here. We will continue automatically.", "Open Shizuku", "start", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            shizuku && shizukuAsRoot() -> home.show("Choose a shell provider", ShellProvider.SHIZUKU_AS_ROOT, "Start", "start",
                pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            // Space freed hands back plain Start; the other results offer another patch.
            result != null && !pending.getOrThrow() -> home.result(result,
                if (state.optString("status") == "space_freed") "Start" else "Start another patch")
            // The engine's refusal for an update stuck on translated files: ③ offers Re-download instead of a retry.
            state?.optString("status") == "error" && state.optString("error").contains(UPDATE_STUCK) ->
                home.show("The game update is stuck", "The game could not update the files this patcher translated. " +
                    "Re-download them: only those game files are deleted, and the game downloads them again. The rest of the game data is kept.",
                    "Re-download damaged files", "redownload", false, GuidedHome.Stage.ATTENTION)
            // Packages an update rewrote around the translation: the same way out as a stuck update.
            state?.optString("status") == "error" && state.optString("error").contains(UPDATE_MIXED) ->
                home.show("Some game files are still translated", "A game update kept part of the earlier translation in some game files, so the patcher cannot restore them. " +
                    "Re-download them: only those game files are deleted, and the game downloads them again. The rest of the game data is kept.",
                    "Re-download damaged files", "redownload", false, GuidedHome.Stage.ATTENTION)
            state?.optString("status") == "error" && state.optString("error").contains(UPDATE_WAITING) ->
                home.show("Finish the game update", "Open the game and let it finish the update to the login screen. Close it, then tap Start to patch again.",
                    "Open game", "game", false, GuidedHome.Stage.ATTENTION)
            // With recovery on offer, ③ opens it rather than asking to try again against the recovery card.
            state?.optString("status") in setOf("error", "recovery_required") -> home.show("Work stopped",
                friendlyFailure(state?.optString("error").orEmpty(), recoverable),
                if (recoverable) "Open recovery options" else "Try again", if (recoverable) "recovery_options" else "start",
                recoverable, GuidedHome.Stage.ATTENTION)
            pending.getOrThrow() -> home.show("Finish your game safely", "We will check unfinished work and recover it before patching.", "Continue", "start", true, GuidedHome.Stage.ATTENTION)
            else -> home.show("Ready when you are", "Tap Start. We will check your game and prepare everything. Keep the game closed while we work.", "Start", "start", false)
        }
        home.working(busy || live || (automatic && !waitingForShizuku))
        home.languageEnabled(!busy && !live && !automatic)
        home.providerEnabled(!busy && !live && !automatic)
        home.progress(live || (busy && automatic), step)
        buttons.forEach { it.isEnabled = !busy && !live && !automatic }
        home.resultMessage(if (!automatic && state?.optString("status") in setOf("error", "recovery_required") &&
            listOf(UPDATE_STUCK, UPDATE_MIXED, UPDATE_WAITING).none { state?.optString("error").orEmpty().contains(it) })
            friendlyFailure(state?.optString("error").orEmpty(), recoverable) else "")
        home.errorDetails(when {
            live -> ""
            // The worker's own raw error first: the automatic flow also logs it, already explained, as an ERROR.
            state?.optString("status") in setOf("error", "recovery_required") -> state?.optString("error").orEmpty()
            else -> lastTaskError
        })
    }

    private fun friendlyFailure(message: String,
                                recoverable: Boolean = runCatching { RecoveryMaterial.read(this).any }.getOrDefault(true)): String {
        StorageBudget.explainFailure(message, filesDir.usableSpace)?.let { return UiText.storage(this, it) }
        if (message.contains("GB free for this step")) return UiText.storage(this, message.removePrefix("ERROR: "))
        return when {
            // The engine's way out it cannot avoid; its path names Android's Storage page, not a lack of space.
            message.contains(CLEAR_DATA) ->
                "The patcher cannot restore the untranslated game files. Clear the game's data in Android Settings, open the game and let it download again to the login screen, close it, then tap Start. Open Technical tools for the reason."
            message.contains("space", true) || message.contains("storage", true) ->
                ui("Free now:") + " ${StorageBudget.freeSpaceLabel(filesDir.usableSpace)}.\n" +
                    ui("The phone did not report how much more space is needed. Free space elsewhere and retry. Keep saved recovery files.")
            message.contains(ShellProvider.SHIZUKU_AS_ROOT) -> ShellProvider.SHIZUKU_AS_ROOT
            WirelessDebugging.REFUSALS.any { message.contains(it) } -> WirelessDebugging.REFUSALS.first { message.contains(it) }
            RootWorkerStarter.REFUSALS.any { message.contains(it) } -> RootWorkerStarter.REFUSALS.first { message.contains(it) }
            message.contains(PatchCoordinator.ROOT_ACCESS_INSTALLED) -> PatchCoordinator.ROOT_ACCESS_INSTALLED
            message.contains(PatchCoordinator.OTHER_PROVIDER) -> PatchCoordinator.OTHER_PROVIDER
            // A run's lost root: the root manager revoked HOK ACE, or its su ended.
            provider() == ShellProvider.ROOT && message.contains("disconnected", true) -> if (recoverable)
                "Root access stopped. Keep the game closed. Check HOK ACE in your root manager, then check recovery options below."
                else "Root access stopped. Keep the game closed. Check HOK ACE in your root manager, then tap Try again."

            // A run's lost connection: Wi-Fi or wireless debugging went off under it.
            provider() == ShellProvider.WIRELESS && message.contains("disconnected", true) -> if (recoverable)
                "Wireless debugging disconnected. Keep the game closed. Turn Wi-Fi and Wireless debugging back on, then check recovery options below."
                else "Wireless debugging disconnected. Keep the game closed. Turn Wi-Fi and Wireless debugging back on, then tap Try again."
            message.contains("Worker connection timed out") -> if (usesShizuku())
                "Shizuku is running, but the patcher's helper did not start. Open Shizuku, stop it and start it again, then return here and tap Try again. If it happens again, save a log for help. Keep the game closed."
                else "The patcher's helper did not start. Tap Try again. If it happens again, save a log for help. Keep the game closed."
            message.contains(PrivilegedDeviceService.GAME_MISSING) -> when (FirstSetupPackagePolicy.missingReason(message)) {
                FirstSetupPackagePolicy.Missing.HIDDEN ->
                    "The game is installed but hidden or switched off in this phone's main space, for example by Hide apps. Show it again, open it once, close it, then tap Try again."
                FirstSetupPackagePolicy.Missing.OTHER_PROFILE_ONLY ->
                    "The game is installed only in Dual App. Install it in the phone's main space too, open it once and finish all downloads, close it, then tap Try again."
                FirstSetupPackagePolicy.Missing.ABSENT ->
                    "The game is not installed in this phone's main space. Install it there (Dual App alone is not enough), open it once and finish all downloads, close it, then tap Try again."
            }
            message.contains(FirstSetupPackagePolicy.OTHER_PROFILE) ->
                "The game is also installed in another Android profile, such as Dual App or a work profile. Remove it from that profile, then tap Try again. Keep the game closed."
            message.contains(FirstSetupPackagePolicy.UNCHECKED_PROFILE) ->
                "This phone has another Android profile, such as Dual App, that could not be checked for the game. Remove the game from Dual App, then tap Try again. If it happens again, save a log for help. Keep the game closed."
            message.contains(InstalledGameVerifier.DIFFERENT_APP) ->
                "The installed game app is not the saved app this check looks for. It is a different app, not a damaged one. If no patch was started, tap Try again. Otherwise check recovery options below, or save a log for help. Keep the game closed."
            message.contains("USER_RESTRICTED", true) ->
                "The phone blocked installation. Unlock it and accept the install prompt. Open Technical tools for the full error."
            // The command ran, so the shell provider is working; the phone itself refused the step.
            message.contains("Device command failed") -> UiText.string(this,
                if (recoverable) "phone_refused_step_check_recovery" else "phone_refused_step_try_again", "provider" to ui(provider().label))
            message.contains("Shizuku", true) || message.contains("permission", true) ||
                message.contains("disconnected", true) || message.contains("is not available in this build") -> when {
                    !provider().available -> notReady(provider())
                    usesShizuku() -> "Open Shizuku. Start it and allow HOK ACE. Return here and retry. Keep the game closed."
                    else -> UiText.string(this, "work_could_not_start_check_provider", "provider" to ui(provider().label))
                }
            else -> if (recoverable) "Work stopped. Keep the game closed. Check recovery options below, or save a log for help."
                else "Work stopped. Keep the game closed. Tap Try again, or save a log for help."
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
                        runOnUiThread { showPatchConfirmation({ PatchRequestStore(this).confirm(prepared, it) }) }
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
    private fun showFreeSpaceConfirmation() {
        val saved = listOf("preparations", "recovery").sumOf { name ->
            File(filesDir, name).walkTopDown().filter { it.isFile }.sumOf { it.length() }
        }
        val apk = File(filesDir, "recovery").walkTopDown().filter { it.name == "normal.apk" }
            .maxOfOrNull { it.length() } ?: 0L
        val remove = CheckBox(this).apply {
            tag = "free-space-remove-apks"
            text = UiText.removeSavedApks(this@MainActivity, saved, StorageBudget.required(apk, apk, apk, apk))
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
     * Re-download damaged files deletes the translated packages a stuck game update names. The update has
     * not finished, so its checkbox asks only that the game is closed; the request store records the
     * same consent field a patch does.
     */
    private fun showRedownloadConfirmation(confirm: (Boolean) -> String): AlertDialog {
        val confirmation = CheckBox(this).apply { tag = "redownload-confirmation"; text = ui("I closed the game") }
        val dialog = AlertDialog.Builder(this).setTitle(ui("Re-download damaged files"))
            .setMessage(UiText.redownloadConfirmation(this))
            .setView(confirmation).setNegativeButton(ui("Cancel")) { _, _ -> stopAutomatic() }.setOnCancelListener { stopAutomatic() }
            .setPositiveButton(ui("Delete and re-download"), null).create()
        dialog.show()
        PanelDialog.style(dialog)
        val start = dialog.getButton(AlertDialog.BUTTON_POSITIVE); start.isEnabled = false
        confirmation.setOnCheckedChangeListener { _, checked -> start.isEnabled = checked }
        start.setOnClickListener {
            if (!busy) {
                dialog.dismiss()
                runTask {
                    val request = confirm(confirmation.isChecked)
                    runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                        .setAction("redownload").putExtra("request", request)) }
                }
            }
        }
        return dialog
    }

    /**
     * <remove> asks to confirm Remove translation, which writes the original game files back instead. <confirm>
     * records the checked confirmation and returns its request; <root> words it for a run that keeps the game app.
     */
    private fun showPatchConfirmation(confirm: (Boolean) -> String, remove: Boolean = false,
                                      root: Boolean = false): AlertDialog {
        val confirmation = CheckBox(this).apply {
            tag = "update-confirmation"; text = ui("All in-game updates finished, and I closed the game")
        }
        val dialog = AlertDialog.Builder(this).setTitle(ui(if (remove) "Remove translation" else "Start translation"))
            .setMessage(if (remove) UiText.removeConfirmation(this, root) else UiText.patchConfirmation(this, root))
            .setView(confirmation).setNegativeButton(ui("Cancel")) { _, _ -> stopAutomatic() }.setOnCancelListener { stopAutomatic() }
            .setPositiveButton(ui(if (remove) "Remove the translation" else "Start patch"), null).create()
        dialog.show()
        PanelDialog.style(dialog)
        run {
            val start = dialog.getButton(AlertDialog.BUTTON_POSITIVE); start.isEnabled = false
            confirmation.setOnCheckedChangeListener { _, checked -> start.isEnabled = checked }
            start.setOnClickListener {
                if (!busy) {
                    dialog.dismiss()
                    runTask {
                        val request = confirm(confirmation.isChecked)
                        runOnUiThread { startWorker(Intent(this, PatchWorkerService::class.java)
                            .setAction(if (remove) "remove" else "patch").putExtra("request", request)) }
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

    override fun onResume() { super.onResume(); shown = true; DiagnosticTrace.event("ui", "Activity resumed"); statusHandler.post(refreshStatus) }
    override fun onPause() { shown = false; DiagnosticTrace.event("ui", "Activity paused"); statusHandler.removeCallbacks(refreshStatus); super.onPause() }

    companion object {
        /** True while the patcher is on screen; a finished run then posts no notification. */
        @Volatile var shown = false
        /**
         * The engine's refusals that open Re-download and the update wait (`android_bridge.UPDATE_STUCK`,
         * `UPDATE_MIXED`, `UPDATE_WAITING`), and the start of its clear-data advice (`CLEAR_DATA`).
         */
        const val UPDATE_STUCK = "The game's update stopped on translated files"
        const val UPDATE_MIXED = "A game update kept part of this patcher's translation"
        const val CLEAR_DATA = "Clear the game's data (Android Settings"
        const val UPDATE_WAITING = "The game has not downloaded the re-downloaded files yet"
    }

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
            val device = awaitService()
            checkNotNull(contentResolver.openOutputStream(uri, "wt")).bufferedWriter().use { output ->
                DiagnosticLogExport(this, device).write(output)
            }
            log("Diagnostic logs exported to the selected document")
        }
    }
    /**
     * The export's shell view needs the activity's service: bind it now if Shizuku is running and allowed,
     * and wait up to [EXPORT_BIND_MS] for it. Worker thread only. Null means the export goes without it.
     */
    private fun awaitService(): IPrivilegedDeviceService? {
        service?.let { return it }
        val allowed = runCatching { Shizuku.pingBinder() && !shizukuAsRoot() &&
            Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED }.getOrDefault(false)
        if (!allowed) return null
        runOnUiThread { connect() }
        val deadline = System.currentTimeMillis() + EXPORT_BIND_MS
        while (service == null && System.currentTimeMillis() < deadline && !destroyed) Thread.sleep(100)
        DiagnosticTrace.event("ui", "Export bound activity UserService on demand: ${service != null}")
        return service
    }

    private fun connect() {
        if (service != null) return
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
                if (message.startsWith("ERROR:") || message.startsWith("Cannot ") || message.startsWith("Prepare game") || message.startsWith("No ")) {
                    val failure = message.startsWith("ERROR:") || message.startsWith("Cannot ")
                    home.message(if (failure) friendlyFailure(message) else message, failure)
                }
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
        state.putBoolean("removing", removing)
        state.putBoolean("redownloading", redownloading)
        state.putString("automatic-token", awaitingToken)
        state.putString("automatic-action", awaitingAction)
        state.putLong("automatic-since", awaitingSince)
        super.onSaveInstanceState(state)
    }
    override fun onDestroy() {
        DiagnosticTrace.event("ui", "Activity destroyed; changing configuration $isChangingConfigurations")
        destroyed = true
        updateDialog?.dismiss()
        updateWorker.shutdownNow()
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
