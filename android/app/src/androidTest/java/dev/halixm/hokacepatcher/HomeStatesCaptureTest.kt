package dev.halixm.hokacepatcher

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The home screen brief's states (`.scratch/shared-design/home-screen-brief.md`, section 5), each
 * drawn as a full page in both languages at the phone's current font size, saved to `cache/home-states/<code>-<fontScale>-<state>.png`. Fails on any shown text that is
 * ellipsized, broken inside a word, taller than its view, or wider than the page. UI only: never
 * starts a worker. Run it once per font size (`settings put system font_scale`).
 */
class HomeStatesCaptureTest {
    private val counts = JSONObject().put("text_tables", 12345).put("applied_textures", 99999)
        .put("skipped_tables", 12345).put("skipped_textures", 99999)
    private val logLines = (1..40).map { "Log line $it: checking package files" }

    private val states: List<Pair<String, (GuidedHome, Activity) -> Unit>> = listOf(
        "idle" to { home, _ ->
            home.show("Ready when you are", "Tap Start. We will check your game and prepare everything. Keep the game closed while we work.", "Start", "start", false)
        },
        "install-shizuku" to { home, _ ->
            home.show("Install Shizuku", "Shizuku is required. Install it from Google Play, start it, then return here.", "Get Shizuku", "start", false, GuidedHome.Stage.SHIZUKU)
        },
        "start-shizuku" to { home, _ ->
            home.show("Start Shizuku", "Shizuku must be running. Start it, then return here. We will continue automatically.", "Open Shizuku", "start", false, GuidedHome.Stage.SHIZUKU)
        },
        "running" to { home, activity ->
            val step = UiText.step(PatchLanguage.current(activity), JSONObject().put("status", "running")
                .put("action", "patch").put("step", "unlock_access").put("steps", 6))!!
            home.show("Working on your game", step.line, "Please wait", "start", false, GuidedHome.Stage.WORKING)
            home.working(true); home.languageEnabled(false); home.progress(true, step); home.logs(logLines)
        },
        "recovery" to { home, _ ->
            home.recoveryActions(null)
            home.show("Finish your game safely", "We will check unfinished work and recover it before patching.", "Continue", "start", true, GuidedHome.Stage.ATTENTION)
            home.showRecovery()
        },
        "storage" to { home, activity ->
            val storage = UiText.storage(activity, StorageBudget.explainFailure("2000000000 bytes required, 1000000000 available")!!)
            home.show("Work stopped", storage, "Try again", "start", false, GuidedHome.Stage.ATTENTION)
            home.errorDetails("ERROR: 2000000000 bytes required, 1000000000 available"); home.logs(logLines)
        },
        "interrupted" to { home, _ ->
            home.show("Finish your game safely", "We will check unfinished work and recover it before patching.", "Continue", "start", true, GuidedHome.Stage.ATTENTION)
            home.message("Work was interrupted. Tap Start to check and restore unfinished work.", failure = true)
        },
        "success" to { home, activity ->
            home.result(UiText.result(PatchLanguage.current(activity), JSONObject().put("status", "complete").put("counts", counts))!!, "Start another patch")
            home.logs(logLines)
        },
        "removed" to { home, activity ->
            home.result(UiText.result(PatchLanguage.current(activity), JSONObject().put("status", "complete").put("removed", 12345))!!, "Start another patch")
        },
        "unconfirmed" to { home, activity ->
            home.result(UiText.result(PatchLanguage.current(activity), JSONObject().put("status", "recovered_unconfirmed"))!!, "Start another patch")
        },
        "space-freed" to { home, activity ->
            home.result(UiText.result(PatchLanguage.current(activity), JSONObject().put("status", "space_freed")
                .put("freed_bytes", 12_345_000_000L).put("free_bytes", 99_999_000_000L))!!, "Start")
        },
        "notice" to { home, _ ->
            home.show("Ready when you are", "Tap Start. We will check your game and prepare everything. Keep the game closed while we work.", "Start", "start", false)
            home.message("Access was not allowed. Tap Start to try again.", failure = true)
        },
        "notice-info" to { home, _ ->
            home.show("Ready when you are", "Tap Start. We will check your game and prepare everything. Keep the game closed while we work.", "Start", "start", false)
            home.message("Finish the current work before freeing space.")
        },
        "failed" to { home, _ ->
            home.recoveryActions(null)
            home.show("Work stopped", "The phone refused a step, although Shizuku is working. Keep the game closed. Check recovery options below, or save a log for help.", "Open recovery options", "recovery_options", true, GuidedHome.Stage.ATTENTION)
            home.errorDetails("ERROR: Device command failed: cp exited with status 1"); home.logs(logLines)
        },
    )

    private fun shown(view: View): Boolean =
        view.visibility == View.VISIBLE && (view.parent as? View)?.let(::shown) ?: true

    private fun textViews(view: View): List<TextView> = when (view) {
        is TextView -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { textViews(view.getChildAt(it)) }
        else -> emptyList()
    }

    /** Each shown text whose lines are cut short, run past its view's height, or leave the page. */
    private fun clipped(page: View): List<String> {
        val bounds = Rect().also { page.getGlobalVisibleRect(it) }
        return textViews(page).filter { shown(it) && it.text.isNotEmpty() }.mapNotNull { view ->
            val layout = view.layout ?: return@mapNotNull "${view.text}: no layout"
            val place = IntArray(2).also(view::getLocationOnScreen)
            val inLog = generateSequence(view.parent) { it.parent }.any { (it as? View)?.tag?.toString()?.endsWith("log-scroll") == true }
            val text = view.text
            when {
                (0 until layout.lineCount).any { layout.getEllipsisCount(it) > 0 } -> "${view.text}: ellipsized"
                !inLog && (0 until layout.lineCount - 1).map(layout::getLineEnd)
                    .any { text[it - 1].isLetterOrDigit() && text[it].isLetterOrDigit() } -> "${view.text}: breaks inside a word"
                !inLog && layout.height + view.totalPaddingTop + view.totalPaddingBottom > view.height + 1 ->
                    "${view.text}: text ${layout.height}px in ${view.height - view.totalPaddingTop - view.totalPaddingBottom}px"
                place[0] < bounds.left || place[0] + view.width > bounds.right + 1 -> "${view.text}: leaves the page"
                else -> null
            }
        }
    }

    @Test fun everyBriefStateFitsAndIsSaved() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val original = PatchLanguage.current(context)
        val problems = mutableListOf<String>()
        try {
            for (code in listOf("en", "id")) {
                PatchLanguage.set(context, code)
                for ((name, apply) in states) {
                    ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                        scenario.onActivity { activity -> apply(GuidedHome(activity) { }, activity) }
                        instrumentation.waitForIdleSync()
                        scenario.onActivity { activity ->
                            val page = ((activity.window.decorView.findViewWithTag<View>("start-card").parent) as ViewGroup)
                            val scale = activity.resources.configuration.fontScale
                            clipped(page).forEach { problems += "$code $scale $name: $it" }
                            val bitmap = Bitmap.createBitmap(page.width, page.height, Bitmap.Config.ARGB_8888)
                            page.draw(Canvas(bitmap))
                            val folder = File(activity.cacheDir, "home-states").apply { mkdirs() }
                            File(folder, "$code-$scale-$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                            bitmap.recycle()
                        }
                    }
                }
            }
        } finally { PatchLanguage.set(context, original) }
        assertTrue(problems.joinToString("\n"), problems.isEmpty())
    }
}
