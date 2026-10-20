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

    /**
     * What ② is doing, named by its eyebrow so a failure, a result or a missing Shizuku never sits
     * under "READY TO PLAY".
     */
    enum class Stage(val eyebrow: String) {
        READY("02  /  READY TO PLAY"), SHIZUKU("02  /  NEEDS SHIZUKU"), WORKING("02  /  IN PROGRESS"),
        DONE("02  /  DONE"), ATTENTION("02  /  NEEDS ATTENTION"),
    }

    private val ink = activity.getColor(R.color.ink)
    private val muted = activity.getColor(R.color.text_muted)
    private val root = column()
    private val stage = eyebrow(Stage.READY.eyebrow).apply { tag = "start-eyebrow" }
    private val heading = text("Let's get started", Type.HEADING)
    private val detail = text("Start Shizuku, then come back here.", Type.BODY)
    private val primary = button("Start", "next-step", true) { invoke(next) }
    /** Under Open game, on a result that leaves the game ready: the result's own label (Start another patch). */
    private val again = button("Start another patch", "start-again") { invoke("start") }.apply { visibility = View.GONE }
    private val recovery = card(R.color.warning_surface, R.color.warning)
    private val recoveryToggle = button("Show recovery options", "show-recovery") {
        foldRecovery(recoveryOptions.visibility != View.VISIBLE)
    }
    private var shown = ""
    private val stop = button("Stop safely", "stop-automatic") { invoke("stop") }
    /** Running: the bar takes the button's place; determinate while the worker reports a step. */
    private val bar = android.widget.ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal).apply {
        tag = "progress-bar"
        layoutParams = LinearLayout.LayoutParams(-1, dp(8)).apply { setMargins(0, dp(12), 0, dp(12)) }
    }
    /** One ink line under ②'s instruction; a notice that reports a failure leads with the warning disc. */
    private val notice = text("", Type.BODY).apply { tag = "friendly-notice"; layoutParams = LinearLayout.LayoutParams(0, -2, 1f) }
    private val noticeMark = android.widget.ImageView(activity).apply {
        tag = "notice-mark"; setImageResource(R.drawable.ic_notice_warning); visibility = View.GONE
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        // As tall as the text, centred on the first line, so it follows the system font size.
        val size = notice.textSize.toInt()
        val line = notice.paint.fontMetricsInt.let { it.descent - it.ascent }
        layoutParams = LinearLayout.LayoutParams(size, size).apply {
            setMargins(0, notice.paddingTop + (line - size) / 2, dp(8), 0)
        }
    }
    private val noticeRow = LinearLayout(activity).apply {
        tag = "friendly-notice-row"; orientation = LinearLayout.HORIZONTAL; visibility = View.GONE
        addView(noticeMark); addView(notice)
    }
    /** A result state's counts, one row each, and the login note that follows them. */
    private val resultItems = column().apply { tag = "result-items"; visibility = View.GONE }
    private val resultNote = text("", Type.BODY).apply { tag = "result-note"; visibility = View.GONE }
    private var shownItems = emptyList<String>()
    private val languageNote = text("", Type.BODY, supporting = true).apply { tag = "language-note" }
    private val removeButton = button("Remove translation", "remove-translation") { invoke("remove") }
    private var errorRaw = ""
    private val errorText = text("", Type.BODY).apply { tag = "error-details"; setTextIsSelectable(true) }
    private val errorBox = card(R.color.error_surface, R.color.error).apply {
        tag = "error-card"; visibility = View.GONE
        addView(text("Error details", Type.HEADING))
        addView(errorText)
        addView(button("Copy error details", "copy-error") { copyError() })
        addView(button("Save log for help", "error-export-log") { invoke("export") })
    }
    private val liveLog = text("", Type.BODY).apply {
        tag = "live-patch-log"; setTextIsSelectable(true)
        typeface = Typeface.MONOSPACE; setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_log))
    }
    private val logScroll = LogScrollView(activity).apply {
        addView(liveLog)
        layoutParams = LinearLayout.LayoutParams(-1, dp(180)).apply { topMargin = dp(8) }
        tag = "live-log-scroll"
    }
    private val logCard = card().apply {
        visibility = View.GONE
        addView(text("Patching activity", Type.HEADING))
        addView(text("New messages appear here as we work. Scroll to see earlier messages.", Type.BODY, supporting = true))
        addView(logScroll)
    }
    val advanced = column()
    private val updateButton = footerButton("Check for updates", "check-app-update") { invoke("check_update") }
    private val freeSpaceButton = footerButton("Free up space", "free-space") { invoke("free_space") }
    private var next = "start"
    private var workerNotice = ""
    private var choosingLanguage = false
    private val languages = RadioGroup(activity).apply {
        tag = "language-picker"; orientation = LinearLayout.VERTICAL
        PatchLanguage.choices.forEach { (code, name) ->
            addView(RadioButton(activity).apply {
                id = View.generateViewId(); text = name; tag = "language-$code"
                setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_button))
                typeface = activity.resources.getFont(R.font.barlow_semibold)
                minHeight = dp(48)
                // Locked choices take the disabled colours, not only a lower alpha.
                setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
                    intArrayOf(activity.getColor(R.color.disabled_text), ink)))
                buttonTintList = ColorStateList(
                    arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(activity.getColor(R.color.disabled_text), ink, muted))
                background = android.graphics.drawable.StateListDrawable().apply {
                    addState(intArrayOf(-android.R.attr.state_enabled), background(activity.getColor(R.color.disabled_fill)))
                    addState(intArrayOf(), background(activity.getColor(R.color.card_solid)))
                }
                setPadding(dp(12), dp(6), dp(12), dp(6))
                layoutParams = RadioGroup.LayoutParams(-1, -2).apply { setMargins(0, dp(4), 0, dp(4)) }
            })
        }
        setOnCheckedChangeListener { group, checked ->
            val code = group.findViewById<RadioButton>(checked)?.tag?.toString()?.removePrefix("language-")
            if (!choosingLanguage && code != null) invoke("language:$code")
        }
    }

    /** Hidden while the screen already offers Save log for help: the error card's, or ② itself. */
    private val recoveryExport by lazy { textButton("Save log for help", "export-log") { invoke("export") } }
    private val recoverPatch by lazy { button("Restore interrupted patch", "recover-patch") { invoke("recover") } }
    private val recoverSetup by lazy { textButton("Finish or repair first setup", "recover-setup") { invoke("setup_recover") } }
    private val savedApkActions by lazy {
        listOf(textButton("Reinstall saved game app", "recover-apk") { invoke("installer") },
            text("After reinstalling, check the game app below. Unfinished file changes still need recovery.", Type.BODY, supporting = true),
            textButton("Check restored game app", "verify-game") { invoke("verify") })
    }

    /** Folded; Restore interrupted patch leads, and every other tool sits in a quieter group of text buttons. */
    private val recoveryOptions by lazy {
        column().apply {
            tag = "recovery-options"; visibility = View.GONE
            addView(recoverPatch)
            addView(column().apply {
                tag = "more-recovery-tools"
                addView(text("More recovery tools", Type.LABEL, supporting = true).apply { setPadding(0, dp(12), 0, dp(2)) })
                addView(textButton("Free up space", "free-space-recovery") { invoke("free_space") })
                addView(recoverSetup)
                savedApkActions.forEach { addView(it) }
                addView(recoveryExport)
            })
        }
    }

    /** Offer only the recovery actions the saved records can serve; every one when the records cannot be read. */
    fun recoveryActions(material: RecoveryMaterial?) {
        fun View.offered(value: Boolean) { visibility = if (material == null || value) View.VISIBLE else View.GONE }
        recoverPatch.offered(material?.patch == true)
        recoverSetup.offered(material?.setup == true)
        savedApkActions.forEach { it.offered(material?.savedApk == true) }
    }

    init {
        root.setPadding(dp(20), dp(16), dp(20), dp(32))
        root.background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(activity.getColor(R.color.page_top), activity.getColor(R.color.page_bottom)))
        root.addView(hero())
        val languageCard = card().apply { tag = "language-card" }
        languageCard.addView(eyebrow("01  /  YOUR TRANSLATION"))
        languageCard.addView(text("Language", Type.HEADING))
        showLanguageNote()
        languageCard.addView(languageNote)
        languageCard.addView(languages)
        languageCard.addView(removeButton)
        root.addView(languageCard)
        // ② rewrites itself in place: heading, instruction, the notice line, a result's counts and note, then the button.
        val card = card().apply { tag = "start-card" }
        card.addView(stage)
        card.addView(heading); card.addView(detail); card.addView(noticeRow)
        card.addView(resultItems); card.addView(resultNote); card.addView(primary); card.addView(again)
        // DESIGN.md: the track is disabled-fill, the fill ink.
        bar.progressTintList = ColorStateList.valueOf(ink); bar.indeterminateTintList = ColorStateList.valueOf(ink)
        bar.progressBackgroundTintList = ColorStateList.valueOf(activity.getColor(R.color.disabled_fill))
        bar.visibility = View.GONE; stop.visibility = View.GONE
        card.addView(bar); card.addView(stop)
        root.addView(card)
        // Anything that needs the player sits directly under ②, above the log.
        root.addView(errorBox)
        recovery.tag = "recovery-card"
        root.addView(recovery)
        root.addView(logCard)
        recovery.addView(text("Game won't open?", Type.HEADING))
        recovery.addView(text("Keep the game closed. Use recovery first.", Type.BODY))
        recovery.addView(recoveryToggle)
        recovery.addView(recoveryOptions)
        recovery.visibility = View.GONE
        // The footer: the version, then one row of text buttons; Technical tools opens below it.
        root.addView(column().apply {
            tag = "footer"
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, space(R.dimen.space_md), 0, 0) }
            addView(text("${ui("Patcher version")}: ${BuildConfig.VERSION_NAME}", Type.BODY, supporting = true).apply {
                tag = "patcher-version"; textAlignment = View.TEXT_ALIGNMENT_CENTER
            })
            addView(FooterRow(activity).apply {
                tag = "footer-actions"; isBaselineAligned = false
                addView(footerButton("Technical tools", "show-technical") {
                    advanced.visibility = if (advanced.visibility == View.VISIBLE) View.GONE else View.VISIBLE
                })
                addView(updateButton)
                addView(freeSpaceButton)
            })
        })
        advanced.visibility = View.GONE
        advanced.addView(text("For testing or support", Type.HEADING))
        root.addView(advanced)
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

    fun show(title: String, instruction: String, label: String, action: String, recoveryNeeded: Boolean,
             stage: Stage = Stage.READY) {
        trace("$title | $instruction | $label -> $action, recovery $recoveryNeeded")
        heading.text = ui(title); detail.text = ui(instruction); primary.text = ui(label); next = action
        this.stage.text = ui(stage.eyebrow)
        recovery.visibility = if (recoveryNeeded) View.VISIBLE else View.GONE
        again.visibility = View.GONE
        showItems(emptyList(), "")
        showRecoveryExport()
    }

    /** A result state: its heading and summary, the run's own counts as a list, the login note, then Open game or <label>. */
    fun result(result: UiText.Result, label: String) {
        // A new result starts without the notice an earlier screen left.
        if (trace("${result.english} | $label")) { notice.text = ""; noticeMark.visibility = View.GONE }
        heading.text = result.heading; detail.text = result.summary
        if (result.gameReady) {
            primary.text = ui("Open game"); next = "game"
            again.text = ui(label); again.visibility = View.VISIBLE
        } else {
            primary.text = ui(label); next = "start"
            again.visibility = View.GONE
        }
        stage.text = ui(Stage.DONE.eyebrow)
        recovery.visibility = View.GONE
        showItems(result.items, result.note)
        showRecoveryExport()
    }

    /** Trace <screen> in English once per change; true when it changed. */
    private fun trace(screen: String): Boolean {
        if (screen == shown) return false
        shown = screen; DiagnosticTrace.event("screen", screen)
        return true
    }

    private fun showItems(items: List<String>, note: String) {
        if (items != shownItems) {
            shownItems = items
            resultItems.removeAllViews()
            items.forEach { resultItems.addView(countRow(it)) }
        }
        resultItems.visibility = if (items.isEmpty()) View.GONE else View.VISIBLE
        resultNote.text = note
        resultNote.visibility = if (note.isEmpty()) View.GONE else View.VISIBLE
        showNotice()
    }

    /** "Label: value" as a row with the value at the end, so five-digit counts line up. */
    private fun countRow(item: String) = LinearLayout(activity).apply {
        tag = "result-item"; orientation = LinearLayout.HORIZONTAL
        val split = item.lastIndexOf(": ")
        val label = if (split < 0) item else item.substring(0, split)
        addView(text(label, Type.BODY).apply {
            layoutParams = LinearLayout.LayoutParams(0, -2, 1f); setPadding(0, dp(2), dp(12), dp(2))
        })
        if (split >= 0) addView(text(item.substring(split + 2), Type.BODY).apply {
            typeface = activity.resources.getFont(R.font.barlow_semibold); setPadding(0, dp(2), 0, dp(2))
            textAlignment = View.TEXT_ALIGNMENT_VIEW_END
        })
    }

    fun showRecovery() {
        recovery.visibility = View.VISIBLE
        foldRecovery(true)
        (root.parent as? ScrollView)?.post { (root.parent as? ScrollView)?.smoothScrollTo(0, recovery.top) }
    }

    /** Open or fold the recovery options; the toggle names what a tap will do. */
    private fun foldRecovery(open: Boolean) {
        recoveryOptions.visibility = if (open) View.VISIBLE else View.GONE
        recoveryToggle.text = ui(if (open) "Hide recovery options" else "Show recovery options")
    }

    /** One Save log for help per screen: the recovery group's steps aside for the error card's or ②'s. */
    private fun showRecoveryExport() {
        recoveryExport.visibility = if (errorBox.visibility == View.VISIBLE || next == "export") View.GONE else View.VISIBLE
    }

    /** Show the bar in place of the button while <value>; <step> fills it, and without one it only moves. */
    fun progress(value: Boolean, step: UiText.Step? = null) {
        bar.visibility = if (value) View.VISIBLE else View.GONE
        primary.visibility = if (value) View.GONE else View.VISIBLE
        stop.visibility = if (value) View.VISIBLE else View.GONE
        bar.isIndeterminate = step == null
        if (step != null) { bar.max = step.total; bar.progress = step.number }
    }

    fun logs(lines: List<String>) {
        val value = lines.joinToString("\n")
        logCard.visibility = if (value.isEmpty()) View.GONE else View.VISIBLE
        if (liveLog.text.toString() == value) return
        val follow = logScroll.scrollY + logScroll.height >= liveLog.height - dp(24)
        liveLog.text = value
        if (follow) logScroll.post { logScroll.fullScroll(View.FOCUS_DOWN) }
    }

    fun working(value: Boolean) { primary.isEnabled = !value; again.isEnabled = !value; freeSpaceButton.isEnabled = !value }

    /**
     * A launcher shortcut's <key>, acted on like a tap. Start is refused while ② offers only Save log for help
     * (recovery records cannot be read): the player could not tap Start there either.
     */
    fun shortcut(key: String) { if (key != "start" || next != "export") invoke(key) }

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
            "If another patcher or an older version translated this game, clear its data before you switch languages."
        })
    }

    /** A run reads the language once at its start, so the choice is locked while work is in progress. */
    fun languageEnabled(value: Boolean) {
        if (value) showLanguageNote()
        removeButton.isEnabled = value
        for (index in 0 until languages.childCount) languages.getChildAt(index).isEnabled = value
    }

    fun resultMessage(value: String) {
        if (value == workerNotice) return
        if (value.isEmpty() && notice.text.toString() == ui(workerNotice)) { notice.text = ""; showNotice() }
        workerNotice = value
        if (value.isNotEmpty()) message(value, failure = true)
    }

    /** Show <value> under ②'s instruction; [failure] marks a notice that reports something that went wrong. */
    fun message(value: String, failure: Boolean = false) {
        noticeMark.visibility = if (failure) View.VISIBLE else View.GONE
        if (notice.text.toString() == ui(value)) return
        DiagnosticTrace.event("screen", "Notice: $value")
        notice.text = ui(value); showNotice()
        notice.announceForAccessibility(notice.text)
    }

    /** Hidden when empty or when it only repeats the instruction. */
    private fun showNotice() {
        noticeRow.visibility = if (notice.text.isEmpty() || notice.text.toString() == detail.text.toString()) View.GONE else View.VISIBLE
    }

    /** Show the cause of <raw> on screen and keep all of it for copying; empty hides the box. */
    fun errorDetails(raw: String) {
        if (raw == errorRaw) return
        errorRaw = raw
        errorText.text = ErrorSummary.cause(raw)
        errorBox.visibility = if (raw.isBlank()) View.GONE else View.VISIBLE
        showRecoveryExport()
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

    /** A content card; the warning and error cards pass their surface and accent colours. */
    private fun card(fill: Int = R.color.card, edge: Int = R.color.card_edge) = column().apply {
        background = background(activity.getColor(fill)).apply { setStroke(dp(1), activity.getColor(edge)) }
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
    /** [plain] draws a text button: no fill or edge, the ripple kept inside the corners. */
    private fun button(label: String, testTag: String?, primaryAction: Boolean = false, plain: Boolean = false,
                       callback: () -> Unit) = Button(activity).apply {
        text = ui(label); tag = testTag; isAllCaps = false; minHeight = dp(60); minimumHeight = dp(60)
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_button))
        typeface = activity.resources.getFont(R.font.barlow_semibold)
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(activity.getColor(R.color.disabled_text), activity.getColor(if (primaryAction) R.color.on_panel else R.color.ink))))
        // Primary: the panel gradient. Secondary: the card fill with a 1 dp ink edge at 30 %. Text: nothing.
        val enabled = when {
            primaryAction -> GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(activity.getColor(R.color.panel_top), activity.getColor(R.color.panel_bottom))).apply {
                    cornerRadius = activity.resources.getDimension(R.dimen.corner_button)
                }
            plain -> android.graphics.drawable.ColorDrawable(Color.TRANSPARENT)
            else -> background(activity.getColor(R.color.card)).apply { setStroke(dp(1), withAlpha(ink, 0.3f)) }
        }
        val states = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled), background(activity.getColor(R.color.disabled_fill)))
            addState(intArrayOf(), enabled)
        }
        background = RippleDrawable(ColorStateList.valueOf(withAlpha(ink, 0.18f)), states, if (plain) background(Color.WHITE) else null)
        setPadding(dp(14), dp(12), dp(14), dp(12))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(6), 0, dp(6)) }
        setOnClickListener { callback() }
    }

    /** DESIGN.md's text button: `ink` text with no fill or edge, still 60 dp tall, spanning the card with its label at the start. */
    private fun textButton(label: String, testTag: String, callback: () -> Unit) =
        button(label, testTag, plain = true, callback = callback).apply {
            gravity = android.view.Gravity.START or android.view.Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(2), 0, dp(2)) }
        }

    /** A footer text button: the three share the row equally, and a long label wraps instead of leaving it. */
    private fun footerButton(label: String, testTag: String, callback: () -> Unit) =
        button(label, testTag, plain = true, callback = callback).apply {
            setPadding(dp(6), dp(8), dp(6), dp(8))
            layoutParams = LinearLayout.LayoutParams(0, -2, 1f).apply { setMargins(dp(2), dp(4), dp(2), dp(4)) }
        }
}

/**
 * The footer's text buttons: side by side, sharing the width, while every label's longest word fits its
 * share; stacked one per line otherwise, so a large system font never breaks a label inside a word.
 */
private class FooterRow(context: android.content.Context) : LinearLayout(context) {
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val share = (MeasureSpec.getSize(widthMeasureSpec) - paddingLeft - paddingRight) / childCount.coerceAtLeast(1)
        val buttons = (0 until childCount).map { getChildAt(it) }.filterIsInstance<TextView>()
        val fits = buttons.all { button ->
            val margins = (button.layoutParams as MarginLayoutParams).let { it.leftMargin + it.rightMargin }
            val word = button.text.split(Regex("\\s+")).maxOf { button.paint.measureText(it) }
            word + button.paddingLeft + button.paddingRight + margins <= share
        }
        val wanted = if (fits) HORIZONTAL else VERTICAL
        if (orientation != wanted) {
            orientation = wanted
            buttons.forEach { (it.layoutParams as LayoutParams).apply { width = if (fits) 0 else -1; weight = if (fits) 1f else 0f } }
        }
        super.onMeasure(widthMeasureSpec, heightMeasureSpec)
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
