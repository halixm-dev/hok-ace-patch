package dev.halixm.hokacepatcher

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.view.Gravity
import android.view.View
import android.view.MotionEvent
import android.widget.Button
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast

/** One start action; show only work progress and checkpoints that need the user. */
class GuidedHome(private val activity: Activity, private val invoke: (String) -> Unit) {
    private val ink = Color.rgb(38, 39, 82)
    private val blue = Color.rgb(78, 69, 179)
    private val muted = Color.rgb(96, 98, 127)
    private val edge = Color.rgb(219, 218, 242)
    private val root = column()
    private val heading = text("Let's get started", 25)
    private val detail = text("Start Shizuku, then come back here.", 16)
    private val primary = button("Start", "next-step", true) { invoke(next) }
    private val recovery = column()
    private var shown = ""
    private val stop = button("Stop safely", "stop-automatic") { invoke("stop") }
    private val spinner = android.widget.ProgressBar(activity)
    private val notice = text("", 18)
    private val languageNote = text("", 15).apply { tag = "language-note" }
    private val removeButton = button("Remove translation", "remove-translation") { invoke("remove") }
    private var errorRaw = ""
    private val errorText = text("", 14).apply { tag = "error-details"; setTextIsSelectable(true) }
    private val errorBox = column().apply {
        visibility = View.GONE
        addView(text("Error details", 18))
        addView(errorText)
        addView(button("Copy error details", "copy-error") { copyError() })
    }
    private val liveLog = text("", 15).apply { tag = "live-patch-log"; setTextIsSelectable(true) }
    private val logScroll = LogScrollView(activity).apply {
        addView(liveLog)
        layoutParams = LinearLayout.LayoutParams(-1, dp(180))
        tag = "live-log-scroll"
    }
    private val logCard = card().apply {
        visibility = View.GONE
        addView(text("Patching activity", 23))
        addView(text("New messages appear here as we work. Scroll to see earlier messages.", 16))
        addView(logScroll)
    }
    val advanced = column()
    private val updateButton = button("Check for updates", "check-app-update") { invoke("check_update") }
    private var next = "start"
    private var workerNotice = ""
    private var choosingLanguage = false
    private val languages = RadioGroup(activity).apply {
        tag = "language-picker"; orientation = LinearLayout.VERTICAL
        PatchLanguage.choices.forEach { (code, name) ->
            addView(RadioButton(activity).apply {
                id = View.generateViewId(); text = name; tag = "language-$code"; textSize = 18f; setTextColor(ink)
                minHeight = dp(48)
                buttonTintList = ColorStateList(
                    arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(muted, blue, muted))
                background = background(Color.rgb(246, 245, 255))
                setPadding(dp(12), dp(6), dp(12), dp(6))
                layoutParams = RadioGroup.LayoutParams(-1, -2).apply { setMargins(0, dp(4), 0, dp(4)) }
            })
        }
        setOnCheckedChangeListener { group, checked ->
            val code = group.findViewById<RadioButton>(checked)?.tag?.toString()?.removePrefix("language-")
            if (!choosingLanguage && code != null) invoke("language:$code")
        }
    }

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
        root.setPadding(dp(20), dp(16), dp(20), dp(32))
        root.background = GradientDrawable(GradientDrawable.Orientation.TL_BR,
            intArrayOf(Color.rgb(230, 234, 255), Color.rgb(245, 242, 255), Color.rgb(232, 242, 255)))
        root.addView(hero())
        val languageCard = card()
        languageCard.addView(eyebrow("01  /  YOUR TRANSLATION"))
        languageCard.addView(text("Language", 23))
        showLanguageNote()
        languageCard.addView(languageNote)
        languageCard.addView(removeButton)
        languageCard.addView(languages)
        root.addView(languageCard)
        val card = card()
        card.addView(eyebrow("02  /  READY TO PLAY"))
        card.addView(heading); card.addView(detail); card.addView(primary)
        spinner.indeterminateTintList = ColorStateList.valueOf(blue)
        spinner.visibility = View.GONE; stop.visibility = View.GONE
        card.addView(spinner); card.addView(stop)
        root.addView(card)
        root.addView(logCard)
        notice.tag = "friendly-notice"; notice.visibility = View.GONE
        root.addView(notice)
        root.addView(errorBox)
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
        root.addView(text("${ui("Patcher version")}: ${BuildConfig.VERSION_NAME}", 14))
        root.addView(updateButton)
        root.addView(text("COMMUNITY PATCHER  /  HOK ACE", 11).apply {
            gravity = Gravity.CENTER; letterSpacing = 0.12f
            setPadding(0, dp(24), 0, 0)
        })
        activity.setContentView(ScrollView(activity).apply {
            isFillViewport = true
            setBackgroundColor(Color.rgb(230, 234, 255))
            addView(root)
            setOnApplyWindowInsetsListener { view, insets ->
                val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars())
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                insets
            }
        })
    }

    fun show(title: String, instruction: String, label: String, action: String, recoveryNeeded: Boolean) {
        val screen = "$title | $instruction | $label -> $action, recovery $recoveryNeeded"
        if (screen != shown) { shown = screen; DiagnosticTrace.event("screen", screen) }
        heading.text = ui(title); detail.text = ui(instruction); primary.text = ui(label); next = action
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

    fun checkingUpdate(value: Boolean) {
        updateButton.isEnabled = !value
        updateButton.text = ui(if (value) "Checking for updates…" else "Check for updates")
    }

    /** Show <code> as chosen without reporting it back as a new choice. */
    fun language(code: String) {
        val button = languages.findViewWithTag<RadioButton>("language-$code") ?: return
        if (button.isChecked) return
        choosingLanguage = true
        try { languages.check(button.id) } finally { choosingLanguage = false }
    }

    /** Whether switching needs a clear: not once the patcher keeps a pristine delta for the phone. */
    private fun showLanguageNote() {
        // Remove translation needs the delta, so it is offered only while one is kept.
        removeButton.visibility = if (PristineDelta.held(activity)) View.VISIBLE else View.GONE
        languageNote.text = ui(if (PristineDelta.held(activity)) {
            "Switching languages? No need to clear: the patcher kept the original game files it changed."
        } else {
            "Switching languages on a phone another patcher or an older version translated? Clear the game's data and download it again first."
        })
    }

    /** A run reads the language once at its start, so the choice is locked while work is in progress. */
    fun languageEnabled(value: Boolean) {
        if (value) showLanguageNote()
        removeButton.isEnabled = value
        for (index in 0 until languages.childCount) languages.getChildAt(index).apply {
            isEnabled = value; alpha = if (value) 1f else 0.55f
        }
    }

    fun resultMessage(value: String) {
        if (value == workerNotice) return
        if (value.isEmpty() && notice.text.toString() == ui(workerNotice)) notice.visibility = View.GONE
        workerNotice = value
        if (value.isNotEmpty()) message(value)
    }

    fun message(value: String) {
        if (notice.text.toString() == ui(value)) return
        DiagnosticTrace.event("screen", "Notice: $value")
        notice.text = ui(value); notice.visibility = View.VISIBLE
        notice.announceForAccessibility(notice.text)
    }

    /** Show the cause of <raw> on screen and keep all of it for copying; empty hides the box. */
    fun errorDetails(raw: String) {
        if (raw == errorRaw) return
        errorRaw = raw
        errorText.text = ErrorSummary.cause(raw)
        errorBox.visibility = if (raw.isBlank()) View.GONE else View.VISIBLE
    }

    private fun copyError() {
        if (errorRaw.isBlank()) return
        activity.getSystemService(ClipboardManager::class.java)
            .setPrimaryClip(ClipData.newPlainText("HOK ACE error", errorRaw))
        DiagnosticTrace.event("ui", "Copied error details (${errorRaw.length} chars)")
        // Android 13+ confirms a copy itself.
        if (android.os.Build.VERSION.SDK_INT < 33) Toast.makeText(activity, ui("Error details copied"), Toast.LENGTH_SHORT).show()
    }

    fun technicalButton(label: String, callback: () -> Unit): Button = button(label, null, callback = callback).also {
        advanced.addView(it)
    }

    fun addDiagnosticLog(output: TextView) {
        advanced.addView(LogScrollView(activity).apply {
            tag = "diagnostic-log-scroll"
            layoutParams = LinearLayout.LayoutParams(-1, dp(240))
            addView(output)
        })
    }

    private fun ui(value: String) = UiText.text(activity, value)

    private fun dp(value: Int) = (value * activity.resources.displayMetrics.density).toInt()
    private fun column() = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
    private fun background(color: Int) = GradientDrawable().apply { setColor(color); cornerRadius = dp(18).toFloat() }
    private fun eyebrow(value: String) = text(value, 11).apply {
        setTextColor(blue); letterSpacing = 0.14f; setTypeface(null, Typeface.BOLD)
        setPadding(0, 0, 0, dp(4))
    }

    private fun hero() = column().apply {
        background = AceHeroDrawable(activity.resources.displayMetrics.density)
        setPadding(dp(22), dp(20), dp(22), dp(20))
        addView(eyebrow("HONOR OF KINGS  /  ACE").apply { setTextColor(Color.rgb(224, 228, 255)) })
        addView(text(activity.getString(R.string.app_name), 32).apply {
            setTextColor(Color.WHITE); setLineSpacing(0f, 0.95f)
            typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
        })
        addView(text("Your next move. Your language.", 16).apply { setTextColor(Color.WHITE) })
        addView(text("Some game text will stay Chinese.\nUse Scan to login after setup.", 14).apply {
            setTextColor(Color.WHITE)
            background = background(Color.argb(65, 20, 22, 75))
            setPadding(dp(12), dp(10), dp(12), dp(10))
        })
    }

    private fun card() = column().apply {
        background = background(Color.argb(235, 255, 255, 255)).apply { setStroke(dp(1), edge) }
        setPadding(dp(20), dp(20), dp(20), dp(20))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(16), 0, 0) }
    }
    private fun text(value: String, size: Int) = TextView(activity).apply {
        text = ui(value); textSize = size.toFloat(); setTextColor(if (size >= 23) ink else muted)
        setPadding(0, dp(8), 0, dp(10)); setLineSpacing(dp(3).toFloat(), 1f)
        if (size >= 23) { setTypeface(null, Typeface.BOLD); isAccessibilityHeading = true }
    }
    private fun button(label: String, testTag: String?, primaryAction: Boolean = false, callback: () -> Unit) = Button(activity).apply {
        text = ui(label); tag = testTag; textSize = 16f; isAllCaps = false; minHeight = dp(60); minimumHeight = dp(60)
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(muted, if (primaryAction) Color.WHITE else blue)))
        val enabled = if (primaryAction) GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,
            intArrayOf(blue, Color.rgb(66, 98, 187))).apply { cornerRadius = dp(16).toFloat() }
            else background(Color.WHITE).apply { setStroke(dp(1), edge) }
        val states = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled), background(Color.rgb(226, 226, 240)))
            addState(intArrayOf(), enabled)
        }
        background = RippleDrawable(ColorStateList.valueOf(Color.argb(45, 125, 137, 231)), states, null)
        setPadding(dp(14), dp(12), dp(14), dp(12))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(6), 0, dp(6)) }
        setOnClickListener { callback() }
    }
}

/** Reserve log gestures even when a selectable child TextView consumes the initial touch. */
private class LogScrollView(context: android.content.Context) : ScrollView(context) {
    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        parent?.requestDisallowInterceptTouchEvent(
            event.actionMasked != MotionEvent.ACTION_UP && event.actionMasked != MotionEvent.ACTION_CANCEL)
        return super.dispatchTouchEvent(event)
    }
}
