package dev.halixm.hokacepatcher;

import android.content.Context;
import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.TreeSet;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.json.JSONObject;
import org.junit.Assume;
import static org.junit.Assert.*;

/** Test-only, app-private, read-only input preflight. Never binds a provider or installs an APK. */
final class PrivateProbeFixtures {
    static final String DESCRIPTOR = "probe-fixtures/automatic-continuation/fixture.json";
    final JSONObject descriptor;
    final File base, normalFile, accessFile;
    final ApkIdentity normal, access;

    private static JSONObject json(File file) throws Exception {
        assertTrue("Missing fixture file: " + file, file.isFile());
        assertTrue("Fixture JSON must be 1..2 MiB: " + file, file.length() > 0 && file.length() <= 2 * 1024 * 1024);
        return new JSONObject(new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
    }
    private static File child(File root, String relative) throws Exception {
        assertFalse("Absolute fixture path", new File(relative).isAbsolute());
        assertTrue("Unsafe fixture path", relative.matches("[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*"));
        for (String part : relative.split("/")) assertFalse("Fixture traversal", part.equals(".") || part.equals(".."));
        // Android may expose /data/user/0 through a platform alias; reject links
        // below the trusted files root, rather than rejecting that platform alias.
        File file = new File(root.getCanonicalFile(), relative);
        assertEquals("Fixture symlink/escape", file.getAbsoluteFile(), file.getCanonicalFile());
        assertTrue(file.getCanonicalPath().startsWith(root.getCanonicalPath() + File.separator));
        return file;
    }
    private static String digest(InputStream input) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[1024 * 1024]; int count;
        while ((count = input.read(buffer)) >= 0) hash.update(buffer, 0, count);
        StringBuilder result = new StringBuilder();
        for (byte part : hash.digest()) result.append(String.format("%02x", part & 255));
        return result.toString();
    }
    private static void entries(File apk, JSONObject expected) throws Exception {
        TreeSet<String> actual = new TreeSet<>();
        try (ZipFile zip = new ZipFile(apk)) {
            for (Enumeration<? extends ZipEntry> iterator = zip.entries(); iterator.hasMoreElements();) {
                ZipEntry entry = iterator.nextElement();
                assertTrue("Duplicate APK entry", actual.add(entry.getName()));
                try (InputStream input = zip.getInputStream(entry)) {
                    assertEquals("Fixture APK entry: " + entry.getName(), expected.getString(entry.getName()), digest(input));
                }
            }
        }
        assertEquals("Exact APK entry manifest", expected.length(), actual.size());
        assertTrue(actual.contains("AndroidManifest.xml"));
    }
    static PrivateProbeFixtures load(Context context) throws Exception {
        File descriptor = child(context.getFilesDir(), DESCRIPTOR);
        Assume.assumeTrue("UNAVAILABLE: supply app-private " + descriptor +
            " with schema=1, normal/access {path, identity, entries}; no legacy APK paths are guessed", descriptor.isFile());
        return new PrivateProbeFixtures(context, json(descriptor));
    }
    private PrivateProbeFixtures(Context context, JSONObject value) throws Exception {
        descriptor = value; assertEquals("Fixture schema", 1, value.getInt("schema"));
        base = new File(context.getFilesDir(), "probe-fixtures/automatic-continuation");
        JSONObject n = value.getJSONObject("normal"), a = value.getJSONObject("access");
        normalFile = child(base, n.getString("path")); accessFile = child(base, a.getString("path"));
        normal = ApkIdentity.Companion.read(context, normalFile); normal.requireRecovery();
        access = ApkIdentity.Companion.read(context, accessFile);
        assertEquals(ApkIdentity.Companion.fromJson(n.getJSONObject("identity")), normal);
        assertEquals(ApkIdentity.Companion.fromJson(a.getJSONObject("identity")), access);
        assertTrue("Access debug flag", access.getDebuggable());
        assertEquals(normal.getCertificateSha256(), access.getCertificateSha256());
        assertEquals(normal.getPackageName(), access.getPackageName());
        assertEquals(normal.getVersionCode(), access.getVersionCode());
        assertEquals(normal.getVersionName(), access.getVersionName());
        assertNotEquals(normal.getSha256(), access.getSha256());
        entries(normalFile, n.getJSONObject("entries")); entries(accessFile, a.getJSONObject("entries"));
    }
    File sourceRoot() throws Exception {
        Assume.assumeTrue("UNAVAILABLE: full coordinator needs source_root, source_files {relative: sha256}, " +
            "staged_hashes and expected_counts in " + DESCRIPTOR, descriptor.has("source_root") &&
            descriptor.has("source_files") && descriptor.has("staged_hashes") && descriptor.has("expected_counts"));
        File root = child(base, descriptor.getString("source_root"));
        JSONObject expected = descriptor.getJSONObject("source_files");
        assertTrue("Empty source manifest", expected.length() > 0);
        TreeSet<String> actual = new TreeSet<>();
        try (java.util.stream.Stream<java.nio.file.Path> paths = Files.walk(root.toPath())) {
            for (java.nio.file.Path path : (Iterable<java.nio.file.Path>) paths::iterator) {
                assertFalse("Source fixture symlink", Files.isSymbolicLink(path));
                if (Files.isRegularFile(path)) actual.add(root.toPath().relativize(path).toString().replace(File.separatorChar, '/'));
            }
        }
        assertEquals("Exact source fixture file set", expected.length(), actual.size());
        for (Iterator<String> names = expected.keys(); names.hasNext();) {
            String name = names.next(); assertTrue("Missing source: " + name, actual.contains(name));
            assertEquals("Source fixture digest: " + name, expected.getString(name), ApkIdentity.Companion.digest(child(root, name)));
        }
        assertTrue("Empty staged manifest", descriptor.getJSONObject("staged_hashes").length() > 0);
        for (String name : new String[]{"text_tables", "applied_textures", "skipped_tables", "skipped_textures"})
            assertTrue("Invalid expected count: " + name, descriptor.getJSONObject("expected_counts").getInt(name) >= 0);
        return root;
    }
}
