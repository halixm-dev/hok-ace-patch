package dev.halixm.hokacepatcher

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.AtomicFile
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** User-started local file processing; durable journals survive foreground timeout/process death. */
class PatchWorkerService : Service() {
    companion object {
        /** Process-local service lifetime, never inferred from a saved running result. */
        @Volatile var isWorking = false
            private set

        /** Validate before claiming process-local lifetime; malformed input never falls back to a picker. */
        fun dispatchRun(context: android.content.Context, intent: Intent?): RunStore.Run? {
            val action = intent?.action
            if (action == "recover") {
                val session = checkNotNull(intent.getStringExtra("session"))
                GameFilePolicy.session(session)
                val journal = SessionJournal.load(File(context.filesDir, "sessions/$session"))
                val runId = journal.runId ?: return null // Legacy authority permits safety recovery only.
                val store = RunStore(context); val run = store.load(runId); store.requireTarget(run)
                check(run.sessionId == session && journal.authorizationKey == run.authorizationKey) { "Recovery journal has no correlated Start" }
                return run // Stop revokes continuation, never justified safety recovery.
            }
            if (action == "first_setup") {
                // Destructive setup runs only under its own one-use consent, bound to a Start that may still continue.
                val parent = FirstSetupRequestStore(context).parent(checkNotNull(intent.getStringExtra("request"))) ?: return null
                val store = RunStore(context); val run = store.load(parent); store.requireTarget(run)
                check(run.action == "translate" && run.mayContinue && run.provider != ShellProvider.ROOT) {
                    "Setup consent differs from the saved Start"
                }
                return run
            }
            if (action == "setup_recover" || action == "setup_update") {
                // Install-only recovery and the downloads answer use the provider the setup's Start recorded, even after Stop.
                val setup = checkNotNull(intent.getStringExtra("setup")); GameFilePolicy.session(setup)
                val parent = FirstSetupJournal.load(File(context.filesDir, "first-setups/$setup")).parentRun ?: return null
                val store = RunStore(context); val run = store.load(parent); store.requireTarget(run)
                return run
            }
            if (action !in setOf("prepare", "patch", "remove", "redownload")) return null
            val id = if (action == "prepare") intent?.getStringExtra("run") else intent?.getStringExtra("request")
            val store = RunStore(context)
            val run = store.load(checkNotNull(id) { "Durable Start required" })
            store.requireTarget(run)
            val expected = when (action) { "patch" -> "translate"; "prepare" -> run.action; else -> action }
            check(run.action == expected && run.mayContinue) { "Dispatch differs from saved Start" }
            intent?.getStringExtra("run")?.let { check(it == run.id) { "Conflicting run references" } }
            return run
        }
    }
    private val recentMessages = ArrayDeque<String>()
    private var activeFlow: String? = null
    private val executor = Executors.newSingleThreadExecutor()
    private val busy = AtomicBoolean(false)
    private val retiring = AtomicBoolean(false)
    private val cancelRequested = AtomicBoolean(false)
    /** Set when the provider dropped the worker: a prepare it cancels reports this line, which ③ reads as that provider's loss. */
    @Volatile private var lost: String? = null
    @Volatile private var coordinator: PatchCoordinator? = null
    @Volatile private var setup: FirstSetupCoordinator? = null
    @Volatile private var connection: WorkerDeviceConnection? = null
    private val notificationId = 1402
    @Volatile private var activeAction = ""
    /** The run's current [WorkerStep] key; null for an action that reports no step. */
    @Volatile private var activeStep: String? = null
    /** The run's provider is Root, whose runs skip two of the steps. */
    @Volatile private var rootRun = false
    @Volatile private var activeRunId: String? = null
    /** Stop safely was received: it is saved first, shown at once, and a repeated Stop does nothing. */
    @Volatile private var stopping = false

    @Synchronized private fun state(value: JSONObject) {
        if (retiring.get() && value.optString("status") !in setOf("recovery_required", "cancelled")) return
        val message = value.optString("progress").ifBlank { value.optString("error") }
        if (value.optString("status") != "running") DiagnosticTrace.event("worker", "Result: $value")
        else if (message.isNotBlank() && message != recentMessages.lastOrNull()?.substringAfter("  ")) {
            DiagnosticTrace.event("worker", "Progress: $message")
        }
        if (message.isNotBlank()) {
            val time = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date())
            // A stack trace in the 180 dp live log scrolls its own cause out of view; the trace keeps it whole.
            recentMessages.addLast("$time  ${ErrorSummary.cause(message).take(2000)}")
            while (recentMessages.size > 40) recentMessages.removeFirst()
        }
        activeRunId?.let { value.put("run", it) }
        value.put("messages", JSONArray(recentMessages.toList()))
        value.put("updated_ms", System.currentTimeMillis())
        activeFlow?.let { value.put("flow", it) }
        val file = AtomicFile(File(filesDir, "worker-state.json"))
        val output = file.startWrite()
        try {
            output.write(value.toString().toByteArray(Charsets.UTF_8))
            output.fd.sync()
            file.finishWrite(output)
            DurableFiles.syncDirectory(filesDir)
        } catch (error: Throwable) { file.failWrite(output); throw error }
    }

    /** The last saved worker record, or null when there is none or it does not read. */
    private fun savedState(): JSONObject? = runCatching {
        JSONObject(String(DurableFiles.readCommitted(File(filesDir, "worker-state.json")), Charsets.UTF_8))
    }.getOrNull()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        DiagnosticTrace.init(this)
        DiagnosticTrace.event("worker", "Service created")
    }

    private fun show(message: String) {
        if (retiring.get()) return
        if (message == WorkerStep.DAMAGED_FILES_FOUND) activeAction = "redownload"
        activeStep = WorkerStep.next(activeAction, activeStep, message, rootRun)
        state(JSONObject().put("status", "running").put("action", activeAction).put("progress", message).also { running ->
            activeStep?.let { running.put("step", it).put("steps", WorkerStep.KEYS.size) }
            if (stopping) running.put("stopping", true)
        })
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("patch", UiText.text(this, "Game patch progress"),
            NotificationManager.IMPORTANCE_LOW))
        val cancel = PendingIntent.getService(this, 1, Intent(this, PatchWorkerService::class.java)
            .setAction("cancel"), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = Notification.Builder(this, "patch")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(getString(R.string.app_name))
            .setContentText((if (stopping) UiText.text(this, "Stopping safely") else UiText.progress(this, message)).take(160))
            .setContentIntent(open).setOngoing(true)
        // Once Stop is saved the action is gone: a second Stop cannot be sent.
        if (!stopping) builder.addAction(Notification.Action.Builder(null,
                UiText.text(this, when (activeAction) { "prepare" -> "Cancel preparation"; "first_setup" -> "Stop after safe installation";
                    else -> "Cancel and recover" }), cancel).build())
        val notification = builder.build()
        startForeground(notificationId, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        DiagnosticTrace.event("worker", "Start command ${intent?.action} start $startId flags $flags busy ${busy.get()} " +
            "extras ${intent?.extras?.keySet()?.associateWith { intent.extras?.get(it) }}")
        if (intent?.action == "cancel") {
            if (!busy.get()) { stopSelf(startId); return START_NOT_STICKY }
            if (stopping) return START_NOT_STICKY // Already saved and acting on it.
            stopping = true
            // Saved before it is acknowledged; a failed save still stops this attempt at its next safe boundary.
            val saved = activeRunId?.let { id -> runCatching { RunStore(this).stop(id) }
                .onFailure { DiagnosticTrace.error("worker", "Stop could not be saved", it) }.isSuccess } ?: true
            cancelRequested.set(true)
            coordinator?.cancel()
            setup?.cancel()
            DiagnosticTrace.event("worker", "Stop safely received during $activeAction; saved $saved")
            runCatching { show(if (saved) "Stopping safely" else UiText.english("stop_not_saved")) }
            return START_NOT_STICKY
        }
        if (busy.get()) return START_NOT_STICKY
        val savedRun = try { dispatchRun(this, intent) } catch (error: Throwable) {
            // A Stop saved before this request arrived: nothing started, so it is a cancellation, not a damaged record.
            val stopped = stoppedBeforeWork(intent)
            // Not busy here: this refused request owns the record, so its flow answers the screen waiting for it.
            activeRunId = null; activeFlow = intent?.getStringExtra("flow")
            state(if (stopped != null) JSONObject().put("status", "cancelled").put("action", intent?.action).put("run", stopped)
                    .put("error", "Stopped before work started")
                else JSONObject().put("status", "recovery_required").put("launch_allowed", false)
                    .put("error", error.message ?: "Saved Start cannot be read").put("error_type", error.javaClass.name))
            stopSelf(startId)
            return START_NOT_STICKY
        }
        if (!busy.compareAndSet(false, true)) return START_NOT_STICKY
        isWorking = true
        stopping = false
        activeFlow = intent?.getStringExtra("flow")
        activeAction = intent?.action ?: ""
        activeStep = null
        // Read once: changing the provider while a run is in progress is refused, and this run keeps its own.
        activeRunId = savedRun?.id
        val provider = savedRun?.provider ?: ShellProvider.current(this)
        rootRun = provider == ShellProvider.ROOT
        recentMessages.clear()
        recentMessages.addAll(WorkerStep.carriedMessages(activeAction, savedState()))
        state(JSONObject().put("status", "running").put("action", intent?.action))
        show("Preparing verified recovery material")

        executor.execute {
            try {
                val bound = WorkerDeviceConnection.open(this, provider) {
                    lost = "${provider.label} disconnected"
                    cancelRequested.set(true)
                    coordinator?.interrupted("${provider.label} disconnected; recovery required")
                    setup?.interrupted("${provider.label} disconnected; game setup recovery required")
                }
                connection = bound
                val device = bound.await()
                check(!retiring.get()) { "Worker stopped before device connection completed" }
                val worker = PatchCoordinator(this, device, report = { message ->
                    android.util.Log.i("HokAceWorker", message)
                    show(message)
                })
                coordinator = worker
                if (cancelRequested.get()) worker.cancel()
                val setupWorker = FirstSetupCoordinator(this, FirstSetupDeviceTransport(this, device), { show(it) })
                setup = setupWorker
                if (cancelRequested.get()) setupWorker.cancel()
                when (intent?.action) {
                    "first_setup" -> {
                        val request = checkNotNull(intent.getStringExtra("request"))
                        val parent = FirstSetupRequestStore(this).parent(request)
                        check(parent == activeRunId) { "Setup consent differs from the saved Start" }
                        // The setup is its parent Start's logical operation, persisted before dispatch; never re-armed.
                        parent?.let { RunStore(this).beginAttempt(it, "first_setup") }
                        val prepared = FirstSetupRequestStore(this).claim(request)
                        check(!cancelRequested.get() && !retiring.get()) { "Setup cancelled before removal" }
                        state(setupWorker.run(prepared, EngineAssets.prepare(this).name, true, request, parent))
                    }
                    "setup_recover" -> state(setupWorker.recover(checkNotNull(intent.getStringExtra("setup"))))
                    "setup_update" -> state(setupWorker.finishUpdate(checkNotNull(intent.getStringExtra("setup")),
                        intent.getBooleanExtra("confirmed", false)))
                    "prepare" -> RunStore.coordinator(this) {
                        val run = checkNotNull(activeRunId) { "Durable Start required before preparation" }
                        val authority = RunStore(this).load(run)
                        check(authority.mayContinue && authority.provider == provider) { "Preparation authorization is stopped" }
                        RunStore(this).beginAttempt(run, "preparation")
                        val checkpoint = { check(!cancelRequested.get() && !retiring.get() && RunStore(this).load(run).mayContinue) { "Preparation cancelled" } }
                        // Root installs no APK, so it prepares only a copy of the installed game app (ADR 0007).
                        val result = if (WorkerAccess.of(device) == WorkerAccess.ROOT) {
                            val prepared = ApkPreparation(this).prepareRoot(device, { message -> show(message) }, checkpoint)
                            // A Stop during the last preparation step reads as a cancel, not as a refused bind.
                            checkpoint()
                            PatchRequestStore(this).authorizeRoot(run, prepared)
                            JSONObject().put("preparation", prepared.directory.name).put("root", true)
                                .put("normal", prepared.installed.sha256).put("requires_signature_conversion", false)
                        } else {
                            val prepared = ApkPreparation(this).prepare(device, { message -> show(message) }, checkpoint)
                            checkpoint()
                            if (!prepared.requiresSignatureConversion) PatchRequestStore(this).authorize(run, prepared)
                            JSONObject().put("preparation", prepared.directory.name).put("normal", prepared.normal.sha256)
                                .put("requires_signature_conversion", prepared.requiresSignatureConversion)
                        }
                        check(!retiring.get()) { "Preparation worker stopped" }
                        state(if (cancelRequested.get()) JSONObject().put("status", "cancelled").put("action", "prepare")
                                .apply { lost?.let { put("error", it) } }
                            else result.put("status", "prepared").put("action", "prepare"))
                    }
                    "recover" -> state(worker.recover(checkNotNull(intent.getStringExtra("session")),
                        WorkerAccess.of(device) == WorkerAccess.ROOT))
                    "free_space" -> state(worker.freeSpace(intent.getBooleanExtra("remove_saved_apks", false)))
                    "verify" -> {
                        val normal = checkNotNull(intent.getStringExtra("normal"))
                        val emergency = intent.getStringExtra("emergency")
                        show("Checking the installed normal game app")
                        if (emergency == null) worker.verifyRecoveryInstalled(normal)
                        else EmergencyRestoreStore(this).verify(emergency, normal, worker::verifyRecoveryInstalled)
                        state(JSONObject().put("status", "verified").put("action", "verify"))
                    }
                    "redownload" -> {
                        val summary = claimAndRun(worker, checkNotNull(intent.getStringExtra("request")),
                            "Re-download cancelled before access", redownload = true)
                        state(redownloadResult(summary))
                    }
                    "patch", "remove" -> {
                        val summary = claimAndRun(worker, checkNotNull(intent.getStringExtra("request")),
                            "Patch cancelled before access", remove = intent.action == "remove")
                        // The build found damaged files, and the run deleted them instead of patching.
                        if (summary.has("status")) state(summary)
                        else if (summary.has("redownload")) state(redownloadResult(summary)) else {
                            val root = EngineAssets.prepare(this)
                            val result = JSONObject().put("status", "complete").put("counts", JSONObject(
                                com.chaquo.python.Python.getInstance().getModule("android_bridge").callAttr(
                                    "result_counts", root.path, summary.toString()).toString())).put("root", rootRun)
                            summary.optJSONArray("removed")?.let { result.put("removed", it.length()) }
                            state(result)
                        }
                    }
                    else -> error("Unsupported worker request")
                }
            } catch (error: Throwable) {
                val prepareCancelled = activeAction == "prepare" && cancelRequested.get()
                val failureMessage = (if (prepareCancelled) lost else null) ?: error.message?.takeIf { it.isNotBlank() } ?:
                    "The operation stopped unexpectedly. Keep the game closed, check ${provider.label}, then retry verification or recovery."
                if (!retiring.get()) runCatching {
                    val pending = setup?.pendingRecoveryResult() ?: coordinator?.pendingRecoveryResult()
                    val result = pending ?: JSONObject().put("status", if (prepareCancelled) "cancelled" else "error")
                        .put("action", activeAction).put("error", failureMessage).put("error_type", error.javaClass.name)
                    val storageShortage = StorageBudget.shortage(error)
                    if (storageShortage != null && activeRunId != null) {
                        val run = RunStore(this).load(checkNotNull(activeRunId))
                        if (run.mayContinue) {
                            RunStore(this).waitFor(run.id, "storage")
                            val unresolved = pending != null || runCatching {
                                SessionJournal.pending(File(filesDir, "sessions")).isNotEmpty() ||
                                    FirstSetupJournal.pending(this).isNotEmpty() ||
                                    EmergencyRestoreStore(this).snapshot()?.optString("status") == "verification_pending"
                            }.getOrDefault(true)
                            val shortage = storageShortage.result(unresolved)
                            shortage.keys().forEach { key -> result.put(key, shortage.get(key)) }
                            if (prepareCancelled) result.put("status", "cancelled")
                        }
                    }
                    state(result)
                }
                DiagnosticTrace.error("worker", "Patch/recovery stopped during $activeAction", error)
            } finally {
                // A finished run tells a player who left the patcher; a stopped worker (retiring) has its own recovery path.
                if (!retiring.get()) savedState()?.let { RunNotification.post(this, it, MainActivity.shown) }
                connection?.close()
                connection = null
                coordinator = null
                setup = null
                busy.set(false)
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    /** The run id when <intent> names a readable saved Start (directly, or through its setup consent) that is stopped. */
    private fun stoppedBeforeWork(intent: Intent?): String? = runCatching {
        val id = when (intent?.action) {
            "first_setup" -> FirstSetupRequestStore(this).parent(checkNotNull(intent.getStringExtra("request")))
            "prepare" -> intent.getStringExtra("run")
            else -> intent?.getStringExtra("request")
        } ?: return null
        id.takeIf { RunStore(this).load(it).stopRequested }
    }.getOrNull()

    private fun redownloadResult(summary: JSONObject) = JSONObject().put("status", "complete").put("action", "redownload")
        .put("redownloaded", summary.getJSONArray("redownload").length())
        .put("packages", summary.getJSONObject("packages").length()).put("root", rootRun)

    /** Claim confirmation <request> and run it on the path it was confirmed for: root's, or the shell path's. */
    private fun claimAndRun(worker: PatchCoordinator, request: String, cancelled: String,
                            remove: Boolean = false, redownload: Boolean = false): JSONObject {
        check(!cancelRequested.get() && !retiring.get()) { cancelled }
        val run = RunStore(this).load(request)
        val action = when { redownload -> "redownload"; remove -> "remove"; else -> "translate" }
        check(run.action == action) { "Dispatch action differs from saved Start" }
        // The coordinator resolves the saved action from its verified journal (COMPLETE, or a Stop made
        // consistent), never from this worker-state projection; an interruption leaves it to continue.
        return worker.dispatch(request, action, run.provider)
    }

    override fun onTimeout(startId: Int, fgsType: Int) {

        DiagnosticTrace.event("worker", "Foreground service timeout during $activeAction (type $fgsType)")
        retiring.set(true)
        cancelRequested.set(true)
        coordinator?.interrupted("Foreground processing timed out; inspect retained recovery journal")
        setup?.interrupted("Foreground processing timed out; inspect retained game setup journal")
        runCatching { state(JSONObject().put("status", if (activeAction == "prepare") "cancelled" else "recovery_required")
            .put("action", activeAction).put("error", "Foreground timeout")) }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf(startId)
    }

    override fun onDestroy() {
        DiagnosticTrace.event("worker", "Service destroyed; busy ${busy.get()} action $activeAction")
        retiring.set(true)
        cancelRequested.set(true)
        coordinator?.interrupted("Worker interrupted; recovery required")
        setup?.interrupted("Worker interrupted; game setup recovery required")
        connection?.close()
        executor.shutdownNow()
        isWorking = false
        super.onDestroy()
    }
}
