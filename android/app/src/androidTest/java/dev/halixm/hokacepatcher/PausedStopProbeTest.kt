package dev.halixm.hokacepatcher

import android.app.Activity
import android.content.Context
import android.hardware.display.DisplayManager
import android.view.Display
import android.view.ContextThemeWrapper
import android.view.View
import android.widget.Button
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test

/** Builds only GuidedHome in an unattached Activity; never launches MainActivity or any service. */
class PausedStopProbeTest {
    private class Page(context: Context) : Activity() {
        lateinit var content: View
        init {
            val display = context.getSystemService(DisplayManager::class.java).getDisplay(Display.DEFAULT_DISPLAY)
            attachBaseContext(ContextThemeWrapper(context.createDisplayContext(display), android.R.style.Theme_Material_Light_NoActionBar))
        }
        // An unattached Activity has no mWindowManager. Forward its UI service to the display context.
        override fun getSystemService(name: String): Any? =
            if (name == Context.WINDOW_SERVICE) baseContext.getSystemService(name) else super.getSystemService(name)
        override fun setContentView(view: View) { content = view }
    }
    @Test fun idlePendingActionKeepsRetryAndStopAndFreeSpaceClickable() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync {
            val page = Page(instrumentation.targetContext)
            val actions = mutableListOf<String>()
            val home = GuidedHome(page) { actions += it }
            home.show("Work stopped", "Storage needed", "Try again", "start", false, GuidedHome.Stage.ATTENTION)
            home.progress(false, canStop = true)
            home.working(false); home.stopping(false)
            val stop = page.content.findViewWithTag<Button>("stop-automatic")
            val retry = page.content.findViewWithTag<Button>("next-step")
            val free = page.content.findViewWithTag<Button>("free-space")
            assertEquals(View.VISIBLE, stop.visibility); assertTrue(stop.isEnabled)
            assertEquals(View.VISIBLE, retry.visibility); assertTrue(retry.isEnabled)
            assertTrue(free.isEnabled)
            stop.performClick(); assertEquals(listOf("stop"), actions)
            home.progress(false, canStop = false)
            assertEquals(View.GONE, stop.visibility)
        }
    }
}
