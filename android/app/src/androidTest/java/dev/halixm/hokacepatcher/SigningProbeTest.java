package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.junit.Test;
import org.junit.Assume;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.security.MessageDigest;
import static org.junit.Assert.*;

/** Compare the Java RSA adapter with desktop v2 output; never installs a game APK. */
@RunWith(AndroidJUnit4.class)
public final class SigningProbeTest {
    private static String sha256(File file) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) hash.update(buffer, 0, count);
        }
        StringBuilder result = new StringBuilder();
        for (byte value : hash.digest()) result.append(String.format("%02x", value & 255));
        return result.toString();
    }

    @Test public void testFixtureSigningParity() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String session = InstrumentationRegistry.getArguments().getString("session");
        assertNotNull(session);
        assertTrue(session.matches("[a-zA-Z0-9-]{1,64}"));
        File scratch = new File(context.getFilesDir(), "scratch/" + session);
        File root = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        GameSigner signer = new GameSigner(root);
        String outputName = InstrumentationRegistry.getArguments().getString("signedOutput", "java-signed.apk");
        assertTrue(outputName.matches("java-signed(?:-[a-z0-9]+)?[.]apk"));
        File input = new File(scratch, "unsigned.apk"), output = new File(scratch, outputName);
        JSONObject result = new JSONObject(Python.getInstance().getModule("android_bridge").callAttr(
            "sign_with_java", root.getPath(), input.getPath(), output.getPath(), signer).toString());
        assertEquals(sha256(new File(scratch, "baseline.apk")), sha256(output));
        assertEquals(result.getString("sha256"), sha256(output));
        PackageInfo archive = context.getPackageManager().getPackageArchiveInfo(output.getPath(),
            PackageManager.GET_SIGNING_CERTIFICATES);
        assertNotNull("Android could not parse signed APK", archive);
        assertEquals("io.github.hokace.fixture", archive.packageName);
        assertEquals(1, archive.signingInfo.getApkContentsSigners().length);
        assertArrayEquals(signer.getCertificateDer(), archive.signingInfo.getApkContentsSigners()[0].toByteArray());
        android.util.Log.i("HokAceProbe", "PASS: Java RSA/desktop v2 byte parity " + result);
    }

    @Test public void testGameApkSigningParity() throws Exception {
        Assume.assumeTrue("true".equals(InstrumentationRegistry.getArguments().getString("probeLargeApk")));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String session = InstrumentationRegistry.getArguments().getString("session");
        String expected = InstrumentationRegistry.getArguments().getString("expectedApkSha256");
        assertNotNull(session); assertNotNull(expected);
        assertTrue(session.matches("[a-zA-Z0-9-]{1,64}"));
        assertTrue(expected.matches("[0-9a-f]{64}"));
        File scratch = new File(context.getFilesDir(), "scratch/" + session);
        File input = new File(scratch, "normal.apk"), output = new File(scratch, "java-game-signed.apk");
        assertTrue(context.getFilesDir().getUsableSpace() > input.length() + 256L * 1024 * 1024);
        assertEquals(expected, sha256(input));
        File root = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        GameSigner signer = new GameSigner(root);
        JSONObject result = new JSONObject(Python.getInstance().getModule("android_bridge").callAttr(
            "sign_with_java", root.getPath(), input.getPath(), output.getPath(), signer).toString());
        assertEquals(input.length(), output.length());
        assertEquals(expected, sha256(output));
        assertEquals(expected, result.getString("sha256"));
        android.util.Log.i("HokAceProbe", "PASS: full game APK Java/desktop v2 byte parity " + result);
    }
}
