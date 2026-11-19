package dev.halixm.hokacepatcher

import android.app.Activity
import android.content.Intent
import android.content.ComponentName
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.IBinder
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.widget.Button
import android.widget.ScrollView
import android.widget.TextView
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import rikka.shizuku.Shizuku
import java.io.File
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import org.json.JSONObject

/** A launcher shortcut's Start waits for Shizuku's binder this many times, this long apart (3 s in all). */
private const val SHORTCUT_TRIES = 15
private const val SHORTCUT_WAIT_MS = 200L
private const val EXPORT_BIND_MS = 5000L
private const val PAIRING_NOTIFICATIONS = 1405

/** Feasibility UI: independent engine checks and explicit, fixed device probes. */
class MainActivity : Activity() {
    // Members marked internal are used by MainActivityDialogs.kt and AppUpdatePrompt.kt (tech-debt ticket 02).
    private val worker = Executors.newSingleThreadExecutor()
    private val updateCheck = AppUpdatePrompt(this)
    internal lateinit var home: GuidedHome
        private set
    private val actions = mutableMapOf<String, () -> Unit>()
    private lateinit var output: TextView
    private lateinit var workerStatus: TextView
    private val statusHandler = Handler(Looper.getMainLooper())
    private var nextStorageCheck = 0L
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
            resumeStorageWait()
            statusHandler.postDelayed(this, 1000)
        }
    }
    private val buttons = mutableListOf<Button>()
    @Volatile private var service: IPrivilegedDeviceService? = null
    /** Raw text of the newest `ERROR:` an on-screen task logged; cleared when the next task starts. */
    private var lastTaskError = ""
    @Volatile internal var destroyed = false
        private set
    private val tasks = UiTaskRunner(
        execute = { worker.execute(it) }, postUi = { runOnUiThread(it) },
        started = {
            lastTaskError = ""
            home.working(true)
            buttons.forEach { it.isEnabled = false }
        },
        failed = { error ->
            DiagnosticTrace.error("ui", "Task failed", error)
            runOnUiThread { stopAutomatic() }; log("ERROR: ${error.message}")
        },
        finished = { if (!destroyed) refreshHome() },
    )
    internal val busy: Boolean get() = tasks.busy
    internal var automatic = false
        private set
    /** The automatic flow ends in Remove translation rather than a patch. */
    internal var removing = false
    /** The automatic flow ends in Re-download damaged files rather than a patch. */
    private var awaitingToken: String? = null
    private var awaitingAction: String? = null
    private var permissionRequested = false
    private var waitingForShizuku = false
    private var awaitingSince = 0L
    internal var waitingForDownloads: String? = null
    /** Stop safely was tapped: only safety recovery and closing the stopped record may run until it ends. */
    private var stopping = false
    /** A saved action waits for its own provider (Wi-Fi, pairing, Wireless debugging) to come back while open. */
    private var waitingForAccess = false
    /** The flow resumes an approved saved action (reopen, retry or its own button): ③ says Continuing, not Working. */
    private var continuing = false
    /** The flow came from Recovery needs attention's button: it recovers or continues, never prepares a fresh patch. */
    private var recoveryOnly = false
    /** The one unresolved saved Start, re-read every refresh; its provider and choices are locked until it resolves. */
    @Volatile internal var savedRun: RunStore.Run? = null
        private set
    /** The exact scope rendered on the card; a tap must never approve a newer, unseen plan. */
    private var shownRedownload: Pair<String, String>? = null
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
        waitingForAccess = state?.getBoolean("waiting-access") ?: false
        automatic = (awaitingToken != null || waitingForShizuku || waitingForDownloads != null || waitingForAccess) &&
            state?.getBoolean("automatic") == true
        stopping = automatic && state?.getBoolean("stopping") == true
        continuing = automatic && state?.getBoolean("continuing") == true
        recoveryOnly = automatic && state?.getBoolean("recovery-only") == true
        loadSavedRun()
        removing = automatic && state?.getBoolean("removing") == true
        home = GuidedHome(this) { key ->
            DiagnosticTrace.event("ui", "Tap $key; busy $busy automatic $automatic provider ${provider().key} " +
                "shizuku ${Shizuku.pingBinder()}")
            when (key) {
                "check_update" -> updateCheck.checkAppUpdate()
                "start" -> beginAutomatic(explicit = true)
                // The explicit Remove: one plain dialog at the tap, then no further question (ticket 13).
                "remove" -> if (!PristineDelta.held(this)) {
                    home.message("This patcher has no record of a translation on this phone, so there is nothing to remove.")
                } else if (!busy && !automatic && !PatchWorkerService.isWorking && savedRun == null) {
                    showRemoveConfirmation()
                }
                // Recovery needs attention: ③'s button recovers or continues the saved action, never a fresh patch.
                "recover_attention" -> if (!busy && !automatic && !PatchWorkerService.isWorking) {
                    loadSavedRun()
                    recoveryOnly = true
                    stopping = savedRun?.stopRequested == true
                    removing = savedRun?.action == "remove"
                    beginAutomatic(explicit = true)
                }
                // The saved action's own scoped answer (ticket 12): never a new Re-download action.
                "redownload" -> if (!busy && !automatic && !PatchWorkerService.isWorking) reviewRedownload()
                "redownload_finished" -> if (!busy && !automatic && !PatchWorkerService.isWorking) confirmDownloads()
                "redownload_game" -> if (!busy && !automatic && !PatchWorkerService.isWorking) openDownloadGame()
                // The tap is the instruction: no second confirmation (ticket 11).
                "stop" -> requestStop()
                "shizuku" -> {
                    if (!Shizuku.pingBinder()) {
                        openShizuku()
                    } else actions["Authorize Shizuku"]?.let { runTask(it) }
                }
                "recovery_options" -> home.showRecovery()
                "pair" -> pairWireless()
                "provider:shizuku", "provider:wireless", "provider:root" -> {
                    val chosen = ShellProvider.of(key.removePrefix("provider:"))
                    // A saved action keeps the provider it was started with until Stop safely resolves it.
                    if (busy || automatic || PatchWorkerService.isWorking || savedRun != null) home.provider(provider())
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
                    if (busy || automatic || PatchWorkerService.isWorking || savedRun != null) home.language(PatchLanguage.current(this))
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
        if (state == null && !automatic) resumeSavedAction()
    }

    /**
     * Startup and reconnect (spec Q1). A live worker for the one saved action is attached to, never started
     * twice. Without one, [AutomaticRoute.onLaunch] decides from durable records only: a saved Stop finishes its
     * safety recovery and closes, an approved setup is recovered install-only, and a Start that may continue
     * resumes within its retry budget. A clean idle screen or a saved status starts nothing.
     */
    private fun resumeSavedAction() {
        val runs = runCatching { RunStore(this).pending() }.getOrNull() ?: return
        val setups = runCatching { FirstSetupJournal.pending(this) }.getOrNull() ?: return
        val run = runs.singleOrNull()
        val saved = run?.let { AutomaticRoute.Saved(it.id, it.action, it.lifecycle, it.mayContinue, it.stopRequested,
            it.retryExhausted, runCatching { FirstSetupJournal.readyFor(this, it.id) }.getOrDefault(false)) }
        val launch = AutomaticRoute.onLaunch(saved, runs.size, setups.map {
            AutomaticRoute.Setup(it.id, it.phase == FirstSetupPhase.WAITING_FOR_GAME_UPDATE) })
        if (launch == AutomaticRoute.Launch.NONE) return
        if (launch != AutomaticRoute.Launch.STOP && run?.waiting == "storage") {
            val result = runCatching { savedWorker() }.getOrNull()
            val needed = result?.takeIf { it.optString("run") == run.id }
                ?.optJSONObject("storage_wait")?.optLong("required_bytes", -1) ?: -1L
            if (needed <= 0 || filesDir.usableSpace < needed) return
        }
        if (launch != AutomaticRoute.Launch.STOP && run?.mayContinue == true && run.sourceDownloads == "required") return
        // A saved action waiting for the game's download, or for a Re-download review the loop guard held back,
        // starts nothing at launch; its card asks (ticket 12). An approved plan, automatic since the user's
        // decision of 2026-11-13, resumes like any saved action.
        if (launch != AutomaticRoute.Launch.STOP && run?.mayContinue == true && run.redownload?.let {
                it.needsAnswer || it.state == RedownloadConsent.DELETED } == true) return
        removing = run?.action == "remove"
        stopping = launch == AutomaticRoute.Launch.STOP
        continuing = launch == AutomaticRoute.Launch.CONTINUE
        val worker = runCatching { savedWorker() }.getOrNull()
        if (PatchWorkerService.isWorking) {
            val flow = worker?.optString("flow").orEmpty()
            if (run == null || worker?.optString("run") != run.id || flow.isEmpty()) { stopping = false; continuing = false; return }
            continuing = true
            automatic = true; awaitingToken = flow; awaitingAction = worker.optString("action")
            awaitingSince = android.os.SystemClock.elapsedRealtime()
            stopping = stopping || worker.optBoolean("stopping")
            DiagnosticTrace.event("ui", "Attached to the live worker of the saved action")
            return
        }
        DiagnosticTrace.event("ui", "Resuming the saved action after restart: $launch")
        // Never opens another app at launch: a stopped Shizuku is waited for, as after a tap on Start.
        if (usesShizuku() && !Shizuku.pingBinder()) { automatic = true; waitingForShizuku = true; return }
        beginAutomatic()
    }

    /** Re-read the one unresolved saved Start; unreadable or ambiguous records leave no saved provider override. */
    private fun loadSavedRun() {
        // A momentarily held store lock keeps the last reading rather than falling back to the picker's provider.
        runCatching { RunStore(this).pending() }.onSuccess { savedRun = it.singleOrNull() }
    }

    /** Persist Stop for <id>, retrying briefly while the worker holds the short store lock; false if never saved. */
    private fun saveStop(id: String): Boolean {
        repeat(5) { attempt ->
            if (runCatching { RunStore(this).stop(id) }.onFailure { DiagnosticTrace.error("ui", "Stop save attempt $attempt", it) }
                    .isSuccess) return true
            Thread.sleep(20)
        }
        return false
    }

    /**
     * Stop safely. Saved first (continuation off), shown at once as Stopping safely with the button disabled,
     * then the worker is told; it stops at its next safe boundary and restores consistency. Without a worker the
     * flow runs only safety recovery and closes the stopped record. It stays stopped across reopen.
     */
    private fun requestStop() {
        if (stopping) return
        val run = runCatching { RunStore(this).pending().singleOrNull() }.getOrNull()
        val saved = run?.let { saveStop(it.id) } ?: true
        DiagnosticTrace.event("ui", "Stop safely: saved $saved, run ${run?.id}, worker ${PatchWorkerService.isWorking}")
        loadSavedRun()
        if (!saved) home.message(UiText.string(this, "stop_not_saved"), failure = true)
        val worker = PatchWorkerService.isWorking
        if (run == null && !worker && awaitingToken == null) { stopAutomatic(); refreshHome(); return }
        waitingForShizuku = false; waitingForAccess = false; waitingForDownloads = null
        stopping = true; automatic = true
        if (worker) startService(Intent(this, PatchWorkerService::class.java).setAction("cancel"))
        else if (awaitingToken == null) routeAutomatic()
        refreshHome()
    }

    /** The Stop flow reached a state with nothing left to restore: the saved action stays stopped. */
    private fun finishStop() {
        stopAutomatic()
        loadSavedRun()
        home.message(UiText.string(this, "stopped_safely_note"))
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

    /** The saved action's own provider while one is unresolved, otherwise the one a new Start would use. */
    internal fun provider() = savedRun?.provider ?: ShellProvider.current(this)

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

    /**
     * <explicit> is a tap on Start or Try again: it re-arms the saved action's safe automatic retries (never Stop,
     * consent or an uninstall). A saved action whose provider is not ready waits for it while the app is open.
     */
    internal fun beginAutomatic(explicit: Boolean = false) {
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
    private fun wirelessRefusal(): String? = when {
        !WirelessDebugging.onWifi(this) -> WirelessDebugging.NO_WIFI
        !WirelessDebugging.paired(this) -> WirelessDebugging.NOT_PAIRED
        !WirelessDebugging.switchedOn(this) -> WirelessDebugging.SWITCHED_OFF
        else -> null
    }

    /** Post the notification that takes the pairing code, then open Wireless debugging for its code. */
    private fun pairWireless() {
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
    private fun notReady(provider: ShellProvider) = FailureText.notReady(this, provider)

    internal fun stopAutomatic() { automatic = false; removing = false; awaitingToken = null; awaitingAction = null; waitingForShizuku = false; waitingForDownloads = null; waitingForAccess = false; stopping = false; continuing = false; recoveryOnly = false }

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

    internal fun startWorker(intent: Intent) {
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

    private fun savedWorker(): JSONObject? {
        val file = File(filesDir, "worker-state.json")
        return if (!file.exists() && !File(file.path + ".bak").exists()) null
            else JSONObject(String(DurableFiles.readCommitted(file), Charsets.UTF_8))
    }

    /** Recheck only free bytes, with bounded polling. The coordinator rechecks before opening access. */
    private fun resumeStorageWait() {
        val now = android.os.SystemClock.elapsedRealtime()
        if (now < nextStorageCheck || automatic || busy || destroyed || PatchWorkerService.isWorking) return
        nextStorageCheck = now + 5_000
        val run = savedRun?.takeIf { it.mayContinue && !it.retryExhausted && it.waiting == "storage" } ?: return
        val result = runCatching { savedWorker() }.getOrNull() ?: return
        if (result.optString("run") != run.id || result.optString("reason") != "storage") return
        val needed = result.optJSONObject("storage_wait")?.optLong("required_bytes", -1) ?: return
        if (needed > 0 && filesDir.usableSpace >= needed) beginAutomatic()
    }

    private fun advanceAutomatic() {
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
    private fun continueStop(result: JSONObject) {
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
    private fun retryAutomatically(result: JSONObject?): Boolean {
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
    private fun failureClass(result: JSONObject?): String = when {
        result?.optString("error").orEmpty().contains("disconnected", true) -> "provider_lost"
        result?.optString("status") == "running" -> "interrupted"
        result?.optString("status") == "recovery_required" -> "recovery_required"
        result?.optString("status") == "cancelled" -> "cancelled"
        else -> "error"
    }

    /** Wait for the saved provider while the app is open; the reason is saved, and waiting is never an attempt. */
    private fun waitForAccess() { waitingForAccess = true; savedWaiting("provider") }

    private fun savedWaiting(reason: String?) {
        val run = savedRun?.takeIf { it.mayContinue && it.waiting != reason } ?: return
        runCatching { RunStore(this).waitFor(run.id, reason) }.onFailure { DiagnosticTrace.error("ui", "Waiting reason not saved", it) }
        loadSavedRun()
    }

    /** Ask again for data-loss consent on the same preparation, but only for a saved Start that may continue. */
    private fun freshSetupConsent(result: JSONObject) {
        val run = savedRun?.takeIf { it.mayContinue && it.action == "translate" }
        val preparation = result.optString("preparation")
        if (run == null || preparation.isEmpty()) { stopAutomatic(); log(WorkerStatus.describe(result)); return }
        runTask {
            val prepared = ApkPreparation(this).load(preparation)
            check(prepared.requiresSignatureConversion) { "This game is already converted; use the patch update checkpoint" }
            runOnUiThread { if (automatic && !destroyed) showFirstSetupConfirmation(prepared, run.id) }
        }
    }

    private fun refreshHome() {
        if (!::home.isInitialized) return
        shownRedownload = null
        loadSavedRun()
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
        val error = state?.optString("error").orEmpty()
        val stop = StopCard.decide(state?.optString("status"), error, pending.getOrNull(), recoverable)
        val stopLine = stop?.let { friendlyFailure(error, StopCard.pointsAtRecovery(it, recoverable)) }.orEmpty()
        // Durable Stop (the saved Start) or the worker's own record: either keeps Stopping safely on screen.
        // While the Stop waits for its provider, that provider's own instruction shows instead.
        val stopShown = (live || (automatic && !waitingForShizuku && !waitingForAccess)) && (stopping || savedRun?.stopRequested == true || state?.optBoolean("stopping") == true)
        // Recovery needs attention: ③'s one button is the required recovery action, never a fresh patch.
        val (attentionLabel, attentionKey) = attentionAction(material, pending.getOrNull())
        // Unreadable records count as pending: no wait is offered over them.
        val wait = savedRun.let { run -> StopCard.savedWait(state?.optString("status"), pending.getOrDefault(true),
            run?.mayContinue == true, run?.waiting, run?.sourceDownloads, run?.redownload?.needsAnswer == true,
            run?.redownload?.state) }
        when {
            // Stop is saved; the current step finishes or rolls back first, so the wait is explained, not hidden.
            stopShown -> home.show("Stopping safely", "Waiting for the current operation, then restoring the game safely.",
                "Stopping safely", "stop", false, GuidedHome.Stage.WORKING)
            // The step names where the run is; its free-text line is in the log. The heading names the state:
            // Restoring (safety recovery), Continuing (an approved saved action) or Working (fresh work).
            live -> home.show(when {
                    awaitingAction in RESTORE_ACTIONS -> UiText.string(this, "restoring_your_game")
                    continuing -> UiText.string(this, "continuing_saved_work")
                    else -> "Working on your game"
                }, step?.line ?: UiText.progress(this, state?.optString("progress",
                "Checking and preparing files…") ?: "Checking and preparing files…"), "Please wait", "start", false, GuidedHome.Stage.WORKING)
            busy && automatic -> home.show("Checking game files", "Please wait. We are checking the saved game app and recovery files.", "Please wait", "start", false, GuidedHome.Stage.WORKING)
            // Unreadable records: the recovery options are the action; Save log for help stays among them, secondary.
            pending.isFailure -> home.show("Recovery needs attention", "Keep the game closed. Use recovery first.", "Open recovery options", "recovery_options", true, GuidedHome.Stage.ATTENTION)
            !provider.available -> home.show("Choose a shell provider", notReady(provider), "Start", "start",
                pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            provider == ShellProvider.WIRELESS && !WirelessDebugging.onWifi(this) -> home.show("Connect to Wi-Fi",
                WirelessDebugging.NO_WIFI, "Start", "start", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            provider == ShellProvider.WIRELESS && !WirelessDebugging.paired(this) -> home.show("Pair wireless debugging",
                "Turn on Wireless debugging, tap Pair, then type the pairing code into the patcher's notification.",
                "Pair", "pair", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            provider == ShellProvider.WIRELESS && !WirelessDebugging.switchedOn(this) -> home.show("Turn on wireless debugging",
                "Wireless debugging is off. Turn it on in Developer options, then tap Start.", "Start", "start",
                pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            shizuku && !Shizuku.pingBinder() && !ShizukuLauncher.isInstalled(this) -> home.show("Install Shizuku", "Shizuku is required. Install it from Google Play, start it, then return here.", "Get Shizuku", "start", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            shizuku && !Shizuku.pingBinder() -> home.show("Start Shizuku", "Shizuku must be running. Start it, then return here. We will continue automatically.", "Open Shizuku", "start", pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            shizuku && shizukuAsRoot() -> home.show("Choose a shell provider", ShellProvider.SHIZUKU_AS_ROOT, "Start", "start",
                pending.getOrDefault(false), GuidedHome.Stage.ACCESS)
            // Space freed hands back plain Start; the other results offer another patch.
            // The saved action waits for the user (ticket 12): its scoped Re-download answer, or the game's download.
            // Only once nothing needs recovery: required recovery leads, below ([StopCard.savedWait]).
            wait == StopCard.Wait.STORAGE ->
                home.show(UiText.string(this, "free_up_space"),
                    friendlyFailure(error, false), UiText.string(this, "try_again"), "start", false, GuidedHome.Stage.ATTENTION)
            wait == StopCard.Wait.SOURCE_DOWNLOADS ->
                home.show(UiText.string(this, "redownload_download_title"), UiText.setupUpdate(this),
                    "Open game", "redownload_game", false, GuidedHome.Stage.ATTENTION,
                    UiText.string(this, "downloads_finished"), "redownload_finished")
            wait == StopCard.Wait.REDOWNLOAD_ANSWER -> {
                val run = requireNotNull(savedRun)
                val consent = requireNotNull(run.redownload)
                shownRedownload = run.id to consent.planSha256
                // Only the loop guard's fallback reaches this card: Re-download is otherwise approved automatically.
                val repeat = if (consent.packages.any { it in run.redownloadedPackages })
                    UiText.string(this, "redownload_repeat_review") + "\n\n" else ""
                home.show(UiText.string(this, "redownload_review_title"),
                    repeat + UiText.string(this, "redownload_review_scope", "files" to consent.files,
                        "size" to StorageBudget.freeSpaceLabel(consent.bytes),
                        "packages" to consent.packages.joinToString(", ")) + "\n\n" +
                        UiText.string(this, "redownload_review_consequences"),
                    UiText.string(this, "delete_and_redownload"), "redownload", false, GuidedHome.Stage.ATTENTION)
            }
            wait == StopCard.Wait.REDOWNLOAD_DOWNLOAD ->
                home.show(UiText.string(this, "redownload_download_title"), UiText.string(this, "redownload_download_body"),
                    "Open game", "redownload_game", false, GuidedHome.Stage.ATTENTION,
                    UiText.string(this, "downloads_finished"), "redownload_finished")
            result != null && !pending.getOrThrow() -> home.result(result,
                if (state.optString("status") == "space_freed") "Start" else "Start another patch")
            stop == StopCard.Exit.REDOWNLOAD_STUCK ->
                home.show("The game update is stuck", "The game could not update the files this patcher translated. " +
                    "Re-download them: only those game files are deleted, and the game downloads them again. The rest of the game data is kept.",
                    "Re-download damaged files", "redownload", false, GuidedHome.Stage.ATTENTION)
            stop == StopCard.Exit.REDOWNLOAD_MIXED ->
                home.show("Some game files are still translated", "A game update kept part of the earlier translation in some game files, so the patcher cannot restore them. " +
                    "Re-download them: only those game files are deleted, and the game downloads them again. The rest of the game data is kept.",
                    "Re-download damaged files", "redownload", false, GuidedHome.Stage.ATTENTION)
            stop == StopCard.Exit.WAIT_FOR_GAME ->
                home.show("Finish the game update", "Open the game and let it finish the update to the login screen. Close it, then tap Start to patch again.",
                    "Open game", "game", false, GuidedHome.Stage.ATTENTION)
            stop == StopCard.Exit.START -> home.show("Work stopped", stopLine, "Start", "start",
                pending.getOrDefault(false), GuidedHome.Stage.ATTENTION)
            stop == StopCard.Exit.TRY_AGAIN -> home.show("Work stopped", stopLine, "Try again", "start",
                false, GuidedHome.Stage.ATTENTION)
            // With recovery on offer, ③'s button becomes the one required recovery action, not Try again.
            stop == StopCard.Exit.RECOVERY -> home.show("Recovery needs attention", stopLine, attentionLabel,
                attentionKey, true, GuidedHome.Stage.ATTENTION)
            pending.getOrThrow() -> home.show("Finish your game safely", attentionDetail(), attentionLabel, attentionKey, true,
                GuidedHome.Stage.ATTENTION)
            // An unresolved saved action with nothing mid-change (its retry is spent, or it waits): continue or finish its Stop.
            savedRun != null && !automatic -> home.show("Finish your game safely", attentionDetail(), attentionLabel,
                attentionKey, false, GuidedHome.Stage.ATTENTION)
            // The finish-updates and closed-game instruction sits here, before Start; no dialog repeats it.
            else -> home.show("Ready when you are", UiText.string(this,
                if (provider == ShellProvider.ROOT) "ready_before_start_root" else "ready_before_start"), "Start", "start", false)
        }
        home.working(busy || live || (automatic && !waitingForShizuku && !waitingForAccess))
        // A saved action locks its language and provider until it completes or Stop safely resolves it; the note says so.
        home.languageEnabled(!busy && !live && !automatic && savedRun == null, locked = savedRun != null)
        home.providerEnabled(!busy && !live && !automatic && savedRun == null)
        home.progress(live || (busy && automatic) || stopShown, step,
            canStop = live || (busy && automatic) || stopShown || savedRun?.mayContinue == true)
        home.stopping(stopShown)
        buttons.forEach { it.isEnabled = !busy && !live && !automatic }
        home.resultMessage(if (!automatic && stop != null && !StopCard.ownCard(stop)) stopLine else "")
        home.errorDetails(when {
            live -> ""
            // The worker's own raw error first: the automatic flow also logs it, already explained, as an ERROR.
            state?.optString("status") in setOf("error", "recovery_required") -> state?.optString("error").orEmpty()
            else -> lastTaskError
        })
    }

    /**
     * Recovery needs attention's one action, as (label, key): the saved Stop's restoration, the saved action's
     * continuation, then the specific recovery the records call for. Unreadable or ambiguous records open the
     * recovery options. Every key but recovery_options dispatches recovery through [AutomaticRoute], never a fresh patch.
     */
    private fun attentionAction(material: RecoveryMaterial?, pending: Boolean?): Pair<String, String> = when {
        material == null || pending == null -> "Open recovery options" to "recovery_options"
        savedRun?.stopRequested == true -> UiText.string(this, "finish_stopping_safely") to "recover_attention"
        savedRun?.mayContinue == true -> UiText.string(this, "continue_saved_work") to "recover_attention"
        material?.patch == true -> "Restore interrupted patch" to "recover_attention"
        material?.setup == true -> "Finish or repair first setup" to "recover_attention"
        pending == true -> "Check restored game app" to "recover_attention"
        else -> "Open recovery options" to "recovery_options"
    }

    /** The attention state's instruction, from the saved action. */
    private fun attentionDetail(): String = when {
        savedRun?.stopRequested == true -> UiText.string(this, "attention_stop_saved")
        savedRun?.mayContinue == true -> UiText.string(this, "attention_saved_action")
        else -> ui("We will check unfinished work and recover it before patching.")
    }

    private fun friendlyFailure(message: String,
                                recoverable: Boolean = runCatching { RecoveryMaterial.read(this).any }.getOrDefault(true)): String =
        FailureText.explain(this, provider(), message, recoverable)

    internal fun ui(value: String) = UiText.text(this, value)

    private fun device(): IPrivilegedDeviceService = checkNotNull(service) { "Authorize and connect Shizuku first" }

    /** A direct deletion tap approves only the plan already rendered on the recovery card. */
    private fun reviewRedownload() {
        val reviewed = shownRedownload
        shownRedownload = null
        loadSavedRun()
        val run = savedRun
        val consent = run?.takeIf { it.mayContinue }?.redownload
        when {
            run?.mayContinue == true && run.sourceDownloads == "required" -> refreshHome()
            run == null || consent == null -> beginAutomatic(explicit = true)
            consent.needsAnswer -> {
                if (reviewed == null || reviewed != (run.id to consent.planSha256)) {
                    refreshHome()
                    home.message(UiText.string(this, "redownload_plan_changed"), failure = true)
                    return
                }
                var saved: Result<RunStore.Run>? = null
                runTaskThen({
                    saved = runCatching { RunStore(this).approveRedownload(reviewed.first, reviewed.second) }
                }) {
                    loadSavedRun()
                    if (saved?.isSuccess == true) beginAutomatic() else {
                        refreshHome()
                        saved?.exceptionOrNull()?.let {
                            DiagnosticTrace.error("ui", "Re-download approval not saved", it)
                            home.message(UiText.string(this, "redownload_plan_changed"), failure = true)
                        }
                    }
                }
            }
            consent.state == RedownloadConsent.DELETED -> refreshHome()
            else -> beginAutomatic(explicit = true)
        }
    }

    /** Wait on the card; neither returning to the app nor Start answers a held-back review or the download. */
    private fun redownloadWaits(run: RunStore.Run): Boolean {
        if (run.sourceDownloads != "required" && run.redownload?.state !in setOf(
                RedownloadConsent.AWAITING, RedownloadConsent.DECLINED, RedownloadConsent.DELETED)) return false
        stopAutomatic()
        refreshHome()
        return true
    }

    /** The normal APK and recovery checks must finish before the game can download its replacement files. */
    private fun openDownloadGame() {
        loadSavedRun()
        val run = savedRun?.takeIf { it.mayContinue } ?: return
        if (run.sourceDownloads != "required" && run.redownload?.state != RedownloadConsent.DELETED) return
        runTask {
            check(SessionJournal.pending(File(filesDir, "sessions")).isEmpty()) { "Finish recovery before opening the game" }
            EmergencyRestoreStore(this).requireResolved()
            runOnUiThread {
                val launch = packageManager.getLaunchIntentForPackage("com.tencent.tmgp.osgame")
                if (launch != null) startActivity(launch)
                else home.message("The game is not installed. Install it before preparing files.", failure = true)
            }
        }
    }

    /** One Downloads finished tap resumes the saved action; the build still checks download readiness. */
    private fun confirmDownloads() {
        loadSavedRun()
        val run = savedRun?.takeIf { it.mayContinue } ?: return
        if (run.sourceDownloads != "required" && run.redownload?.state != RedownloadConsent.DELETED) return
        var saved: Result<RunStore.Run>? = null
        runTaskThen({
            saved = runCatching {
                if (run.sourceDownloads == "required") RunStore(this).confirmSourceDownloads(run.id)
                else RunStore(this).confirmRedownloadDownloads(run.id)
            }
        }) {
            loadSavedRun()
            if (saved?.isSuccess == true) beginAutomatic() else refreshHome()
        }
    }

    /** Send the saved action, its prepared files now bound to it: Remove translation or the patch. */
    private fun dispatchAuthorized(request: String) = startWorker(Intent(this, PatchWorkerService::class.java)
        .setAction(if (removing) "remove" else "patch").putExtra("request", request))

    override fun onResume() { super.onResume(); shown = true; DiagnosticTrace.event("ui", "Activity resumed"); statusHandler.post(refreshStatus) }
    override fun onPause() { shown = false; DiagnosticTrace.event("ui", "Activity paused"); statusHandler.removeCallbacks(refreshStatus); super.onPause() }

    companion object {
        /** True while the patcher is on screen; a finished run then posts no notification. */
        @Volatile var shown = false

        /** Worker actions that return the game to consistency: ③ names them Restoring. */
        private val RESTORE_ACTIONS = setOf("recover", "setup_recover", "verify")
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

    internal fun runTask(task: () -> Unit) = tasks.run(task)
    /** [runTask], then <then> on the UI thread once the gate is clear, so <then> may start gated work itself. */
    private fun runTaskThen(task: () -> Unit, then: () -> Unit) = tasks.run(task, then)
    internal fun log(message: String) {
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
        state.putBoolean("waiting-access", waitingForAccess)
        state.putBoolean("stopping", stopping)
        state.putBoolean("continuing", continuing)
        state.putBoolean("recovery-only", recoveryOnly)
        state.putBoolean("automatic", automatic)
        state.putBoolean("removing", removing)
        state.putString("automatic-token", awaitingToken)
        state.putString("automatic-action", awaitingAction)
        state.putLong("automatic-since", awaitingSince)
        super.onSaveInstanceState(state)
    }
    override fun onDestroy() {
        DiagnosticTrace.event("ui", "Activity destroyed; changing configuration $isChangingConfigurations")
        destroyed = true
        updateCheck.close()
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
