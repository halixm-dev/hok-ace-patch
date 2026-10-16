package dev.halixm.hokacepatcher;

import org.junit.Test;
import static org.junit.Assert.*;

/** On-screen error text keeps the cause and drops the stack trace that scrolled it out of view. */
public final class ErrorSummaryTest {
    private static final ErrorSummary SUMMARY = ErrorSummary.INSTANCE;

    // The first_setup failure from the TECNO KL7 and Infinix X678B logs (2026-10-09), shortened.
    private static final String PROFILE = "Device command failed (255): \n" +
        "Exception occurred while executing 'list':\n" +
        "java.lang.SecurityException: Shell does not have permission to access user 999\n" +
        " com.android.server.am.ActivityManagerService.handleIncomingUser:14469 android.app.ActivityManager.handleIncomingUser:4953 com.android.server.pm.PackageManagerShellCommand.translateUserId:3792 \n" +
        "\tat com.android.server.am.UserController.handleIncomingUser(UserController.java:2578)\n" +
        "\tat com.android.server.pm.PackageManagerShellCommand.runListPackages(PackageManagerShellCommand.java:1065)\n" +
        "\tat android.os.Binder.execTransact(Binder.java:1275)\n" +
        "\t... 4 more\n";

    @Test public void keepsTheCauseAndDropsFramesAndCallers() {
        assertEquals("Device command failed (255):\n" +
            "Exception occurred while executing 'list':\n" +
            "java.lang.SecurityException: Shell does not have permission to access user 999", SUMMARY.cause(PROFILE));
    }

    @Test public void plainMessagesPassThrough() {
        assertEquals("Installed APK stream is incomplete", SUMMARY.cause("Installed APK stream is incomplete"));
        assertEquals("Copying and verifying the installed source APK",
            SUMMARY.cause("Copying and verifying the installed source APK"));
        assertEquals("", SUMMARY.cause(""));
    }

    @Test public void keepsCausedByAndOrdinaryColonText() {
        String raw = "java.lang.IllegalStateException: outer\n\tat a.B.c(B.java:1)\n" +
            "Caused by: java.io.IOException: Need 2.1 GB free\n\tat d.E.f(E.java:2)\n";
        assertEquals("java.lang.IllegalStateException: outer\nCaused by: java.io.IOException: Need 2.1 GB free",
            SUMMARY.cause(raw));
        assertEquals("Version 1.1.1:774472 differs", SUMMARY.cause("Version 1.1.1:774472 differs"));
    }

    @Test public void longOutputIsCutAndMarked() {
        StringBuilder raw = new StringBuilder();
        for (int line = 0; line < 20; line++) raw.append("line ").append(line).append('\n');
        String summary = SUMMARY.cause(raw.toString());
        assertTrue(summary.startsWith("line 0\n"));
        assertTrue(summary.endsWith("\n…"));
        assertFalse(summary.contains("line 8"));
    }

    @Test public void onlyFramesFallsBackToTheRawText() {
        assertEquals("\tat a.B.c(B.java:1)".trim(), SUMMARY.cause("\tat a.B.c(B.java:1)\n"));
    }
}
