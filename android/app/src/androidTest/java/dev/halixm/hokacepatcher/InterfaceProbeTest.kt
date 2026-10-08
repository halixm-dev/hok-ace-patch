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
