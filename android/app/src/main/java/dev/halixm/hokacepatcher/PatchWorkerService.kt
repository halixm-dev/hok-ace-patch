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
    }
    private val recentMessages = ArrayDeque<String>()
    private var activeFlow: String? = null
    private val executor = Executors.newSingleThreadExecutor()
    private val busy = AtomicBoolean(false)
    private val retiring = AtomicBoolean(false)
    private val cancelRequested = AtomicBoolean(false)
    @Volatile private var coordinator: PatchCoordinator? = null
    @Volatile private var setup: FirstSetupCoordinator? = null
    @Volatile private var connection: WorkerDeviceConnection? = null
    private val notificationId = 1402
    @Volatile private var activeAction = ""
    /** The run's current [WorkerStep] key; null for an action that reports no step. */
    @Volatile private var activeStep: String? = null

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
        activeStep = WorkerStep.next(activeAction, activeStep, message)
        state(JSONObject().put("status", "running").put("action", activeAction).put("progress", message).also { running ->
            activeStep?.let { running.put("step", it).put("steps", WorkerStep.KEYS.size) }
        })
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("patch", UiText.text(this, "Game patch progress"),
            NotificationManager.IMPORTANCE_LOW))
        val cancel = PendingIntent.getService(this, 1, Intent(this, PatchWorkerService::class.java)
            .setAction("cancel"), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, "patch")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(getString(R.string.app_name)).setContentText(UiText.progress(this, message).take(160))
            .setContentIntent(open).setOngoing(true)
            .addAction(Notification.Action.Builder(null,
                UiText.text(this, when (activeAction) { "prepare" -> "Cancel preparation"; "first_setup" -> "Stop after safe installation";
                    else -> "Cancel and recover" }), cancel).build()).build()
        startForeground(notificationId, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        DiagnosticTrace.event("worker", "Start command ${intent?.action} start $startId flags $flags busy ${busy.get()} " +
            "extras ${intent?.extras?.keySet()?.associateWith { intent.extras?.get(it) }}")
        if (intent?.action == "cancel") {
            cancelRequested.set(true)
            coordinator?.cancel()
            setup?.cancel()
            if (!busy.get()) stopSelf(startId)
            return START_NOT_STICKY
        }
        if (!busy.compareAndSet(false, true)) return START_NOT_STICKY
        isWorking = true
        activeFlow = intent?.getStringExtra("flow")
        activeAction = intent?.action ?: ""
        activeStep = null
        recentMessages.clear()
        recentMessages.addAll(WorkerStep.carriedMessages(activeAction, savedState()))
        state(JSONObject().put("status", "running").put("action", intent?.action))
        show("Preparing verified recovery material")
        executor.execute {
            try {
                val bound = WorkerDeviceConnection(this) {
                    cancelRequested.set(true)
                    coordinator?.interrupted("Shizuku disconnected; recovery required")
                    setup?.interrupted("Shizuku disconnected; game setup recovery required")
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
                        val prepared = FirstSetupRequestStore(this).claim(request)
                        check(!cancelRequested.get() && !retiring.get()) { "Setup cancelled before removal" }
                        state(setupWorker.run(prepared, EngineAssets.prepare(this).name, true, request))
                    }
                    "setup_recover" -> state(setupWorker.recover(checkNotNull(intent.getStringExtra("setup"))))
                    "setup_update" -> state(setupWorker.finishUpdate(checkNotNull(intent.getStringExtra("setup")),
                        intent.getBooleanExtra("confirmed", false)))
                    "prepare" -> {
                        val prepared = ApkPreparation(this).prepare(device, { message -> show(message) }, {
                            check(!cancelRequested.get() && !retiring.get()) { "Preparation cancelled" }
                        })
                        check(!retiring.get()) { "Preparation worker stopped" }
                        state(if (cancelRequested.get()) JSONObject().put("status", "cancelled").put("action", "prepare")
                            else JSONObject().put("status", "prepared").put("action", "prepare")
                                .put("preparation", prepared.directory.name).put("normal", prepared.normal.sha256)
                                .put("requires_signature_conversion", prepared.requiresSignatureConversion))
                    }
                    "recover" -> state(worker.recover(checkNotNull(intent.getStringExtra("session"))))
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
                        val prepared = PatchRequestStore(this).claim(checkNotNull(intent.getStringExtra("request")))
                        check(!cancelRequested.get() && !retiring.get()) { "Re-download cancelled before access" }
                        val summary = worker.run(prepared.normal.sha256, prepared.accessFile, prepared.source,
                            redownload = true)
                        state(JSONObject().put("status", "complete").put("action", "redownload")
                            .put("redownloaded", summary.getJSONArray("redownload").length())
                            .put("packages", summary.getJSONObject("packages").length()))
                    }
                    "patch", "remove" -> {
                        val prepared = PatchRequestStore(this).claim(checkNotNull(intent.getStringExtra("request")))
                        check(!cancelRequested.get() && !retiring.get()) { "Patch cancelled before access" }
                        val summary = worker.run(prepared.normal.sha256, prepared.accessFile, prepared.source,
                            remove = intent.action == "remove")
                        val root = EngineAssets.prepare(this)
                        val result = JSONObject().put("status", "complete").put("counts", JSONObject(
                            com.chaquo.python.Python.getInstance().getModule("android_bridge").callAttr(
                                "result_counts", root.path, summary.toString()).toString()))
                        summary.optJSONArray("removed")?.let { result.put("removed", it.length()) }
                        state(result)
                    }
                    else -> error("Unsupported worker request")
                }
            } catch (error: Throwable) {
                val failureMessage = error.message?.takeIf { it.isNotBlank() } ?:
                    "The operation stopped unexpectedly. Keep the game closed, check Shizuku, then retry verification or recovery."
                if (!retiring.get()) runCatching { state(setup?.pendingRecoveryResult() ?: coordinator?.pendingRecoveryResult() ?:
                    JSONObject().put("status", if (activeAction == "prepare" && cancelRequested.get()) "cancelled" else "error")
                        .put("action", activeAction).put("error", failureMessage).put("error_type", error.javaClass.name)) }
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
