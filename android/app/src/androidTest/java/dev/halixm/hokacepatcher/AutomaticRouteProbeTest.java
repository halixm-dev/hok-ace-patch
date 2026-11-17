package dev.halixm.hokacepatcher;

import java.util.Arrays;
import java.util.Collections;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Recovery priority and correlated completion; no device operations or game writes. */
public final class AutomaticRouteProbeTest {
    private final AutomaticRoute route = AutomaticRoute.INSTANCE;
    @Test public void testEmergencyMustBeVerifiedBeforeAnyOtherWork() {
        AutomaticRoute.Decision choice = route.choose("emergency", Arrays.asList("a", "b"),
            Arrays.asList(new AutomaticRoute.Setup("setup", true)));
        assertEquals(AutomaticRoute.Step.VERIFY, choice.getStep()); assertEquals("emergency", choice.getId());
    }
    @Test public void testInterruptedPatchBeforeSetup() {
        AutomaticRoute.Decision choice = route.choose(null, Arrays.asList("patch"),
            Arrays.asList(new AutomaticRoute.Setup("setup", true)));
        assertEquals(AutomaticRoute.Step.RECOVER_PATCH, choice.getStep()); assertEquals("patch", choice.getId());
    }
    @Test public void testAmbiguousPatchDoesNotChooseNewest() {
        assertEquals(AutomaticRoute.Step.MANUAL, route.choose(null, Arrays.asList("a", "b"), Collections.emptyList()).getStep());
    }
    @Test public void testSetupDownloadsNeedHumanConfirmation() {
        assertEquals(AutomaticRoute.Step.WAIT_FOR_DOWNLOADS, route.choose(null, Collections.emptyList(),
            Arrays.asList(new AutomaticRoute.Setup("setup", true))).getStep());
        assertEquals(AutomaticRoute.Step.RECOVER_SETUP, route.choose(null, Collections.emptyList(),
            Arrays.asList(new AutomaticRoute.Setup("setup", false))).getStep());
    }
    @Test public void testAmbiguousSetupDoesNotUninstallAgain() {
        assertEquals(AutomaticRoute.Step.MANUAL, route.choose(null, Collections.emptyList(),
            Arrays.asList(new AutomaticRoute.Setup("a", false), new AutomaticRoute.Setup("b", true))).getStep());
    }
    @Test public void testCleanStateAutomaticallyPreparesFreshFiles() {
        assertEquals(AutomaticRoute.Step.PREPARE, route.choose(null, Collections.emptyList(), Collections.emptyList()).getStep());
    }
    @Test public void testOldResultOrLiveServiceCannotAdvance() throws Exception {
        JSONObject saved = new JSONObject().put("flow", "current").put("status", "prepared");
        assertFalse(route.finished(saved, "old", false));
        assertFalse(route.finished(saved, null, false));
        assertFalse(route.finished(saved, "current", true));
        assertTrue(route.finished(saved, "current", false));
        assertFalse(route.finished(saved.put("status", "running"), "current", false));
        assertFalse(route.finished(saved.put("status", "unknown"), "current", false));
        assertTrue(route.finished(saved.put("status", "error"), "current", false));
    }
    private static AutomaticRoute.Run run(String lifecycle, boolean mayContinue, String session) {
        return new AutomaticRoute.Run("run-" + session, lifecycle, mayContinue, session);
    }
    @Test public void testLinkedSessionContinuesItsClaimedStart() {
        AutomaticRoute.Decision choice = route.choose(null, Arrays.asList("s"), Collections.emptyList(),
            Arrays.asList(run("claimed", true, "s")));
        assertEquals(AutomaticRoute.Step.CONTINUE_RUN, choice.getStep()); assertEquals("run-s", choice.getId());
    }
    @Test public void testStoppedOrUnlinkedSessionGetsSafetyRecoveryOnly() {
        assertEquals(AutomaticRoute.Step.RECOVER_PATCH, route.choose(null, Arrays.asList("s"), Collections.emptyList(),
            Arrays.asList(run("claimed", false, "s"))).getStep());
        assertEquals(AutomaticRoute.Step.RECOVER_PATCH, route.choose(null, Arrays.asList("s"), Collections.emptyList(),
            Arrays.asList(run("claimed", true, "other"))).getStep());
        assertEquals(AutomaticRoute.Step.RECOVER_PATCH, route.choose(null, Arrays.asList("s"), Collections.emptyList(),
            Collections.emptyList()).getStep());
    }
    @Test public void testSetupStaysBeforeAnySavedStart() {
        assertEquals(AutomaticRoute.Step.RECOVER_SETUP, route.choose(null, Collections.emptyList(),
            Arrays.asList(new AutomaticRoute.Setup("setup", false)), Arrays.asList(run("prepared", true, "s"))).getStep());
    }
    @Test public void testSavedStartRoutesByLifecycle() {
        AutomaticRoute.Decision unconfirmed = route.choose(null, Collections.emptyList(), Collections.emptyList(),
            Arrays.asList(run("authorized", true, "s")));
        assertEquals(AutomaticRoute.Step.PREPARE, unconfirmed.getStep()); assertEquals("run-s", unconfirmed.getId());
        assertEquals(AutomaticRoute.Step.CONTINUE_RUN, route.choose(null, Collections.emptyList(), Collections.emptyList(),
            Arrays.asList(run("prepared", true, "s"))).getStep());
        assertEquals(AutomaticRoute.Step.CONTINUE_RUN, route.choose(null, Collections.emptyList(), Collections.emptyList(),
            Arrays.asList(run("claimed", true, "s"))).getStep());
        AutomaticRoute.Decision stopped = route.choose(null, Collections.emptyList(), Collections.emptyList(),
            Arrays.asList(run("claimed", false, "s")));
        assertEquals(AutomaticRoute.Step.RESOLVE_STOPPED, stopped.getStep()); assertEquals("run-s", stopped.getId());
    }
    @Test public void testAmbiguousSavedStartsDoNotGuess() {
        assertEquals(AutomaticRoute.Step.MANUAL, route.choose(null, Collections.emptyList(), Collections.emptyList(),
            Arrays.asList(run("prepared", true, "a"), run("claimed", true, "b"))).getStep());
        assertEquals(AutomaticRoute.Step.RECOVER_PATCH, route.choose(null, Arrays.asList("a"), Collections.emptyList(),
            Arrays.asList(run("claimed", true, "a"), run("claimed", true, "b"))).getStep());
    }
    @Test public void testWaitingAndStoppedResultsEndTheFlow() throws Exception {
        JSONObject saved = new JSONObject().put("flow", "current");
        assertTrue(route.finished(saved.put("status", "waiting"), "current", false));
        assertTrue(route.finished(saved.put("status", "stopped_consistent"), "current", false));
    }
    @Test public void testStopRoutesOnlySafetyRecoveryAndClosing() {
        for (AutomaticRoute.Step step : AutomaticRoute.Step.values()) {
            boolean safety = step == AutomaticRoute.Step.VERIFY || step == AutomaticRoute.Step.RECOVER_PATCH ||
                step == AutomaticRoute.Step.RECOVER_SETUP || step == AutomaticRoute.Step.RESOLVE_STOPPED;
            assertEquals(step.name(), safety, route.allowedWhileStopping(step));
        }
        // A stopped claimed Start whose session is mid-change gets safety recovery, which Stop allows.
        assertTrue(route.allowedWhileStopping(route.choose(null, Arrays.asList("s"), Collections.emptyList(),
            Arrays.asList(run("claimed", false, "s"))).getStep()));
        // Nothing left: the next step would be a fresh preparation, which a Stop never starts.
        assertFalse(route.allowedWhileStopping(route.choose(null, Collections.emptyList(), Collections.emptyList(),
            Collections.emptyList()).getStep()));
        assertFalse(route.allowedWhileStopping(route.choose(null, Collections.emptyList(),
            Arrays.asList(new AutomaticRoute.Setup("setup", true)), Collections.emptyList()).getStep()));
    }
    private static AutomaticRoute.Saved saved(String action, String lifecycle, boolean mayContinue, boolean stop,
                                              boolean exhausted, boolean setupReady) {
        return new AutomaticRoute.Saved("run", action, lifecycle, mayContinue, stop, exhausted, setupReady);
    }
    @Test public void testLaunchResumesOnlyDurableIntentWithinBudget() {
        java.util.List<AutomaticRoute.Setup> none = Collections.emptyList();
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(null, 0, none));
        assertEquals(AutomaticRoute.Launch.CONTINUE, route.onLaunch(saved("translate", "claimed", true, false, false, false), 1, none));
        assertEquals(AutomaticRoute.Launch.CONTINUE, route.onLaunch(saved("remove", "prepared", true, false, false, false), 1, none));
        // Not yet confirmed: reopening never prepares by itself.
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(saved("translate", "authorized", true, false, false, false), 1, none));
        // ...unless its setup already has the downloads answer.
        assertEquals(AutomaticRoute.Launch.CONTINUE, route.onLaunch(saved("translate", "authorized", true, false, false, true), 1, none));
        // A legacy Re-download Start never resumes (ticket 12). A translate's own Re-download is approved
        // automatically (2026-11-13); one the loop guard held back for review, or waiting for the game's
        // download, is held at launch by the screen itself (MainActivity reads Redownload first).
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(saved("redownload", "claimed", true, false, false, false), 1, none));
        // The spent retry budget survives reopen: one next action, no automatic dispatch.
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(saved("translate", "claimed", true, false, true, false), 1, none));
        // Stop stays stopped: its reopen only finishes safety recovery and closes the record.
        assertEquals(AutomaticRoute.Launch.STOP, route.onLaunch(saved("translate", "claimed", false, true, false, false), 1, none));
        assertEquals(AutomaticRoute.Launch.STOP, route.onLaunch(saved("translate", "claimed", false, true, true, false), 1,
            Arrays.asList(new AutomaticRoute.Setup("setup", true))));
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(saved("translate", "stopped", false, true, false, false), 1, none));
        // Ambiguity never guesses.
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(null, 2, none));
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(null, 0,
            Arrays.asList(new AutomaticRoute.Setup("a", false), new AutomaticRoute.Setup("b", false))));
    }
    @Test public void testLaunchRecoversApprovedSetupButAsksDownloadsOnlyForAContinuingStart() {
        java.util.List<AutomaticRoute.Setup> intent = Arrays.asList(new AutomaticRoute.Setup("setup", false));
        java.util.List<AutomaticRoute.Setup> downloads = Arrays.asList(new AutomaticRoute.Setup("setup", true));
        // An uninstall/install intent is recovered install-only, even without a Start or with its budget spent.
        assertEquals(AutomaticRoute.Launch.CONTINUE, route.onLaunch(null, 0, intent));
        assertEquals(AutomaticRoute.Launch.CONTINUE, route.onLaunch(saved("translate", "authorized", true, false, true, false), 1, intent));
        // The downloads question belongs to a Start that may continue.
        assertEquals(AutomaticRoute.Launch.NONE, route.onLaunch(null, 0, downloads));
        assertEquals(AutomaticRoute.Launch.CONTINUE, route.onLaunch(saved("translate", "authorized", true, false, false, false), 1, downloads));
        assertEquals(AutomaticRoute.Step.RECOVER_SETUP, route.choose(null, Collections.emptyList(), intent,
            Arrays.asList(run("authorized", true, "s"))).getStep());
    }
}
