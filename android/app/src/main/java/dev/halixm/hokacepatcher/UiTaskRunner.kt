package dev.halixm.hokacepatcher

/**
 * UI-thread gate: result callbacks queued by work still see busy until its final UI callback. A callback that
 * starts more gated work (a confirmed wait that resumes the saved action) goes in <then>, which runs on the UI
 * thread once busy is clear; queued from inside the task it would be refused. <then> runs before <finished>, so the
 * screen refresh sees the work it resumed: refreshed first, a resumed action showed the idle saved-work screen
 * ("Finish your game safely") for 2 to 4 s after Delete and re-download and Downloads finished (phone run 2026-11-18).
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
            finally { postUi { busy = false; then(); finished() } }
        }
    }
}
