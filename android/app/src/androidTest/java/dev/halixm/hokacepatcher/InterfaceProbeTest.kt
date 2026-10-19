package dev.halixm.hokacepatcher

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.RadioButton
import android.widget.ScrollView
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** UI-only checks: never start a worker, change Shizuku installation, or access game data. */
class InterfaceProbeTest {
    private fun shownTexts(view: View): List<String> = when (view) {
        is TextView -> listOf(view.text.toString())
        is ViewGroup -> (0 until view.childCount).flatMap { shownTexts(view.getChildAt(it)) }
        else -> emptyList()
    }

    @Test fun shizukuLaunchAndStoreFallbacks() {
        val installed = Intent("test.installed")
        val attempts = mutableListOf<Intent>()
        assertTrue(ShizukuLauncher.open(installed) { attempts += it })
        assertSame(installed, attempts.single())
        attempts.clear()
        assertTrue(ShizukuLauncher.open(null) { attempts += it })
        assertEquals("com.android.vending", attempts.single().`package`)
        assertEquals("market://details?id=${ShizukuLauncher.PACKAGE}", attempts.single().dataString)
        attempts.clear()
        assertTrue(ShizukuLauncher.open(null) {
            attempts += it
            if (attempts.size == 1) throw ActivityNotFoundException()
        })
        assertEquals(ShizukuLauncher.STORE_URL, attempts.last().dataString)
        assertFalse(ShizukuLauncher.open(null) { throw ActivityNotFoundException() })
        assertFalse(ShizukuLauncher.open(installed) { throw SecurityException() })
    }

    @Test fun pickerChangesInterfaceAndPersistsAcrossRecreation() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val original = PatchLanguage.current(context)
        try {
            PatchLanguage.set(context, "en")
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                scenario.onActivity { activity ->
                    activity.window.decorView.findViewWithTag<RadioButton>("language-id").performClick()
                }
                instrumentation.waitForIdleSync()
                scenario.onActivity { activity ->
                    assertEquals("id", PatchLanguage.current(activity))
                    assertEquals("Alat teknis", activity.window.decorView.findViewWithTag<TextView>("show-technical").text.toString())
                    assertTrue(UiText.firstSetup(activity).contains("akan dihapus"))
                    assertTrue(UiText.patchConfirmation(activity).contains("Bahasa: Bahasa Indonesia"))
                    assertTrue(UiText.storage(activity, StorageBudget.explainFailure("2000000000 bytes required, 1000000000 available")!!).contains("1.0 GB lagi"))
                    // The hero names a community patcher, not the game's publisher, and has no tagline.
                    assertEquals("PATCHER KOMUNITAS  /  HOK ACE", activity.window.decorView.findViewWithTag<TextView>("hero-eyebrow").text.toString())
                    assertFalse(shownTexts(activity.window.decorView).any { it.startsWith("Langkah berikutnya") || it.startsWith("Your next move") })
                    assertEquals("Terjemahan ditulis", UiText.text(activity, "Translation written"))
                    assertTrue(UiText.text(activity, WorkerStatus.UNCONFIRMED).startsWith("Pemulihan selesai."))
                    val view = activity.window.decorView
                    val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                    view.draw(Canvas(bitmap))
                    File(activity.cacheDir, "interface-id.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                    bitmap.recycle()
                }
                scenario.recreate()
                scenario.onActivity { activity ->
                    assertEquals("Alat teknis", activity.window.decorView.findViewWithTag<TextView>("show-technical").text.toString())
                    activity.window.decorView.findViewWithTag<RadioButton>("language-en").performClick()
                }
                instrumentation.waitForIdleSync()
                scenario.onActivity { activity ->
                    assertEquals("en", PatchLanguage.current(activity))
                    assertEquals("Technical tools", activity.window.decorView.findViewWithTag<TextView>("show-technical").text.toString())
                    assertEquals("COMMUNITY PATCHER  /  HOK ACE", activity.window.decorView.findViewWithTag<TextView>("hero-eyebrow").text.toString())
                    val view = activity.window.decorView
                    val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                    view.draw(Canvas(bitmap))
                    File(activity.cacheDir, "interface-en.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                    bitmap.recycle()
                }
            }
        } finally { PatchLanguage.set(context, original) }
    }

    /** ① Language: title, note, choices, then Remove translation, offered only while a delta is kept. */
    @Test fun languageCardOffersRemovalOnlyWithAPristineDelta() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val original = PatchLanguage.current(context)
        // Move a delta this phone already keeps aside, and put it back afterwards.
        val delta = File(PristineDelta.directory(context), "delta.bin")
        val kept = File(PristineDelta.directory(context), "delta.bin.probe")
        if (delta.isFile) assertTrue(delta.renameTo(kept))
        try {
            val clear = "Switching languages on a phone another patcher or an older version translated? Clear the game's data and download it again first."
            val noClear = "Switching languages? No need to clear: the patcher kept the original game files it changed."
            for ((code, held) in listOf("en" to false, "en" to true, "id" to false, "id" to true)) {
                PatchLanguage.set(context, code)
                val note = UiText.text(context, if (held) noClear else clear)
                if (held) { delta.parentFile!!.mkdirs(); delta.writeBytes(byteArrayOf()) } else delta.delete()
                ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                    scenario.onActivity { activity ->
                        val view = activity.window.decorView
                        val card = view.findViewWithTag<ViewGroup>("language-card")
                        val order = listOf("language-note", "language-picker", "remove-translation")
                            .map { tag -> (0 until card.childCount).indexOfFirst { card.getChildAt(it).tag == tag } }
                        val title = (0 until card.childCount).indexOfFirst {
                            (card.getChildAt(it) as? TextView)?.text?.toString() == UiText.text(activity, "Language") }
                        assertTrue("$code: title $title, then $order", title >= 0 && order.all { it > title } && order == order.sorted())
                        assertEquals(note, view.findViewWithTag<TextView>("language-note").text.toString())
                        val remove = view.findViewWithTag<View>("remove-translation")
                        assertEquals("$code, delta $held", if (held) View.VISIBLE else View.GONE, remove.visibility)
                        if (held) assertEquals(UiText.text(activity, "Remove translation"), (remove as TextView).text.toString())
                    }
                }
            }
            // Locked while work runs, in the disabled colours rather than a lower alpha.
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                scenario.onActivity { activity ->
                    val home = GuidedHome(activity) { }
                    home.languageEnabled(false)
                    val view = activity.window.decorView
                    val choice = view.findViewWithTag<RadioButton>("language-en")
                    assertFalse(choice.isEnabled)
                    assertEquals(1f, choice.alpha)
                    assertEquals(activity.getColor(R.color.disabled_text), choice.currentTextColor)
                    assertFalse(view.findViewWithTag<View>("remove-translation").isEnabled)
                    assertEquals(activity.getColor(R.color.disabled_text), view.findViewWithTag<TextView>("remove-translation").currentTextColor)
                    home.languageEnabled(true)
                    assertTrue(choice.isEnabled)
                    assertEquals(activity.getColor(R.color.ink), choice.currentTextColor)
                }
            }
        } finally {
            delta.delete()
            if (kept.isFile) kept.renameTo(delta)
            PatchLanguage.set(context, original)
        }
    }

    /** ② rewrites itself for each result state, in both languages; error and warning cards sit under it, above the log. */
    @Test fun startCardShowsResultStatesAndCardsSitAboveTheLog() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val original = PatchLanguage.current(context)
        val counts = org.json.JSONObject().put("text_tables", 12345).put("applied_textures", 3)
            .put("skipped_tables", 0).put("skipped_textures", 1)
        val states = listOf(
            org.json.JSONObject().put("status", "complete").put("counts", counts),
            org.json.JSONObject().put("status", "complete").put("removed", 7),
            org.json.JSONObject().put("status", "recovered_unconfirmed"),
            org.json.JSONObject().put("status", "space_freed").put("freed_bytes", 2_000_000_000L).put("free_bytes", 5_000_000_000L))
        val headings = mapOf(
            "en" to listOf("Translation added", "Translation removed", "Translation written", "Space freed"),
            "id" to listOf("Terjemahan diterapkan", "Terjemahan dihapus", "Terjemahan ditulis", "Ruang dikosongkan"))
        try {
            for ((code, expected) in headings) {
                PatchLanguage.set(context, code)
                ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                    scenario.onActivity { activity ->
                        val home = GuidedHome(activity) { }
                        val view = activity.window.decorView
                        val card = view.findViewWithTag<ViewGroup>("start-card")
                        for ((state, heading) in states.zip(expected)) {
                            home.result(UiText.result(code, state)!!, "Start")
                            val texts = shownTexts(card)
                            assertTrue("$code: $heading in $texts", heading in texts)
                        }
                        // Translation added: four count rows, the value at the end of each, then the login note.
                        home.result(UiText.result(code, states[0])!!, "Start another patch")
                        val items = view.findViewWithTag<ViewGroup>("result-items")
                        assertEquals(View.VISIBLE, items.visibility)
                        assertEquals(4, items.childCount)
                        assertEquals("12345", shownTexts(items.getChildAt(0)).last())
                        assertEquals(View.VISIBLE, view.findViewWithTag<View>("result-note").visibility)
                        // A notice is one muted line inside ②.
                        home.message("Access was not allowed. Tap Start to try again.")
                        val notice = view.findViewWithTag<TextView>("friendly-notice")
                        assertSame(card, notice.parent)
                        assertEquals(View.VISIBLE, notice.visibility)
                        assertEquals(activity.getColor(R.color.text_muted), notice.currentTextColor)
                        // Any other state clears the counts.
                        home.show("Ready when you are", "Tap Start.", "Start", "start", true)
                        assertEquals(View.GONE, items.visibility)
                        home.errorDetails("Device command failed: probe")
                        home.logs(listOf("Log line"))
                        val root = card.parent as ViewGroup
                        val order = listOf("start-card", "error-card", "recovery-card", "live-log-scroll").map { tag ->
                            (0 until root.childCount).indexOfFirst { root.getChildAt(it).findViewWithTag<View>(tag) != null }
                        }
                        assertEquals("$code: $order", order.sorted(), order)
                        assertTrue(order.all { it >= 0 })
                        for (tag in listOf("copy-error", "error-export-log")) {
                            assertNotNull(tag, view.findViewWithTag<ViewGroup>("error-card").findViewWithTag<View>(tag))
                        }
                    }
                }
            }
        } finally { PatchLanguage.set(context, original) }
    }

    /** Running: a determinate bar in place of the button and "Step N of M · <step>"; an older record without a step keeps its line. */
    @Test fun progressShowsTheStepFromTheSavedState() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val original = PatchLanguage.current(context)
        val saved = org.json.JSONObject().put("status", "running").put("action", "patch")
            .put("progress", "Opening game data access").put("step", "unlock_access").put("steps", 6)
        try {
            for ((code, line) in listOf("en" to "Step 3 of 6 · Unlock access", "id" to "Langkah 3 dari 6 · Buka akses")) {
                PatchLanguage.set(context, code)
                ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                    scenario.onActivity { activity ->
                        val home = GuidedHome(activity) { }
                        val view = activity.window.decorView
                        val step = UiText.step(code, saved)!!
                        home.show("Working on your game", step.line, "Please wait", "start", false)
                        home.progress(true, step)
                        assertTrue("$code: $line", line in shownTexts(view.findViewWithTag<ViewGroup>("start-card")))
                        val bar = view.findViewWithTag<android.widget.ProgressBar>("progress-bar")
                        assertEquals(View.VISIBLE, bar.visibility)
                        assertFalse(bar.isIndeterminate)
                        assertEquals(3, bar.progress); assertEquals(6, bar.max)
                        assertEquals(View.GONE, view.findViewWithTag<View>("next-step").visibility)
                        assertEquals(View.VISIBLE, view.findViewWithTag<View>("stop-automatic").visibility)
                        // Without a step the bar only moves; done, the button comes back.
                        assertNull(UiText.step(code, org.json.JSONObject(saved.toString()).apply { remove("step") }))
                        home.progress(true, null)
                        assertTrue(bar.isIndeterminate)
                        home.progress(false)
                        assertEquals(View.GONE, bar.visibility)
                        assertEquals(View.VISIBLE, view.findViewWithTag<View>("next-step").visibility)
                    }
                }
            }
        } finally { PatchLanguage.set(context, original) }
    }

    @Test fun longLogsScrollWithoutMovingHome() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            lateinit var home: GuidedHome
            scenario.onActivity { activity ->
                // Render the same view with inert callbacks and synthetic logs.
                home = GuidedHome(activity) { }
                home.logs((1..100).map { "Log line $it" })
                home.addDiagnosticLog(TextView(activity).apply { text = (1..100).joinToString("\n") { "Diagnostic $it" } })
                activity.window.decorView.findViewWithTag<View>("show-technical").performClick()
            }
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            scenario.onActivity { activity ->
                for (tag in listOf("live-log-scroll", "diagnostic-log-scroll")) {
                    val scroll = activity.window.decorView.findViewWithTag<ScrollView>(tag)
                    assertTrue(scroll.getChildAt(0).height > scroll.height)
                    scroll.scrollTo(0, 0)
                    val outer = generateSequence(scroll.parent) { it.parent }.filterIsInstance<ScrollView>().first()
                    val before = outer.scrollY
                    val time = android.os.SystemClock.uptimeMillis()
                    for ((index, y) in listOf(140f, 100f, 40f, 10f).withIndex()) {
                        val event = MotionEvent.obtain(time, time + index * 30L,
                            if (index == 0) MotionEvent.ACTION_DOWN else MotionEvent.ACTION_MOVE,
                            30f, y * activity.resources.displayMetrics.density, 0)
                        scroll.dispatchTouchEvent(event); event.recycle()
                    }
                    assertTrue("$tag must consume the vertical drag", scroll.scrollY > 0)
                    assertEquals(before, outer.scrollY)
                    val cancel = MotionEvent.obtain(time, time + 150, MotionEvent.ACTION_CANCEL, 0f, 0f, 0)
                    scroll.dispatchTouchEvent(cancel); cancel.recycle()
                }
            }
        }
    }
}
