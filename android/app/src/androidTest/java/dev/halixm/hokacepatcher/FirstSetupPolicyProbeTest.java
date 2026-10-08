package dev.halixm.hokacepatcher;

import org.junit.Test;
import static org.junit.Assert.*;

/** Listing validation only; no commands, installation or game removal. */
public final class FirstSetupPolicyProbeTest {
    @Test public void testUserProfilesAndExactPackageNames() {
        assertEquals(2, FirstSetupPackagePolicy.INSTANCE.users("Users:\n\tUserInfo{0:Owner:13} running\n\tUserInfo{10:Work:30}\n").size());
        assertTrue(FirstSetupPackagePolicy.INSTANCE.containsGame("package:com.tencent.tmgp.osgame\n"));
        assertFalse(FirstSetupPackagePolicy.INSTANCE.containsGame("package:com.tencent.tmgp.osgame.other\n"));
        assertFalse(FirstSetupPackagePolicy.INSTANCE.containsGame(""));
        assertTrue(FirstSetupPackagePolicy.INSTANCE.containsPackage("package:io.github.hokace.fixture\n", PrivilegedDeviceService.FIXTURE));
        assertFalse(FirstSetupPackagePolicy.INSTANCE.containsPackage("package:com.tencent.tmgp.osgame\n", PrivilegedDeviceService.FIXTURE));
        try { FirstSetupPackagePolicy.INSTANCE.containsPackage("package:com.anything.else\n", "com.anything.else"); fail("Arbitrary package target accepted"); }
        catch (IllegalArgumentException expected) { }
        for (String value : new String[] {"", "Users:\n", "Users:\nUserInfo{10:Work:30}",
                "Users:\nUserInfo{0:Owner:13}\nUserInfo{0:Clone:13}", "Users:\nUserInfo{0:Owner:13}\ntruncated"}) {
            try { FirstSetupPackagePolicy.INSTANCE.users(value); fail("Invalid users accepted"); }
            catch (IllegalStateException expected) { }
        }
        try { FirstSetupPackagePolicy.INSTANCE.containsGame("Error: permission denied"); fail("Error treated as absence"); }
        catch (IllegalStateException expected) { }
    }
    @Test public void testInvalidRemovalIdentityRejectedBeforeShellAccess() {
        for (String value : new String[] {"", "../game", "0", "$(pm uninstall anything)"}) {
            try { new PrivilegedDeviceService().removeGameForFirstSetup(value); fail("Invalid removal identity accepted"); }
            catch (IllegalArgumentException expected) { }
        }
    }
}
