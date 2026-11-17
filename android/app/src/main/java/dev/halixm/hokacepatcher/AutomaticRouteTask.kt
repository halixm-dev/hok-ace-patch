package dev.halixm.hokacepatcher

/** Scheduling seam shared by the Activity and isolated tests; never starts a game worker itself. */
object AutomaticRouteTask {
    fun run(task: (() -> Unit) -> Unit, postUi: (() -> Unit) -> Unit,
            choose: () -> AutomaticRoute.Decision, resolve: (String) -> Unit,
            deliver: (AutomaticRoute.Decision, Result<Unit>?) -> Unit) {
        task {
            val decision = choose()
            // The parent still owns the busy gate when its UI callback runs. Resolve here,
            // in the original background task, instead of submitting a nested task that it drops.
            val result = if (decision.step == AutomaticRoute.Step.RESOLVE_STOPPED)
                runCatching { resolve(decision.id!!) } else null
            postUi { deliver(decision, result) }
        }
    }
}
