package dev.halixm.hokacepatcher

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.graphics.drawable.RippleDrawable
import android.text.SpannableString
import android.text.Spanned
import android.text.style.RelativeSizeSpan
import android.text.style.TypefaceSpan
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.GridLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kotlin.math.roundToInt

/** One start action; show only work progress and checkpoints that need the user. */
class GuidedHome(private val activity: Activity, private val invoke: (String) -> Unit) {
    /** DESIGN.md's text styles for the guided screen. */
    private enum class Type(val size: Int, val font: Int) {
        HEADING(R.dimen.type_heading, R.font.aceheading_bold),
        BODY(R.dimen.type_body, R.font.commissioner_regular),
        LABEL(R.dimen.type_label, R.font.commissioner_semibold),
    }

    /**
     * What ③ is doing, named by its eyebrow so a failure, a result or a shell provider that is not ready
     * never sits under "READY TO PLAY".
     */
    enum class Stage(val eyebrow: String) {
        READY("03  /  READY TO PLAY"), ACCESS("03  /  NEEDS ACCESS"), WORKING("03  /  IN PROGRESS"),
        DONE("03  /  DONE"), ATTENTION("03  /  NEEDS ATTENTION"),
    }

    private val ink = activity.getColor(R.color.ink)
    private val muted = activity.getColor(R.color.text_muted)
    private val root = column()
    private val setup = card(sweep = true)
    private val stage = eyebrow(Stage.READY.eyebrow).apply { tag = "start-eyebrow" }
    private var shownStage: Pair<Stage, Boolean>? = null
    private val heading = text("Let's get started", Type.HEADING)
    private val detail = text("", Type.BODY)
    private val primary = button("Start", "next-step", true) { invoke(next) }
    /** Under Open game: Downloads finished at the download wait, or Start another patch after a result. */
    private var secondaryAction = "start"
    private val again = button("Start another patch", "start-again") { invoke(secondaryAction) }.apply { visibility = View.GONE }
    private val recovery = card(R.color.warning_surface, R.color.warning)
    private val recoveryToggle = button("Show recovery options", "show-recovery") {
        foldRecovery(recoveryOptions.visibility != View.VISIBLE)
    }
    private var shown = ""
    private val stop = button("Stop safely", "stop-automatic") { invoke("stop") }
    private val actions = column()
    /** Running: the bar takes the button's place; determinate while the worker reports a step. */
    private val bar = android.widget.ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal).apply {
        tag = "progress-bar"
        layoutParams = LinearLayout.LayoutParams(-1, dp(8)).apply { setMargins(0, dp(12), 0, dp(12)) }
    }
    /** One ink line under ③'s instruction; a notice that reports a failure leads with the warning disc. */
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
    private val useTwoColumns = activity.resources.configuration.run { screenWidthDp >= 360 && fontScale <= 1.15f }
    private val resultItems = GridLayout(activity).apply {
        tag = "result-items"; visibility = View.GONE
        columnCount = if (useTwoColumns) 2 else 1
    }
    private val resultNote = text("", Type.BODY).apply {
        tag = "result-note"; visibility = View.GONE
        background = background(activity.getColor(R.color.warning_surface))
        setPadding(dp(12), dp(10), dp(12), dp(10))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) }
    }
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
        typeface = activity.resources.getFont(R.font.fragmentmono_regular)
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_log))
        setPadding(dp(12), dp(8), dp(12), dp(8))
    }
    private val logScroll = LogScrollView(activity).apply {
        addView(liveLog)
        layoutParams = LinearLayout.LayoutParams(-1, dp(180)).apply { topMargin = dp(8) }
        tag = "live-log-scroll"
        background = background(activity.getColor(R.color.surface), R.dimen.corner_field)
    }
    private val logCard = card().apply {
        visibility = View.GONE
        addView(text("Patching activity", Type.HEADING))
        addView(logScroll)
    }
    val advanced = card()
    private val updateButton = ImageButton(activity).apply {
        tag = "check-app-update"
        setImageResource(R.drawable.ic_update)
        imageTintList = ColorStateList(
            arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(activity.getColor(R.color.page_bottom), activity.getColor(R.color.on_panel_muted)),
        )
        scaleType = ImageView.ScaleType.CENTER_INSIDE
        setPadding(dp(14), dp(14), dp(14), dp(14))
        val ripple = ColorStateList.valueOf(withAlpha(activity.getColor(R.color.on_panel), 0.24f))
        background = RippleDrawable(ripple, null, background(Color.WHITE, R.dimen.corner_button))
        layoutParams = LinearLayout.LayoutParams(dp(48), dp(48))
        setOnClickListener { invoke("check_update") }
    }
    private val freeSpaceButton = footerButton("Free up space", "free-space") { invoke("free_space") }
    private var next = "start"
    private var workerNotice = ""
    private var choosingLanguage = false
    private val languages = RadioGroup(activity).apply {
        tag = "language-picker"
        orientation = if (useTwoColumns) LinearLayout.HORIZONTAL else LinearLayout.VERTICAL
        isBaselineAligned = false
        PatchLanguage.choices.forEach { (code, name) ->
            val option = choice(name, "language-$code")
            if (useTwoColumns) option.layoutParams = RadioGroup.LayoutParams(0, -1, 1f).apply {
                setMargins(if (childCount == 0) 0 else dp(8), dp(4), 0, dp(4))
            }
            addView(option)
        }
        setOnCheckedChangeListener { group, checked ->
            val code = group.findViewById<RadioButton>(checked)?.tag?.toString()?.removePrefix("language-")
            if (!choosingLanguage && code != null) invoke("language:$code")
        }
    }
    private var choosingProvider = false
    /** ② Shell provider: Wireless debugging, Shizuku, then Root, in [ShellProvider] order. */
    private val providers = RadioGroup(activity).apply {
        tag = "provider-picker"; orientation = LinearLayout.VERTICAL
        ShellProvider.entries.forEach { provider ->
            val label = ui(provider.label)
            val description = ui(when (provider) {
                ShellProvider.WIRELESS -> "Pair over Wi-Fi. No extra app needed."
                ShellProvider.SHIZUKU -> "Requires the Shizuku app to be running."
                ShellProvider.ROOT -> "Requires root. Keeps the installed game app."
            })
            addView(choice(label, "provider-${provider.key}").apply {
                text = SpannableString("$label\n$description").apply {
                    setSpan(RelativeSizeSpan(0.88f), label.length + 1, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                    setSpan(TypefaceSpan(activity.resources.getFont(R.font.commissioner_regular)),
                        label.length + 1, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
            })
        }
        setOnCheckedChangeListener { group, checked ->
            val key = group.findViewById<RadioButton>(checked)?.tag?.toString()?.removePrefix("provider-")
            if (!choosingProvider && key != null) invoke("provider:$key")
        }
    }
    /** The chosen provider's numbered guide, one line per step; its tag names the provider shown. */
    private val guide = column().apply { tag = "provider-guide" }
    private val guideToggle = textButton("Show connection guide", "toggle-provider-guide") {
        guide.visibility = if (guide.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        guideToggleLabel()
    }
    private var guideShown: ShellProvider? = null

    /** Hidden while the screen already offers Save log for help: the error card's, or ③ itself. */
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
        root.setPadding(dp(16), dp(8), dp(16), dp(16))
        root.addView(hero())
        checkingUpdate(false)

        val status = card(sweep = true).apply { tag = "start-card" }
        status.addView(stage)
        status.addView(heading); status.addView(detail); status.addView(noticeRow)
        status.addView(resultItems); status.addView(resultNote)
        bar.progressTintList = ColorStateList.valueOf(activity.getColor(R.color.panel_bottom))
        bar.indeterminateTintList = bar.progressTintList
        bar.progressBackgroundTintList = ColorStateList.valueOf(activity.getColor(R.color.surface_subtle))
        bar.visibility = View.GONE; stop.visibility = View.GONE
        status.addView(bar)
        root.addView(status)
        styleStage(Stage.READY)

        val languageCard = column().apply { tag = "language-card" }
        languageCard.addView(text("Translation language", Type.HEADING))
        showLanguageNote()
        languageCard.addView(languageNote)
        languageCard.addView(languages)
        languageCard.addView(removeButton)
        setup.addView(languageCard)
        setup.addView(View(activity).apply {
            setBackgroundColor(activity.getColor(R.color.card_edge))
            layoutParams = LinearLayout.LayoutParams(-1, dp(1)).apply { topMargin = dp(12); bottomMargin = dp(8) }
        })
        setup.addView(column().apply {
            tag = "provider-card"
            addView(text("Connection method", Type.HEADING))
            addView(providers)
            addView(guideToggle)
            addView(guide)
        })
        guide.visibility = View.GONE
        root.addView(errorBox)
        recovery.tag = "recovery-card"
        root.addView(recovery)
        root.addView(setup)
        root.addView(logCard)
        recovery.addView(text("Game won't open?", Type.HEADING))
        recovery.addView(text("Keep the game closed. Use recovery first.", Type.BODY))
        recovery.addView(recoveryToggle)
        recovery.addView(recoveryOptions)
        recovery.visibility = View.GONE
        advanced.visibility = View.GONE
        advanced.addView(text("For testing or support", Type.HEADING))
        root.addView(advanced)
        val scroll = ScrollView(activity).apply {
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
            isFillViewport = true
            addView(root)
        }
        actions.apply {
            tag = "footer"
            setPadding(dp(16), dp(4), dp(16), dp(4))
            clipToPadding = false
            primary.elevation = dp(6).toFloat()
            addView(primary); addView(again); addView(stop)
            addView(FooterRow(activity).apply {
                tag = "footer-actions"
                gravity = Gravity.CENTER_HORIZONTAL
                isBaselineAligned = false
                addView(footerButton("Technical tools", "show-technical") {
                    advanced.visibility = if (advanced.visibility == View.VISIBLE) View.GONE else View.VISIBLE
                    if (advanced.visibility == View.VISIBLE) {
                        scroll.post { scroll.smoothScrollTo(0, advanced.top) }
                    }
                })
                addView(freeSpaceButton)
            })
        }
        activity.setContentView(column().apply {
            tag = "guided-page"
            val gradient = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(activity.getColor(R.color.page_top), activity.getColor(R.color.page_mid),
                    activity.getColor(R.color.page_bottom)))
            // FigCraft places the watermark behind the status bar, masthead, and cards.
            val watermark = requireNotNull(activity.getDrawable(R.drawable.hok_ace_logo_white)).mutate()
            watermark.alpha = 38 // 15% opacity.
            background = LayerDrawable(arrayOf(gradient, watermark)).apply {
                setLayerSize(1, dp(208), dp(208))
                setLayerGravity(1, Gravity.TOP or Gravity.END)
                setLayerInsetRelative(1, 0, dp(8), dp(2), 0)
            }
            addView(scroll)
            addView(actions)
            setOnApplyWindowInsetsListener { view, insets ->
                val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or
                    android.view.WindowInsets.Type.displayCutout())
                view.setPadding(bars.left, bars.top, bars.right, 0)
                actions.setPadding(dp(16), dp(4), dp(16), dp(4) + bars.bottom)
                insets
            }
        })
    }

    fun show(title: String, instruction: String, label: String, action: String, recoveryNeeded: Boolean,
             stage: Stage = Stage.READY, secondaryLabel: String? = null, secondaryAction: String = "start") {
        trace("$title | $instruction | $label -> $action, recovery $recoveryNeeded")
        heading.text = ui(title); detail.text = ui(instruction)
        primary.text = ui(if (stage == Stage.READY && label == "Start") "Start patching" else label)
        next = action
        styleStage(stage)
        recovery.visibility = if (recoveryNeeded) View.VISIBLE else View.GONE
        this.secondaryAction = secondaryAction
        again.text = secondaryLabel?.let(::ui).orEmpty()
        again.visibility = if (secondaryLabel == null) View.GONE else View.VISIBLE
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
            secondaryAction = "start"
            again.text = ui(label); again.visibility = View.VISIBLE
        } else {
            primary.text = ui(label); next = "start"
            again.visibility = View.GONE
        }
        styleStage(Stage.DONE, verified = result.gameReady)
        recovery.visibility = View.GONE
        showItems(result.items, result.note)
        showRecoveryExport()
    }

    private fun styleStage(state: Stage, verified: Boolean = false) {
        val nextStage = state to verified
        if (shownStage == nextStage) return
        shownStage = nextStage
        val (fill, foreground) = when {
            verified -> R.color.success_surface to R.color.success
            state == Stage.ACCESS || state == Stage.ATTENTION -> R.color.warning_surface to R.color.warning
            else -> R.color.surface_subtle to R.color.ink
        }
        stage.text = ui(state.eyebrow).substringAfter("/").trim()
        stage.setTextColor(activity.getColor(foreground))
        stage.background = background(activity.getColor(fill))
        stage.layoutParams = LinearLayout.LayoutParams(-2, -2)
        stage.setPadding(dp(12), dp(4), dp(12), dp(4))
        stage.visibility = if (state == Stage.READY || state == Stage.ACCESS) View.GONE else View.VISIBLE
        heading.setTextColor(if (state == Stage.ACCESS) activity.getColor(foreground) else ink)
        setup.visibility = if (state == Stage.WORKING) View.GONE else View.VISIBLE
        if (state == Stage.WORKING || state == Stage.DONE) (root.parent as? ScrollView)?.let { scroll ->
            scroll.post { scroll.scrollTo(0, 0) }
        }
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
            items.forEachIndexed { index, item ->
                val columns = resultItems.columnCount
                resultItems.addView(countTile(item), GridLayout.LayoutParams(
                    GridLayout.spec(index / columns, GridLayout.FILL),
                    GridLayout.spec(index % columns, GridLayout.FILL, 1f)
                ).apply {
                    width = 0
                    height = -2
                    setMargins(0, 0, if (columns == 2 && index % columns == 0) dp(8) else 0, dp(8))
                })
            }
        }
        resultItems.visibility = if (items.isEmpty()) View.GONE else View.VISIBLE
        resultNote.text = note
        resultNote.visibility = if (note.isEmpty()) View.GONE else View.VISIBLE
        showNotice()
    }

    private fun countTile(item: String) = column().apply {
        tag = "result-item"
        background = background(activity.getColor(R.color.surface), R.dimen.corner_field)
        setPadding(dp(12), dp(8), dp(12), dp(8))
        val split = item.lastIndexOf(": ")
        val label = if (split < 0) item else item.substring(0, split)
        if (split >= 0) addView(text(item.substring(split + 2), Type.HEADING).apply {
            isAccessibilityHeading = false
            setPadding(0, 0, 0, 0)
        })
        addView(text(label, Type.LABEL, supporting = true).apply { setPadding(0, dp(2), 0, 0) })
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

    /** One Save log for help per screen: the recovery group's steps aside for the error card's or ③'s. */
    private fun showRecoveryExport() {
        recoveryExport.visibility = if (errorBox.visibility == View.VISIBLE || next == "export") View.GONE else View.VISIBLE
    }

    /** Show the bar in place of the button while <value>; <step> fills it, and without one it only moves. */
    fun progress(value: Boolean, step: UiText.Step? = null, canStop: Boolean = value) {
        bar.visibility = if (value) View.VISIBLE else View.GONE
        primary.visibility = if (value) View.GONE else View.VISIBLE
        stop.visibility = if (canStop) View.VISIBLE else View.GONE
        bar.isIndeterminate = step == null
        if (step != null) { bar.max = step.total; bar.progress = step.number }
    }

    /** Stop is saved and being acted on: the button says so and cannot send a second Stop. */
    fun stopping(value: Boolean) {
        stop.isEnabled = !value
        stop.text = ui(if (value) "Stopping safely" else "Stop safely")
    }

    fun logs(lines: List<String>) {
        val value = lines.joinToString("\n")
        logCard.visibility = if (value.isEmpty()) View.GONE else View.VISIBLE
        if (liveLog.text.toString() == value) return
        val follow = logScroll.scrollY + logScroll.height >= liveLog.height - dp(24)
        liveLog.text = value
        if (follow) logScroll.post {
            logScroll.scrollTo(0, (liveLog.height - logScroll.height).coerceAtLeast(0))
        }
    }

    fun working(value: Boolean) { primary.isEnabled = !value; again.isEnabled = !value; freeSpaceButton.isEnabled = !value }

    /**
     * A launcher shortcut's <key>, acted on like a tap. Start is refused while ③ offers a recovery action instead
     * (Recovery needs attention): the player could not tap Start there either.
     */
    fun shortcut(key: String) { if (key != "start" || next !in RECOVERY_KEYS) invoke(key) }

    private companion object {
        /** ③'s actions while recovery is unresolved; none of them starts a fresh patch. */
        val RECOVERY_KEYS = setOf("export", "recovery_options", "recover_attention")
    }

    fun checkingUpdate(value: Boolean) {
        updateButton.isEnabled = !value
        val label = ui(if (value) "Checking for updates…" else "Check for updates")
        updateButton.contentDescription = label
        updateButton.tooltipText = label
    }

    /** Show <code> as chosen without reporting it back as a new choice. */
    fun language(code: String) {
        val button = languages.findViewWithTag<RadioButton>("language-$code") ?: return
        if (button.isChecked) return
        choosingLanguage = true
        try { languages.check(button.id) } finally { choosingLanguage = false }
    }

    /** Show <provider> as chosen, without reporting it back as a new choice, and its guide. */
    fun provider(provider: ShellProvider) {
        val button = providers.findViewWithTag<RadioButton>("provider-${provider.key}") ?: return
        if (!button.isChecked) {
            choosingProvider = true
            try { providers.check(button.id) } finally { choosingProvider = false }
        }
        if (guideShown == provider) return
        guideShown = provider
        guide.removeAllViews()
        guideLines(provider).forEach { guide.addView(text(it, Type.BODY)) }
    }

    private fun guideToggleLabel() {
        guideToggle.text = ui(if (guide.visibility == View.VISIBLE) "Hide connection guide" else "Show connection guide")
    }

    /** Each provider's numbered steps; one this build cannot start says so instead. */
    private fun guideLines(provider: ShellProvider): List<String> = when {
        !provider.available -> listOf(UiText.string(activity, "provider_not_ready", "provider" to ui(provider.label)))
        provider == ShellProvider.WIRELESS -> listOf(ui("1. Connect this phone to Wi-Fi."),
            ui("2. Turn on Developer options: in About phone, tap Build number seven times."),
            ui("3. In Developer options, turn on Wireless debugging."),
            ui("4. Tap Pair here. In Wireless debugging, tap Pair device with pairing code, then type the six-digit code into the patcher's notification."),
            ui("5. Come back here and tap Start. Keep Wi-Fi and Wireless debugging on until the work is done."))
        provider == ShellProvider.ROOT -> listOf(ui("1. Root this phone with a root manager, such as KernelSU, Magisk or APatch."),
            ui("2. Allow root for HOK ACE: in KernelSU, under Superuser, then close and reopen HOK ACE; Magisk and APatch ask when you tap Start."),
            ui("3. Come back here and tap Start. The patcher writes the game files itself and never replaces the game app."),
            ui("4. Hiding root from the game is up to you; the patcher does not touch it."))

        else -> listOf(ui("1. Install Shizuku from Google Play."), ui("2. Start Shizuku, following the steps it shows."),
            ui("3. Come back here and tap Start. Allow HOK ACE when Shizuku asks."))
    }

    /** A run reads the provider once at its start, so the choice is locked while work is in progress. */
    fun providerEnabled(value: Boolean) {
        for (index in 0 until providers.childCount) providers.getChildAt(index).isEnabled = value
    }

    /** Whether switching needs a clear: not once the patcher keeps a pristine delta for the phone. */
    private fun showLanguageNote() {
        // Remove translation needs the delta, so it is offered only while one is kept.
        removeButton.visibility = if (PristineDelta.held(activity)) View.VISIBLE else View.GONE
        languageNote.text = ui(if (PristineDelta.held(activity)) {
            "Original files stay backed up so you can switch anytime."
        } else {
            "If another patcher or an older version translated this game, clear its data before you switch languages."
        })
    }

    /**
     * A run reads the language once at its start, so the choice is locked while work is in progress. <locked>: an
     * unresolved saved action holds it, and the note says how to change it (finish it, or Stop safely).
     */
    fun languageEnabled(value: Boolean, locked: Boolean = false) {
        if (locked) languageNote.text = UiText.string(activity, "choices_locked")
        else if (value || languageNote.text.toString() == UiText.string(activity, "choices_locked")) showLanguageNote()
        removeButton.isEnabled = value
        for (index in 0 until languages.childCount) languages.getChildAt(index).isEnabled = value
    }

    fun resultMessage(value: String) {
        if (value == workerNotice) return
        if (value.isEmpty() && notice.text.toString() == ui(workerNotice)) { notice.text = ""; showNotice() }
        workerNotice = value
        if (value.isNotEmpty()) message(value, failure = true)
    }

    /** Show <value> under ③'s instruction; [failure] marks a notice that reports something that went wrong. */
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

    /** One picker choice, a full-width radio row; a locked choice takes the disabled colours, not only a lower alpha. */
    private fun choice(label: String, testTag: String) = RadioButton(activity).apply {
        id = View.generateViewId(); text = label; tag = testTag
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_button))
        typeface = activity.resources.getFont(R.font.commissioner_semibold)
        minHeight = dp(48)
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(activity.getColor(R.color.disabled_text), ink)))
        buttonTintList = ColorStateList(
            arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf(android.R.attr.state_checked), intArrayOf()),
            intArrayOf(activity.getColor(R.color.disabled_text), ink, muted))
        val states = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled), background(activity.getColor(R.color.disabled_fill), R.dimen.corner_field))
            addState(intArrayOf(android.R.attr.state_checked), background(activity.getColor(R.color.surface_subtle), R.dimen.corner_field))
            addState(intArrayOf(), background(Color.TRANSPARENT, R.dimen.corner_field))
        }
        background = RippleDrawable(ColorStateList.valueOf(withAlpha(ink, 0.16f)), states,
            background(Color.WHITE, R.dimen.corner_field))
        setPadding(dp(12), dp(6), dp(12), dp(6))
        layoutParams = RadioGroup.LayoutParams(-1, -2).apply { setMargins(0, dp(4), 0, dp(4)) }
    }

    private fun dp(value: Int) = (value * activity.resources.displayMetrics.density).toInt()
    private fun space(token: Int) = activity.resources.getDimensionPixelSize(token)
    private fun withAlpha(color: Int, alpha: Float) = Color.argb(Math.round(alpha * 255), Color.red(color), Color.green(color), Color.blue(color))
    private fun column() = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
    private fun background(color: Int, radius: Int = R.dimen.corner_card) = GradientDrawable().apply {
        setColor(color); cornerRadius = activity.resources.getDimension(radius)
    }
    private fun eyebrow(value: String) = text(value, Type.LABEL, supporting = true).apply {
        setPadding(0, 0, 0, dp(4))
    }

    private fun hero() = column().apply {
        tag = "patcher-masthead"
        setPadding(dp(4), dp(8), dp(4), 0)
        addView(ImageView(activity).apply {
            tag = "patcher-wordmark"
            setImageResource(R.drawable.honor_of_kings_ace_wordmark)
            contentDescription = "HONOR OF KINGS ACE"
            isAccessibilityHeading = true
            scaleType = ImageView.ScaleType.FIT_START
            // The PNG was drawn at 4x the display size. Keep its aspect ratio as the font scales.
            val contentWidth = (activity.resources.displayMetrics.widthPixels - dp(40)).coerceAtLeast(1)
            val scale = minOf(
                activity.resources.getDimension(R.dimen.type_title) / 128f,
                contentWidth.toFloat() / drawable.intrinsicWidth,
            )
            layoutParams = LinearLayout.LayoutParams(
                (drawable.intrinsicWidth * scale).roundToInt(),
                (drawable.intrinsicHeight * scale).roundToInt(),
            )
        })
        addView(LinearLayout(activity).apply {
            gravity = Gravity.CENTER_VERTICAL
            isBaselineAligned = false
            layoutParams = LinearLayout.LayoutParams(-2, -2)
            addView(text("${ui("Community patcher")} · v${BuildConfig.VERSION_NAME}", Type.LABEL).apply {
                tag = "patcher-version"
                setTextColor(activity.getColor(R.color.accent_gold))
                layoutParams = LinearLayout.LayoutParams(-2, -2, 1f)
            })
            addView(updateButton)
        })
    }

    /** A tonal card, or a solid semantic surface with its own accent edge. */
    private fun card(fill: Int = R.color.card, edge: Int? = null, sweep: Boolean = false) = column().apply {
        background = if (sweep) GradientDrawable().apply {
            orientation = GradientDrawable.Orientation.LEFT_RIGHT
            setColors(
                intArrayOf(R.color.surface, R.color.surface, R.color.card_sweep_lilac,
                    R.color.card_sweep_blue, R.color.surface_subtle).map(activity::getColor).toIntArray(),
                floatArrayOf(0f, 0.2f, 0.48f, 0.76f, 1f),
            )
            cornerRadius = activity.resources.getDimension(R.dimen.corner_card)
        } else background(activity.getColor(fill)).apply {
            edge?.let { setStroke(dp(1), activity.getColor(it)) }
        }
        space(R.dimen.space_lg).let { setPadding(it, it, it, it) }
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, space(R.dimen.space_md), 0, 0) }
    }
    /** Headings are marked as headings for screen readers by their type step, not by their size. */
    private fun text(value: String, type: Type, supporting: Boolean = false) = TextView(activity).apply {
        text = ui(value); setTextColor(if (supporting) muted else ink)
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(type.size))
        typeface = activity.resources.getFont(type.font)
        setPadding(0, dp(4), 0, dp(6)); setLineSpacing(dp(2).toFloat(), 1f)
        if (type == Type.LABEL) letterSpacing = activity.resources.getFloat(R.dimen.type_label_tracking)
        if (type == Type.HEADING) isAccessibilityHeading = true
    }
    /** [plain] draws a text button: no fill or edge, the ripple kept inside the corners. */
    private fun button(label: String, testTag: String?, primaryAction: Boolean = false, plain: Boolean = false,
                       callback: () -> Unit) = Button(activity).apply {
        text = ui(label); tag = testTag; isAllCaps = false
        stateListAnimator = null
        minHeight = dp(if (primaryAction) 56 else 48); minimumHeight = minHeight
        setTextSize(TypedValue.COMPLEX_UNIT_PX, activity.resources.getDimension(R.dimen.type_button))
        typeface = activity.resources.getFont(R.font.commissioner_semibold)
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(activity.getColor(R.color.disabled_text), activity.getColor(if (primaryAction) R.color.on_panel else R.color.ink))))
        // Primary: the panel gradient. Secondary: the card fill with a 1 dp ink edge at 30 %. Text: nothing.
        val enabled = when {
            primaryAction -> GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(activity.getColor(R.color.panel_top), activity.getColor(R.color.panel_bottom))).apply {
                    cornerRadius = activity.resources.getDimension(R.dimen.corner_button)
                }
            plain -> android.graphics.drawable.ColorDrawable(Color.TRANSPARENT)
            else -> background(activity.getColor(R.color.surface)).apply {
                cornerRadius = activity.resources.getDimension(R.dimen.corner_button)
                setStroke(dp(1), activity.getColor(R.color.outline))
            }
        }
        val states = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled), background(activity.getColor(R.color.disabled_fill)).apply {
                cornerRadius = activity.resources.getDimension(R.dimen.corner_button)
            })
            addState(intArrayOf(), enabled)
        }
        background = RippleDrawable(ColorStateList.valueOf(withAlpha(ink, 0.18f)), states, if (plain) background(Color.WHITE) else null)
        setPadding(dp(14), dp(12), dp(14), dp(12))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(6), 0, dp(6)) }
        setOnClickListener { callback() }
    }

    /** A full-width text button with a 48 dp touch target and leading alignment. */
    private fun textButton(label: String, testTag: String, callback: () -> Unit) =
        button(label, testTag, plain = true, callback = callback).apply {
            gravity = android.view.Gravity.START or android.view.Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(2), 0, dp(2)) }
        }

    /** Footer actions share the row while their labels fit. */
    private fun footerButton(label: String, testTag: String, callback: () -> Unit) =
        button(label, testTag, plain = true, callback = callback).apply {
            minWidth = dp(48)
            minimumWidth = minWidth
            setPadding(dp(12), dp(8), dp(12), dp(8))
            layoutParams = LinearLayout.LayoutParams(-2, -2)
        }
}

/**
 * Keep the utility buttons compact when both labels fit on one line and stack them when needed.
 */
private class FooterRow(context: android.content.Context) : LinearLayout(context) {
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val available = MeasureSpec.getSize(widthMeasureSpec) - paddingLeft - paddingRight
        val buttons = (0 until childCount).map { getChildAt(it) }.filterIsInstance<TextView>()
        val required = buttons.sumOf { button ->
            val label = kotlin.math.ceil(button.paint.measureText(button.text.toString())).toInt()
            maxOf(button.minimumWidth, label + button.paddingLeft + button.paddingRight)
        }
        val fits = required <= available
        val wanted = if (fits) HORIZONTAL else VERTICAL
        if (orientation != wanted) {
            orientation = wanted
            buttons.forEach { it.layoutParams.width = if (fits) LayoutParams.WRAP_CONTENT else LayoutParams.MATCH_PARENT }
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
