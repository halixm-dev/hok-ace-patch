package dev.halixm.hokacepatcher

import android.content.Context

/**
 * The home screen's one line for a failed step, from the worker's or engine's error message alone: what happened
 * and the one thing to do next. [recoverable] says whether recovery options sit below, so the line points there
 * instead of at Try again. Moved verbatim from `MainActivity` (tech-debt ticket 02); the strings it returns are
 * checked by `tools/research/check_ui_strings.py`.
 */
object FailureText {
    /** The provider-not-ready line, shared with the home screen's own checks. */
    fun notReady(context: Context, provider: ShellProvider): String =
        UiText.string(context, "provider_not_ready", "provider" to UiText.text(context, provider.label))

    fun explain(context: Context, shell: ShellProvider, message: String, recoverable: Boolean): String = with(context) {
        // The names the body used as MainActivity members, so it moved unchanged.
        fun provider() = shell
        fun usesShizuku() = shell == ShellProvider.SHIZUKU
        fun ui(value: String) = UiText.text(context, value)
        fun notReady(provider: ShellProvider) = FailureText.notReady(context, provider)

        StorageBudget.explainFailure(message, filesDir.usableSpace)?.let { return UiText.storage(this, it) }
        if (message.contains("GB free for this step")) return UiText.storage(this, message.removePrefix("ERROR: "))
        return when {
            // The engine's way out it cannot avoid; its path names Android's Storage page, not a lack of space.
            message.contains(StopCard.CLEAR_DATA) ->
                "The patcher cannot restore the untranslated game files. Clear the game's data in Android Settings, open the game and let it download again to the login screen, close it, then tap Start. Open Technical tools for the reason."
            message.contains("space", true) || message.contains("storage", true) ->
                ui("Free now:") + " ${StorageBudget.freeSpaceLabel(filesDir.usableSpace)}.\n" +
                    ui("The phone did not report how much more space is needed. Free space elsewhere and retry. Keep saved recovery files.")
            message.contains(ShellProvider.SHIZUKU_AS_ROOT) -> ShellProvider.SHIZUKU_AS_ROOT
            WirelessDebugging.REFUSALS.any { message.contains(it) } -> WirelessDebugging.REFUSALS.first { message.contains(it) }
            RootWorkerStarter.REFUSALS.any { message.contains(it) } -> RootWorkerStarter.REFUSALS.first { message.contains(it) }
            message.contains(PatchCoordinator.ROOT_ACCESS_INSTALLED) -> PatchCoordinator.ROOT_ACCESS_INSTALLED
            message.contains(PatchCoordinator.OTHER_PROVIDER) -> PatchCoordinator.OTHER_PROVIDER
            // A run's lost root: the root manager revoked HOK ACE, or its su ended.
            provider() == ShellProvider.ROOT && message.contains("disconnected", true) -> if (recoverable)
                "Root access stopped. Keep the game closed. Check HOK ACE in your root manager, then check recovery options below."
                else "Root access stopped. Keep the game closed. Check HOK ACE in your root manager, then tap Try again."

            // A run's lost connection: Wi-Fi or wireless debugging went off under it.
            provider() == ShellProvider.WIRELESS && message.contains("disconnected", true) -> if (recoverable)
                "Wireless debugging disconnected. Keep the game closed. Turn Wi-Fi and Wireless debugging back on, then check recovery options below."
                else "Wireless debugging disconnected. Keep the game closed. Turn Wi-Fi and Wireless debugging back on, then tap Try again."
            message.contains("Worker connection timed out") -> if (usesShizuku())
                "Shizuku is running, but the patcher's helper did not start. Open Shizuku, stop it and start it again, then return here and tap Try again. If it happens again, save a log for help. Keep the game closed."
                else "The patcher's helper did not start. Tap Try again. If it happens again, save a log for help. Keep the game closed."
            message.contains(PrivilegedDeviceService.GAME_MISSING) -> when (FirstSetupPackagePolicy.missingReason(message)) {
                FirstSetupPackagePolicy.Missing.HIDDEN ->
                    "The game is installed but hidden or switched off in this phone's main space, for example by Hide apps. Show it again, open it once, close it, then tap Try again."
                FirstSetupPackagePolicy.Missing.OTHER_PROFILE_ONLY ->
                    "The game is installed only in Dual App. Install it in the phone's main space too, open it once and finish all downloads, close it, then tap Try again."
                FirstSetupPackagePolicy.Missing.ABSENT ->
                    "The game is not installed in this phone's main space. Install it there (Dual App alone is not enough), open it once and finish all downloads, close it, then tap Try again."
            }
            message.contains(FirstSetupPackagePolicy.OTHER_PROFILE) ->
                "The game is also installed in another Android profile, such as Dual App or a work profile. Remove it from that profile, then tap Try again. Keep the game closed."
            message.contains(FirstSetupPackagePolicy.UNCHECKED_PROFILE) ->
                "This phone has another Android profile, such as Dual App, that could not be checked for the game. Remove the game from Dual App, then tap Try again. If it happens again, save a log for help. Keep the game closed."
            message.contains(InstalledGameVerifier.DIFFERENT_APP) ->
                "The installed game app is not the saved app this check looks for. It is a different app, not a damaged one. If no patch was started, tap Try again. Otherwise check recovery options below, or save a log for help. Keep the game closed."
            message.contains("USER_RESTRICTED", true) ->
                "The phone blocked installation. Unlock it and accept the install prompt. Open Technical tools for the full error."
            // The command ran, so the shell provider is working; the phone itself refused the step.
            message.contains("Device command failed") -> UiText.string(this,
                if (recoverable) "phone_refused_step_check_recovery" else "phone_refused_step_try_again", "provider" to ui(provider().label))
            message.contains("Shizuku", true) || message.contains("permission", true) ||
                message.contains("disconnected", true) || message.contains("is not available in this build") -> when {
                    !provider().available -> notReady(provider())
                    usesShizuku() -> "Open Shizuku. Start it and allow HOK ACE. Return here and retry. Keep the game closed."
                    else -> UiText.string(this, "work_could_not_start_check_provider", "provider" to ui(provider().label))
                }
            else -> if (recoverable) "Work stopped. Keep the game closed. Check recovery options below, or save a log for help."
                else "Work stopped. Keep the game closed. Tap Try again, or save a log for help."
        }
    }
}
