package dev.halixm.hokacepatcher;

import java.util.Map;
import org.junit.Test;
import static org.junit.Assert.*;

/** Profile fallback parsing only; no commands, installation or game removal. */
public final class FirstSetupProfileTest {
    private static final String GAME = PrivilegedDeviceService.GAME;
    private static final FirstSetupPackagePolicy POLICY = FirstSetupPackagePolicy.INSTANCE;

    // Shape of Android 14's `dumpsys package` lines after the service's grep filter.
    private static String dump(String clone) {
        return "  Package [" + GAME + "] (7b2c1e4):\n" +
            "    User 0: ceDataInode=123 installed=true hidden=false suspended=false distractionFlags=0 stopped=false notLaunched=false enabled=0 instant=false virtual=false quarantined=false\n" +
            "    User 999: ceDataInode=0 installed=" + clone + " hidden=false suspended=false distractionFlags=0 stopped=true notLaunched=true enabled=0 instant=false virtual=false quarantined=false\n";
    }

    @Test public void deniedProfileIsRecognizedOnlyForItsOwnUser() {
        String error = "Device command failed (255): \nException occurred while executing 'list':\n" +
            "java.lang.SecurityException: Shell does not have permission to access user 999\n";
        assertTrue(POLICY.profileDenied(error, 999));
        assertFalse(POLICY.profileDenied(error, 99));
        assertFalse(POLICY.profileDenied("Device command failed (1): Error: unknown user 999", 999));
    }

    @Test public void dumpReportsEachProfileState() {
        Map<Integer, Boolean> absent = POLICY.profileStates(dump("false"), GAME);
        assertEquals(Boolean.TRUE, absent.get(0));
        assertEquals(Boolean.FALSE, absent.get(999));
        assertEquals(Boolean.TRUE, POLICY.profileStates(dump("true"), GAME).get(999));
        assertNull(POLICY.profileStates(dump("false"), GAME).get(10));
    }

    @Test public void noRecordIsDistinctFromAnEmptyRecord() {
        assertNull(POLICY.profileStates("", GAME));
        assertNull(POLICY.profileStates("\n\n", GAME));
        assertTrue(POLICY.profileStates("  Package [" + GAME + "] (abc):\n", GAME).isEmpty());
    }

    @Test public void unexpectedDumpsAreRefusedRatherThanReadAsAbsence() {
        String[] invalid = {
            "  Package [com.other.app] (abc):\n    User 999: ceDataInode=0 installed=false\n",
            "    User 999: ceDataInode=0 installed=false\n",
            "  Package [" + GAME + "] (abc):\n    User 999: installed=maybe\n",
            "  Package [" + GAME + "] (abc):\nError: dump failed\n",
            "  Package [" + GAME + "] (abc):\n    User 999: installed=false\n    User 999: installed=true\n",
        };
        for (String value : invalid) {
            try { POLICY.profileStates(value, GAME); fail("Accepted: " + value); }
            catch (IllegalStateException expected) { }
        }
        try { POLICY.profileStates(dump("false"), "com.anything.else"); fail("Arbitrary package target accepted"); }
        catch (IllegalArgumentException expected) { }
    }

    private static String user(int id, String installed, String hidden, int enabled) {
        return "    User " + id + ": ceDataInode=1 installed=" + installed + " hidden=" + hidden +
            " suspended=false distractionFlags=0 stopped=false notLaunched=false enabled=" + enabled +
            " instant=false virtual=false quarantined=false\n";
    }

    private static FirstSetupPackagePolicy.Missing reason(String dump) {
        // As the UI sees it: the summary travels inside the worker's error message.
        return POLICY.missingReason(PrivilegedDeviceService.GAME_MISSING + " (" + GAME + "; " + POLICY.userStates(dump) + ")");
    }

    @Test public void userStatesKeepOnlyTheFieldsThatDecideVisibility() {
        assertEquals("user 0: installed=true hidden=true suspended=false enabled=0; " +
            "user 999: installed=false hidden=false suspended=false enabled=0",
            POLICY.userStates("  Package [" + GAME + "] (abc):\n" + user(0, "true", "true", 0) + user(999, "false", "false", 0)));
        assertEquals("no package record", POLICY.userStates(""));
    }

    @Test public void missingGameIsClassifiedByTheMainUsersState() {
        String header = "  Package [" + GAME + "] (abc):\n";
        assertEquals(FirstSetupPackagePolicy.Missing.HIDDEN, reason(header + user(0, "true", "true", 0) + user(999, "false", "false", 0)));
        assertEquals(FirstSetupPackagePolicy.Missing.HIDDEN, reason(header + user(0, "true", "false", 4)));
        assertEquals(FirstSetupPackagePolicy.Missing.OTHER_PROFILE_ONLY, reason(header + user(0, "false", "false", 0) + user(999, "true", "false", 0)));
        assertEquals(FirstSetupPackagePolicy.Missing.ABSENT, reason(header + user(0, "false", "false", 0) + user(999, "false", "false", 0)));
        assertEquals(FirstSetupPackagePolicy.Missing.ABSENT, reason(""));
        assertEquals(FirstSetupPackagePolicy.Missing.ABSENT, POLICY.missingReason(PrivilegedDeviceService.GAME_MISSING + " (" + GAME + "; states unreadable)"));
    }

    @Test public void refusalsAvoidTheShizukuAdviceKeywords() {
        for (String value : new String[] {FirstSetupPackagePolicy.OTHER_PROFILE, FirstSetupPackagePolicy.UNCHECKED_PROFILE,
                InstalledGameVerifier.DIFFERENT_APP, PrivilegedDeviceService.GAME_MISSING}) {
            assertFalse(value.toLowerCase().contains("shizuku"));
            assertFalse(value.toLowerCase().contains("permission"));
        }
    }
}
