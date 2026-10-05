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
}
