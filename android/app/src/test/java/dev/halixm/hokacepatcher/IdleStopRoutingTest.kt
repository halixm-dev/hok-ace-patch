package dev.halixm.hokacepatcher

import java.util.ArrayDeque
import org.junit.Assert.*
import org.junit.Test

/** Replays Activity task/UI ordering without launching the Activity or touching the game. */
class IdleStopRoutingTest {
    @Test fun stoppedIdleActionClosesBeforeBusyTaskDeliversUi() {
        val background = ArrayDeque<() -> Unit>()
        val ui = ArrayDeque<() -> Unit>()
        val tasks = UiTaskRunner({ background.add(it) }, { ui.add(it) }, {}, { throw it }, {})
        var resolved = false
        var delivered = false
        AutomaticRouteTask.run(tasks::run, { ui.add(it) }, {
            AutomaticRoute.choose(null, emptyList(), emptyList(),
                listOf(AutomaticRoute.Run("saved-stop", "claimed", false, "session")))
        }, { id ->
            assertEquals("saved-stop", id)
            assertTrue("Resolution belongs to original background task", tasks.busy)
            resolved = true
        }, { decision, result ->
            assertEquals(AutomaticRoute.Step.RESOLVE_STOPPED, decision.step)
            assertTrue(result!!.isSuccess)
            delivered = true
        })
        assertTrue(tasks.busy)
        background.removeFirst().invoke()
        while (ui.isNotEmpty()) ui.removeFirst().invoke()
        assertTrue("Idle Stop must close instead of repeatedly staying Stopping safely", resolved)
        assertTrue("Stop completion must reach the UI", delivered)
        assertFalse(tasks.busy)
        assertTrue("No second task or game worker starts", background.isEmpty())
    }
    @Test fun failedResolutionIsDeliveredWithoutRetryOrNewWork() {
        val background = ArrayDeque<() -> Unit>()
        val ui = ArrayDeque<() -> Unit>()
        val tasks = UiTaskRunner({ background.add(it) }, { ui.add(it) }, {}, { throw it }, {})
        var attempts = 0
        var failure: Throwable? = null
        val blocked = IllegalStateException("Recovery is still unresolved")
        AutomaticRouteTask.run(tasks::run, { ui.add(it) }, {
            AutomaticRoute.Decision(AutomaticRoute.Step.RESOLVE_STOPPED, "saved-stop")
        }, { attempts++; throw blocked }, { _, result -> failure = result!!.exceptionOrNull() })
        background.removeFirst().invoke()
        while (ui.isNotEmpty()) ui.removeFirst().invoke()
        assertSame(blocked, failure)
        assertEquals(1, attempts)
        assertFalse(tasks.busy)
        assertTrue(background.isEmpty())
    }

    @Test fun unknownPendingRecoveryPreventsStoppedResolution() {
        val background = ArrayDeque<() -> Unit>()
        val ui = ArrayDeque<() -> Unit>()
        val tasks = UiTaskRunner({ background.add(it) }, { ui.add(it) }, {}, { throw it }, {})
        var delivered: AutomaticRoute.Step? = null
        AutomaticRouteTask.run(tasks::run, { ui.add(it) }, {
            AutomaticRoute.choose(null, listOf("unknown-session"), emptyList(),
                listOf(AutomaticRoute.Run("saved-stop", "claimed", false, "session")))
        }, { fail("Pending safety recovery must prevent resolution") }, { decision, result ->
            delivered = decision.step
            assertNull(result)
        })
        background.removeFirst().invoke()
        while (ui.isNotEmpty()) ui.removeFirst().invoke()
        assertEquals(AutomaticRoute.Step.RECOVER_PATCH, delivered)
        assertTrue(background.isEmpty())
    }

    @Test fun taskFailureStillDropsNestedTaskAndReleasesBusyAfterUiDelivery() {
        val background = ArrayDeque<() -> Unit>()
        val ui = ArrayDeque<() -> Unit>()
        val events = mutableListOf<String>()
        val error = IllegalStateException("test task failure")
        val tasks = UiTaskRunner({ background.add(it) }, { ui.add(it) },
            { events.add("start") }, { assertSame(error, it); events.add("failure") },
            { events.add("finish") })
        tasks.run {
            ui.add { events.add("delivery"); assertTrue(tasks.busy); tasks.run { fail("Nested task ran") } }
            throw error
        }
        tasks.run { fail("Concurrent task ran") }
        assertEquals(1, background.size)
        background.removeFirst().invoke()
        assertTrue(tasks.busy)
        ui.removeFirst().invoke()
        assertTrue("Busy clears only in the final callback", tasks.busy)
        ui.removeFirst().invoke()
        assertFalse(tasks.busy)
        assertEquals(listOf("start", "failure", "delivery", "finish"), events)
        assertTrue(background.isEmpty())
        tasks.run { events.add("next") }
        background.removeFirst().invoke()
        ui.removeFirst().invoke()
        assertFalse(tasks.busy)
        assertEquals(listOf("start", "failure", "delivery", "finish", "start", "next", "finish"), events)
    }

}
