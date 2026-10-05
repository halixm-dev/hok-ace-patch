package dev.halixm.hokacepatcher

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** One start action; show only work progress and checkpoints that need the user. */
class GuidedHome(private val activity: Activity, private val invoke: (String) -> Unit) {
    private val ink = Color.rgb(24, 42, 61)
    private val blue = Color.rgb(25, 81, 161)
    private val root = column()
    private val heading = text("Let's get started", 25)
    private val detail = text("Start Shizuku, then come back here.", 18)
    private val primary = button("Start", "next-step", true) { invoke(next) }
    private val recovery = column()
    private val stop = button("Stop safely", "stop-automatic") { invoke("stop") }
    private val spinner = android.widget.ProgressBar(activity)
    private val notice = text("", 18)
    private val liveLog = text("", 15).apply { tag = "live-patch-log"; setTextIsSelectable(true) }
    private val logScroll = ScrollView(activity).apply {
        addView(liveLog)
        layoutParams = LinearLayout.LayoutParams(-1, dp(180))
    }
    private val logCard = card().apply {
        visibility = View.GONE
        addView(text("Patching activity", 23))
        addView(text("New messages appear here as we work. Scroll to see earlier messages.", 16))
        addView(logScroll)
    }
    val advanced = column()
    private var next = "start"
    private var workerNotice = ""

    private val recoveryOptions by lazy {
        column().apply {
            visibility = View.GONE
            addView(button("Restore interrupted patch", "recover-patch") { invoke("recover") })
            addView(button("Finish or repair first setup", "recover-setup") { invoke("setup_recover") })
            addView(button("Reinstall saved game app", "recover-apk") { invoke("installer") })
            addView(text("After reinstalling, check the game app below. Unfinished file changes still need recovery.", 16))
            addView(button("Check restored game app", "verify-game") { invoke("verify") })
            addView(button("Save log for help", "export-log") { invoke("export") })
        }
    }

    init {
        root.setPadding(dp(20), dp(24), dp(20), dp(32))
        root.setBackgroundColor(Color.rgb(243, 246, 250))
        root.addView(text("HOK ACE Patcher", 30))
        root.addView(text("English patcher", 16))
        root.addView(text("Some game text will stay Chinese.\nUse Scan to login after setup.", 16))
        val card = card()
        card.addView(StepPicture(activity))
        card.addView(heading); card.addView(detail); card.addView(primary)
        spinner.visibility = View.GONE; stop.visibility = View.GONE
        card.addView(spinner); card.addView(stop)
        root.addView(card)
        root.addView(logCard)
        notice.tag = "friendly-notice"; notice.visibility = View.GONE
        root.addView(notice)
        recovery.background = background(Color.rgb(255, 243, 224))
        recovery.setPadding(dp(16), dp(12), dp(16), dp(12))
        recovery.addView(text("Game won't open?", 23))
        recovery.addView(text("Keep the game closed. Use recovery first.", 18))
        recovery.addView(button("Show recovery options", "show-recovery") {
            recoveryOptions.visibility = if (recoveryOptions.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        })
        recovery.addView(recoveryOptions)
        recovery.visibility = View.GONE
        root.addView(recovery)
        root.addView(button("Technical tools", "show-technical") {
            advanced.visibility = if (advanced.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        })
        advanced.visibility = View.GONE
        advanced.addView(text("For testing or support", 22))
        root.addView(advanced)
        activity.setContentView(ScrollView(activity).apply { isFillViewport = true; addView(root) })
    }

    fun show(title: String, instruction: String, label: String, action: String, recoveryNeeded: Boolean) {
        heading.text = title; detail.text = instruction; primary.text = label; next = action
        recovery.visibility = if (recoveryNeeded) View.VISIBLE else View.GONE
    }

    fun showRecovery() {
        recovery.visibility = View.VISIBLE
        recoveryOptions.visibility = View.VISIBLE
        (root.parent as? ScrollView)?.post { (root.parent as? ScrollView)?.smoothScrollTo(0, recovery.top) }
    }

    fun progress(value: Boolean) {
        spinner.visibility = if (value) View.VISIBLE else View.GONE
        stop.visibility = if (value) View.VISIBLE else View.GONE
    }

    fun logs(lines: List<String>) {
        val value = lines.joinToString("\n")
        logCard.visibility = if (value.isEmpty()) View.GONE else View.VISIBLE
        if (liveLog.text.toString() == value) return
        val follow = logScroll.scrollY + logScroll.height >= liveLog.height - dp(24)
        liveLog.text = value
        if (follow) logScroll.post { logScroll.fullScroll(View.FOCUS_DOWN) }
    }

    fun working(value: Boolean) { primary.isEnabled = !value }

    fun resultMessage(value: String) {
        if (value == workerNotice) return
        if (value.isEmpty() && notice.text.toString() == workerNotice) notice.visibility = View.GONE
        workerNotice = value
        if (value.isNotEmpty()) message(value)
    }

    fun message(value: String) {
        if (notice.text.toString() == value) return
        notice.text = value; notice.visibility = View.VISIBLE
        notice.announceForAccessibility(value)
    }

    fun technicalButton(label: String, callback: () -> Unit): Button = button(label, null, callback = callback).also {
        advanced.addView(it)
    }

    private fun dp(value: Int) = (value * activity.resources.displayMetrics.density).toInt()
    private fun column() = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
    private fun background(color: Int) = GradientDrawable().apply { setColor(color); cornerRadius = dp(18).toFloat() }
    private fun card() = column().apply {
        background = background(Color.WHITE); setPadding(dp(18), dp(18), dp(18), dp(18))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(18), 0, dp(18)) }
    }
    private fun text(value: String, size: Int) = TextView(activity).apply {
        text = value; textSize = size.toFloat(); setTextColor(ink)
        setPadding(0, dp(8), 0, dp(10)); setLineSpacing(dp(3).toFloat(), 1f)
        if (size >= 23) { setTypeface(null, Typeface.BOLD); isAccessibilityHeading = true }
    }
    private fun button(label: String, testTag: String?, primaryAction: Boolean = false, callback: () -> Unit) = Button(activity).apply {
        text = label; tag = testTag; textSize = 18f; isAllCaps = false; minHeight = dp(60); minimumHeight = dp(60)
        setTextColor(if (primaryAction) Color.WHITE else blue)
        background = background(if (primaryAction) blue else Color.WHITE).apply { if (!primaryAction) setStroke(dp(1), blue) }
        setPadding(dp(14), dp(12), dp(14), dp(12))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(6), 0, dp(6)) }
        setOnClickListener { callback() }
    }
}
