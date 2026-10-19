package dev.halixm.hokacepatcher;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.Test;
import static org.junit.Assert.*;

/** Profile fallback parsing and the guard over a fake read-only device; no installation or game removal. */
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

    // vivo V2561, Android 16: `pm list packages --user 10` exits 1 with only this line.
    private static final String VIVO_DENIAL = "Device command failed (1): Error: Shell does not have permission to access user 10";

    @Test public void plainErrorDenialIsRecognizedOnlyForItsOwnUser() {
        assertTrue(POLICY.profileDenied(VIVO_DENIAL, 10));
        assertTrue(POLICY.profileDenied("Device command failed (1): \nError: Shell does not have permission to access user 10\n", 10));
        assertFalse(POLICY.profileDenied(VIVO_DENIAL, 1));
        assertFalse(POLICY.profileDenied(VIVO_DENIAL, 100));
        assertFalse(POLICY.profileDenied(VIVO_DENIAL.replace("user 10", "user 100"), 10));
        assertFalse(POLICY.profileDenied(VIVO_DENIAL.replace("user 10", "user 101"), 10));
        String[] unrelated = {
            "Device command failed (1): Error: Shell does not have permission to access user 10 profile data",
            "Device command failed (1): Error: unknown user 10",
            "Device command failed (1): Error: permission denied",
            "Device command failed (255): Failure [INSTALL_FAILED_USER_RESTRICTED: Shell does not have permission to access user 10]",
            "Device command failed (1): Error: something broke\nError: Shell does not have permission to access user 10",
            "Error: Shell does not have permission to access user 10",
        };
        for (String value : unrelated) assertFalse(value, POLICY.profileDenied(value, 10));
    }

    /** Answers each read-only command by its joined arguments; a value starting with "!" fails like a non-zero exit. */
    private static final class FakeDevice {
        final Map<String, String> answers = new HashMap<>();
        final List<String> calls = new ArrayList<>();
        String dump;

        FakeDevice users(String... ids) {
            StringBuilder out = new StringBuilder("Users:\n");
            for (String id : ids) out.append("\tUserInfo{").append(id).append(":Owner:c13} running\n");
            answers.put("/system/bin/pm list users", out.toString());
            return this;
        }

        FakeDevice listing(int user, String value) {
            answers.put("/system/bin/pm list packages --user " + user + " " + GAME, value);
            return this;
        }

        void run() {
            POLICY.requireNoOtherUsers(GAME, args -> {
                String key = String.join(" ", args);
                calls.add(key);
                String value = answers.get(key);
                if (value == null) throw new AssertionError("Unexpected command: " + key);
                if (value.startsWith("!")) throw new IllegalStateException(value.substring(1));
                return value;
            }, () -> {
                calls.add("dumpsys");
                if (dump == null) throw new IllegalStateException("Device command failed (1): dumpsys failed");
                return dump;
            });
        }

        String refusal() {
            try { run(); } catch (IllegalStateException error) { return error.getMessage(); }
            fail("Guard permitted first setup; calls " + calls);
            return null;
        }
    }

    private static String dumpWith(int user, String installed) {
        return "  Package [" + GAME + "] (7b2c1e4):\n" + user(0, "true", "false", 0) + user(user, installed, "false", 0);
    }

    private static FakeDevice vivo() { return new FakeDevice().users("0", "10").listing(10, "!" + VIVO_DENIAL); }

    @Test public void guardPermitsADeniedProfileTheDumpMeasuresAbsent() {
        FakeDevice device = vivo();
        device.dump = dumpWith(10, "false");
        device.run();
        // The guard only reads: no removal or install command passes through it.
        for (String call : device.calls) assertFalse(call, call.contains("uninstall") || call.contains("install-"));
    }

    @Test public void guardKeepsTheSecurityExceptionFallback() {
        FakeDevice device = new FakeDevice().users("0", "999").listing(999, "!Device command failed (255): \n" +
            "Exception occurred while executing 'list':\njava.lang.SecurityException: Shell does not have permission to access user 999\n");
        device.dump = dumpWith(999, "false");
        device.run();
        device.dump = dumpWith(999, "true");
        assertTrue(device.refusal().startsWith(FirstSetupPackagePolicy.OTHER_PROFILE + " (user 999)"));
    }

    @Test public void guardRefusesADeniedProfileWithTheGame() {
        FakeDevice device = vivo();
        device.dump = dumpWith(10, "true");
        assertTrue(device.refusal().startsWith(FirstSetupPackagePolicy.OTHER_PROFILE + " (user 10)"));
    }

    @Test public void guardRefusesWhenTheDumpCannotRuleTheProfileOut() {
        String header = "  Package [" + GAME + "] (7b2c1e4):\n";
        String[] unreadable = {
            header + user(0, "true", "false", 0),                                   // profile missing from the record
            header + user(10, "false", "false", 0) + user(10, "true", "false", 0),   // conflicting
            header + "    User 10: ceDataInode=0 installed=",                        // truncated
            header + user(10, "false", "false", 0) + "Error: dump failed\n",         // malformed
        };
        for (String dump : unreadable) {
            FakeDevice device = vivo();
            device.dump = dump;
            assertNotNull(dump, device.refusal());
        }
        FakeDevice failed = vivo();
        failed.dump = null;
        assertTrue(failed.refusal().contains("dumpsys failed"));
    }

    @Test public void guardAcceptsNoRecordOnlyWhenTheRetainedListingAgrees() {
        String retained = "/system/bin/pm list packages -u " + GAME;
        FakeDevice absent = vivo();
        absent.dump = "";
        absent.answers.put(retained, "");
        absent.run();
        assertTrue(absent.calls.contains(retained));

        FakeDevice kept = vivo();
        kept.dump = "";
        kept.answers.put(retained, "package:" + GAME + "\n");
        assertTrue(kept.refusal().startsWith(FirstSetupPackagePolicy.UNCHECKED_PROFILE));
    }

    @Test public void guardPropagatesOtherFailuresWithoutTheFallback() {
        String[] failures = {
            VIVO_DENIAL.replace("user 10", "user 100"),
            "Device command failed (1): Error: unknown user 10",
            "Device command failed (1): Error: permission denied",
        };
        for (String failure : failures) {
            FakeDevice device = new FakeDevice().users("0", "10").listing(10, "!" + failure);
            device.dump = dumpWith(10, "false");
            assertEquals(failure, device.refusal());
            assertFalse(device.calls.contains("dumpsys"));
        }
    }

    @Test public void guardReadsAccessibleProfilesDirectly() {
        FakeDevice clean = new FakeDevice().users("0", "10").listing(10, "");
        clean.run();
        assertFalse(clean.calls.contains("dumpsys"));
        FakeDevice installed = new FakeDevice().users("0", "10").listing(10, "package:" + GAME + "\n");
        assertTrue(installed.refusal().startsWith(FirstSetupPackagePolicy.OTHER_PROFILE + " (user 10)"));
        FakeDevice single = new FakeDevice().users("0");
        single.run();
        assertEquals(List.of("/system/bin/pm list users"), single.calls);
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
