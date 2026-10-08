package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.ContextWrapper;
import android.util.Base64;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import java.io.File;
import java.io.StringWriter;
import java.nio.file.Files;
import java.util.UUID;
import static org.junit.Assert.*;

/** Raw diagnostic export must neither repair journals nor follow links or read unbounded files. */
public final class DiagnosticLogExportProbeTest {
    private Context context() {
        Context actual = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(actual.getFilesDir(), "diagnostic-export-probes/" + UUID.randomUUID());
        assertTrue(root.mkdirs());
        return new ContextWrapper(actual) { @Override public File getFilesDir() { return root; } };
    }
    private File write(Context context, String path, byte[] bytes) throws Exception {
        File file = new File(context.getFilesDir(), path);
        file.getParentFile().mkdirs(); Files.write(file.toPath(), bytes); return file;
    }
    private String export(Context context) {
        StringWriter output = new StringWriter(); new DiagnosticLogExport(context).write(output); return output.toString();
    }
    @Test public void corruptBaseAndBackupExportExactBytesWithoutAtomicRecovery() throws Exception {
        Context context = context(); String id = UUID.randomUUID().toString();
        byte[] raw = new byte[] {'{', 0, (byte) 255};
        byte[] backup = "{backup-unvalidated".getBytes("UTF-8");
        File base = write(context, "sessions/" + id + "/journal.json", raw);
        File bak = write(context, "sessions/" + id + "/journal.json.bak", backup);
        write(context, "emergency-restore.json", "{bad-emergency".getBytes("UTF-8"));
        String result = export(context);
        int found = 0;
        for (String line : result.split("\n")) if (line.startsWith("{")) {
            JSONObject value = new JSONObject(line); assertTrue(value.getBoolean("unvalidated"));
            byte[] bytes = Base64.decode(value.getString("raw_base64"), Base64.NO_WRAP);
            if (value.getString("path").equals("sessions/" + id + "/journal.json")) { assertArrayEquals(raw, bytes); found++; }
            if (value.getString("path").equals("sessions/" + id + "/journal.json.bak")) { assertArrayEquals(backup, bytes); found++; }
        }
        assertEquals(2, found); assertArrayEquals(raw, Files.readAllBytes(base.toPath()));
        assertArrayEquals(backup, Files.readAllBytes(bak.toPath()));
        try { SessionJournal.Companion.history(new File(context.getFilesDir(), "sessions")); fail("Corruption no longer blocks recovery"); }
        catch (Exception expected) { }
    }
    @Test public void linkedOversizedMissingAndDraftRecordsAreExplicitlyHandled() throws Exception {
        Context context = context();
        String missing = UUID.randomUUID().toString();
        assertTrue(new File(context.getFilesDir(), "sessions/" + missing).mkdirs());
        String draft = ".creating-" + UUID.randomUUID();
        write(context, "sessions/" + draft + "/journal.json", "SECRET-DRAFT".getBytes("UTF-8"));
        File source = write(context, "not-a-record", "SECRET-LINK".getBytes("UTF-8"));
        String linked = UUID.randomUUID().toString();
        File folder = new File(context.getFilesDir(), "sessions/" + linked); assertTrue(folder.mkdirs());
        Files.createSymbolicLink(new File(folder, "journal.json").toPath(), source.toPath());
        write(context, "emergency-restore.json", new byte[1024 * 1024 + 1]);
        String result = export(context);
        assertTrue(result.contains("Published journal missing: sessions/" + missing));
        assertTrue(result.contains("Skipped linked path")); assertTrue(result.contains("Skipped oversized record"));
        assertFalse(result.contains(draft)); assertFalse(result.contains("SECRET-DRAFT")); assertFalse(result.contains("SECRET-LINK"));
    }
    @Test public void logTailIsBoundedAndOutputFailurePropagates() throws Exception {
        Context context = context(); byte[] log = new byte[300 * 1024]; java.util.Arrays.fill(log, (byte) 'x');
        write(context, "feasibility.log", log);
        String result = export(context);
        JSONObject value = null;
        for (String line : result.split("\n")) if (line.startsWith("{")) value = new JSONObject(line);
        assertNotNull(value); assertEquals(256 * 1024, value.getInt("exported_bytes"));
        assertEquals(44 * 1024, value.getInt("offset"));
        java.io.Writer failed = new java.io.Writer() {
            public void write(char[] chars, int offset, int length) throws java.io.IOException { throw new java.io.IOException("Destination failed"); }
            public void flush() {} public void close() {}
        };
        try { new DiagnosticLogExport(context).write(failed); fail("Destination failure reported success"); }
        catch (Exception expected) { assertTrue(expected.getMessage().contains("Destination failed")); }
    }
    @Test public void totalRawBytesAndSessionEnumerationHaveHardLimits() throws Exception {
        Context context = context();
        byte[] bytes = new byte[1024 * 1024];
        for (int index = 0; index < 9; index++)
            write(context, "sessions/" + UUID.randomUUID() + "/journal.json", bytes);
        String result = export(context); long exported = 0;
        for (String line : result.split("\n")) if (line.startsWith("{"))
            exported += new JSONObject(line).getLong("exported_bytes");
        assertEquals(8L * 1024 * 1024, exported); assertTrue(result.contains("Export byte limit reached"));
        Context many = context();
        for (int index = 0; index < 260; index++)
            assertTrue(new File(many.getFilesDir(), "sessions/" + UUID.randomUUID()).mkdirs());
        String limited = export(many);
        assertTrue(limited.contains("Entry limit reached: sessions"));
        int records = 0;
        for (String line : limited.split("\n")) if (line.startsWith("Published journal missing:")) records++;
        assertEquals(256, records);
    }
}
