package dev.halixm.hokacepatcher

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.util.TypedValue
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
    /** DESIGN.md's four type steps; buttons and the log have their own tokens. */
    private enum class Type(val size: Int, val font: Int) {
        TITLE(R.dimen.type_title, R.font.barlowcondensed_extrabold),
        HEADING(R.dimen.type_heading, R.font.barlow_bold),
        BODY(R.dimen.type_body, R.font.barlow_regular),
        LABEL(R.dimen.type_label, R.font.barlow_semibold),
    }

    private val ink = activity.getColor(R.color.ink)
    private val muted = activity.getColor(R.color.text_muted)
    private val root = column()
    private val heading = text("Let's get started", Type.HEADING)
    private val detail = text("Start Shizuku, then come back here.", Type.BODY)
    private val primary = button("Start", "next-step", true) { invoke(next) }
    private val recovery = column()
    private var shown = ""
    private val stop = button("Stop safely", "stop-automatic") { invoke("stop") }
    private val spinner = android.widget.ProgressBar(activity)
    private val notice = text("", Type.BODY, supporting = true)
    private val languageNote = text("", Type.BODY, supporting = true).apply { tag = "language-note" }
    private val removeButton = button("Remove translation", "remove-translation") { invoke("remove") }
    private var errorRaw = ""
    private val errorText = text("", Type.BODY).apply { tag = "error-details"; setTextIsSelectable(true) }
    private val errorBox = column().apply {
        visibility = View.GONE
        addView(text("Error details", Type.HEADING))
        addView(errorText)
        addView(button("Copy error details", "copy-error") { copyError() })
    }
    private val liveLog = text("", Type.BODY).apply {
        tag = "live-patch-log"; setTextIsSelectable(true)
        typeface = Typeface.MONOSPACE; setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_log))
    }
    private val logScroll = LogScrollView(activity).apply {
        addView(liveLog)
        layoutParams = LinearLayout.LayoutParams(-1, dp(180))
        tag = "live-log-scroll"
    }
    private val logCard = card().apply {
        visibility = View.GONE
        addView(text("Patching activity", Type.HEADING))
        addView(text("New messages appear here as we work. Scroll to see earlier messages.", Type.BODY, supporting = true))
        addView(logScroll)
    }
    val advanced = column()
    private val updateButton = button("Check for updates", "check-app-update") { invoke("check_update") }
    private val freeSpaceButton = button("Free up space", "free-space") { invoke("free_space") }
    private var next = "start"
    private var workerNotice = ""
    private var choosingLanguage = false
    private val languages = RadioGroup(activity).apply {
        tag = "language-picker"; orientation = LinearLayout.VERTICAL
        PatchLanguage.choices.forEach { (code, name) ->
            addView(RadioButton(activity).apply {
                id = View.generateViewId(); text = name; tag = "language-$code"; setTextColor(ink)
                setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_button))
                typeface = activity.resources.getFont(R.font.barlow_semibold)
                minHeight = dp(48)
                buttonTintList = ColorStateList(
                    arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(activity.getColor(R.color.disabled_text), ink, muted))
                background = background(activity.getColor(R.color.card_solid))
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
            addView(button("Free up space", "free-space-recovery") { invoke("free_space") })
            addView(button("Finish or repair first setup", "recover-setup") { invoke("setup_recover") })
            addView(button("Reinstall saved game app", "recover-apk") { invoke("installer") })
            addView(text("After reinstalling, check the game app below. Unfinished file changes still need recovery.", Type.BODY))
            addView(button("Check restored game app", "verify-game") { invoke("verify") })
            addView(button("Save log for help", "export-log") { invoke("export") })
        }
    }

    init {
        root.setPadding(dp(20), dp(16), dp(20), dp(32))
        root.background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(activity.getColor(R.color.page_top), activity.getColor(R.color.page_bottom)))
        root.addView(hero())
        val languageCard = card()
        languageCard.addView(eyebrow("01  /  YOUR TRANSLATION"))
        languageCard.addView(text("Language", Type.HEADING))
        showLanguageNote()
        languageCard.addView(languageNote)
        languageCard.addView(removeButton)
        languageCard.addView(languages)
        root.addView(languageCard)
        val card = card()
        card.addView(eyebrow("02  /  READY TO PLAY"))
        card.addView(heading); card.addView(detail); card.addView(primary)
        spinner.indeterminateTintList = ColorStateList.valueOf(ink)
        spinner.visibility = View.GONE; stop.visibility = View.GONE
        card.addView(spinner); card.addView(stop)
        root.addView(card)
        root.addView(logCard)
        notice.tag = "friendly-notice"; notice.visibility = View.GONE
        root.addView(notice)
        root.addView(errorBox)
        recovery.background = background(activity.getColor(R.color.warning_surface))
        recovery.setPadding(dp(16), dp(12), dp(16), dp(12))
        recovery.addView(text("Game won't open?", Type.HEADING))
        recovery.addView(text("Keep the game closed. Use recovery first.", Type.BODY))
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
        advanced.addView(text("For testing or support", Type.HEADING))
        root.addView(advanced)
        root.addView(text("${ui("Patcher version")}: ${BuildConfig.VERSION_NAME}", Type.BODY, supporting = true))
        root.addView(updateButton)
        root.addView(freeSpaceButton)
        activity.setContentView(ScrollView(activity).apply {
            isFillViewport = true
            setBackgroundColor(activity.getColor(R.color.page_top))
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

    fun working(value: Boolean) { primary.isEnabled = !value; freeSpaceButton.isEnabled = !value }

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
    private fun space(token: Int) = activity.resources.getDimensionPixelSize(token)
    private fun withAlpha(color: Int, alpha: Float) = Color.argb(Math.round(alpha * 255), Color.red(color), Color.green(color), Color.blue(color))
    private fun column() = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
    private fun background(color: Int) = GradientDrawable().apply {
        setColor(color); cornerRadius = activity.resources.getDimension(R.dimen.corner_card)
    }
    private fun eyebrow(value: String) = text(value, Type.LABEL, supporting = true).apply {
        setPadding(0, 0, 0, dp(4))
    }

    /** Eyebrow, title and the one line on the partial translation and Scan to login: no tagline. */
    private fun hero() = column().apply {
        background = AceHeroDrawable(activity)
        space(R.dimen.space_lg).let { setPadding(it, it, it, it) }
        addView(eyebrow("COMMUNITY PATCHER  /  HOK ACE").apply {
            tag = "hero-eyebrow"; setTextColor(activity.getColor(R.color.on_panel_muted))
        })
        addView(text(activity.getString(R.string.app_name), Type.TITLE).apply {
            setTextColor(activity.getColor(R.color.on_panel)); setLineSpacing(0f, 0.95f)
        })
        addView(text("Some game text will stay Chinese.\nUse Scan to login after setup.", Type.BODY).apply {
            setTextColor(activity.getColor(R.color.on_panel))
        })
    }

    private fun card() = column().apply {
        background = background(activity.getColor(R.color.card)).apply { setStroke(dp(1), activity.getColor(R.color.card_edge)) }
        space(R.dimen.space_lg).let { setPadding(it, it, it, it) }
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, space(R.dimen.space_md), 0, 0) }
    }
    /** Headings are marked as headings for screen readers by their type step, not by their size. */
    private fun text(value: String, type: Type, supporting: Boolean = false) = TextView(activity).apply {
        text = ui(value); setTextColor(if (supporting) muted else ink)
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(type.size))
        typeface = activity.resources.getFont(type.font)
        setPadding(0, dp(8), 0, dp(10)); setLineSpacing(dp(3).toFloat(), 1f)
        if (type == Type.LABEL) letterSpacing = activity.resources.getFloat(R.dimen.type_label_tracking)
        if (type == Type.TITLE || type == Type.HEADING) isAccessibilityHeading = true
    }
    private fun button(label: String, testTag: String?, primaryAction: Boolean = false, callback: () -> Unit) = Button(activity).apply {
        text = ui(label); tag = testTag; isAllCaps = false; minHeight = dp(60); minimumHeight = dp(60)
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_button))
        typeface = activity.resources.getFont(R.font.barlow_semibold)
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(activity.getColor(R.color.disabled_text), activity.getColor(if (primaryAction) R.color.on_panel else R.color.ink))))
        // Primary: the panel gradient. Secondary: the card fill with a 1 dp ink edge at 30 %.
        val enabled = if (primaryAction) GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(activity.getColor(R.color.panel_top), activity.getColor(R.color.panel_bottom))).apply {
                cornerRadius = activity.resources.getDimension(R.dimen.corner_button)
            }
            else background(activity.getColor(R.color.card)).apply { setStroke(dp(1), withAlpha(ink, 0.3f)) }
        val states = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled), background(activity.getColor(R.color.disabled_fill)))
            addState(intArrayOf(), enabled)
        }
        background = RippleDrawable(ColorStateList.valueOf(withAlpha(ink, 0.18f)), states, null)
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
