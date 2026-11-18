package dev.halixm.hokacepatcher

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A confirmed wait resumes the saved action from <then>, after the gate clears. Queued from inside the task, as
 * Downloads finished did on the 2026-11-12 device cycle, the resume still saw busy and was dropped.
 */
class UiTaskRunnerTest {
    private val ui = ArrayDeque<() -> Unit>()
    private val events = mutableListOf<String>()
    private lateinit var runner: UiTaskRunner

    private fun runner() = UiTaskRunner(execute = { it() }, postUi = { ui.addLast(it) },
        started = { events += "started" }, failed = { events += "failed" }, finished = { events += "finished" })
        .also { runner = it }

    private fun drain() { while (ui.isNotEmpty()) ui.removeFirst()() }

    @Test fun workQueuedFromInsideTheTaskStillSeesBusy() {
        runner()
        var resumed = false
        runner.run { ui.addLast { runner.run { resumed = true } } }
        drain()
        assertFalse("The old pattern drops the resume", resumed)
    }

    @Test fun thenRunsOnceTheGateIsClearAndMayStartGatedWork() {
        val busyAtFinish = mutableListOf<Boolean>()
        runner = UiTaskRunner(execute = { it() }, postUi = { ui.addLast(it) }, started = { events += "started" },
            failed = { events += "failed" }, finished = { events += "finished"; busyAtFinish += runner.busy })
        var resumed = false
        runner.run({ events += "task" }) {
            assertFalse(runner.busy)
            events += "then"
            runner.run { resumed = true }
        }
        assertTrue(runner.busy)
        drain()
        assertTrue(resumed)
        assertFalse(runner.busy)
        assertEquals(listOf("started", "task", "then", "started", "finished", "finished"), events)
        // The first task's refresh already sees the resumed work running, so no idle screen shows between them.
        assertEquals(listOf(true, false), busyAtFinish)
    }

    @Test fun thenRunsAfterAFailedTaskAndASecondRunIsRefusedWhileBusy() {
        runner()
        var thens = 0
        runner.run({ error("boom") }) { thens++ }
        runner.run({ events += "refused" }) { thens++ }
        drain()
        assertEquals(1, thens)
        assertEquals(listOf("started", "failed", "finished"), events)
    }
}
