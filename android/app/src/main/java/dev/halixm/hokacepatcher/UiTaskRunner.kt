package dev.halixm.hokacepatcher

/**
 * UI-thread gate: result callbacks queued by work still see busy until its final UI callback. A callback that
 * starts more gated work (a confirmed wait that resumes the saved action) goes in <then>, which runs on the UI
 * thread after that final callback, once busy is clear; queued from inside the task it would be refused.
 */
class UiTaskRunner(
    private val execute: (() -> Unit) -> Unit,
    private val postUi: (() -> Unit) -> Unit,
    private val started: () -> Unit,
    private val failed: (Exception) -> Unit,
    private val finished: () -> Unit,
) {
    var busy = false
        private set

    fun run(task: () -> Unit) = run(task) {}

    fun run(task: () -> Unit, then: () -> Unit) {
        if (busy) return
        busy = true
        started()
        execute {
            try { task() } catch (error: Exception) { failed(error) }
            finally { postUi { busy = false; finished(); then() } }
        }
    }
}
