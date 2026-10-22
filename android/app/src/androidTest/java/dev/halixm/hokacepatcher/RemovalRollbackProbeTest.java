package dev.halixm.hokacepatcher;

import android.content.Context;
import android.os.ParcelFileDescriptor;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/**
 * Remove translation on private fixture files: `build_removal` stages the rebuilt pristine files, an
 * interrupted write-back rolls back to the translated snapshot, and a complete one leaves pristine.
 */
@RunWith(AndroidJUnit4.class)
public final class RemovalRollbackProbeTest {
    private static final String ID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    private static final String[] NAMES = {"packages/1/1.info", "packages/1/1.db", "packages/1/1_0.db"};

    private static String hash(byte[] value) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte part : MessageDigest.getInstance("SHA-256").digest(value)) result.append(String.format("%02x", part & 255));
        return result.toString();
    }
    private static byte[] read(java.io.InputStream input) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096]; int count;
        while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
        return output.toByteArray();
    }

    /** The game's package files, held in memory; a write can be cut off after its commit. */
    private static final class Device extends IPrivilegedDeviceService.Stub {
        final Map<String, byte[]> files = new HashMap<>();
        int writes;
        int failAt;
        @Override public String writeGameFile(String session, String relative, ParcelFileDescriptor source,
                                              long length, String sha256) {
            try (ParcelFileDescriptor.AutoCloseInputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
                ParcelFileDescriptor.dup(source.getFileDescriptor()))) {
                GameFilePolicy.INSTANCE.validate(relative, true);
                byte[] value = read(input);
                assertEquals(length, value.length); assertEquals(sha256, hash(value));
                files.put(relative, value);
                if (++writes == failAt) throw new IllegalStateException("Injected interruption during write-back");
                return "verified";
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new RuntimeException(error); }
        }
        @Override public String validateGameSnapshot(ParcelFileDescriptor descriptor) { return "verified"; }
        @Override public void clearGameWatchdog() { files.keySet().removeIf(name -> name.startsWith("Watchdog/")); }
        @Override public void clearSessionTemp(String session, String relative) { GameFilePolicy.INSTANCE.session(session); }
        @Override public void restoreWatchdogDirectory(String relative) { GameFilePolicy.INSTANCE.watchdogDirectory(relative); }
        @Override public String diagnostics() { throw new UnsupportedOperationException(); }
        @Override public String gameApkInfo() { throw new UnsupportedOperationException(); }
        @Override public String copyGameApk(ParcelFileDescriptor destination) { throw new UnsupportedOperationException(); }
        @Override public byte[] probeFixture(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String estimateGameSnapshot() { throw new UnsupportedOperationException(); }
        @Override public void forceStopGame() { throw new UnsupportedOperationException(); }
        @Override public String reinstallFixture(boolean abandon) { throw new UnsupportedOperationException(); }
        @Override public String replaceGameApk(ParcelFileDescriptor source, long length) { throw new UnsupportedOperationException(); }
        @Override public String probeGame(byte[] value) { throw new UnsupportedOperationException(); }
        @Override public String snapshotGame(ParcelFileDescriptor destination, long budget) { throw new UnsupportedOperationException(); }
        @Override public void validateFirstSetupSource(String sha) { throw new UnsupportedOperationException(); }
        @Override public void checkGameProfiles() { throw new UnsupportedOperationException(); }
        @Override public String releaseReplacedGameApks() { return "{\"released\":false,\"freed_bytes\":0}"; }
        @Override public void deleteGameFile(String session, String relative, String sha) { files.remove(relative); }
        @Override public boolean firstSetupGameAbsent() { throw new UnsupportedOperationException(); }
        @Override public void removeGameForFirstSetup(String sha) { throw new UnsupportedOperationException(); }
        @Override public String installFirstSetupGame(ParcelFileDescriptor source, long length) { throw new UnsupportedOperationException(); }
        @Override public void destroy() { throw new UnsupportedOperationException(); }
    }

    private static SessionJournal applying(File parent) throws Exception {
        SessionJournal journal = SessionJournal.Companion.create(parent, ID, ID);
        journal.intent("install_access", new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.SNAPSHOT_READY, new JSONObject());
        journal.intent("install_normal", new JSONObject());
        journal.outcome(PatchPhase.NORMAL_RESTORED_FOR_BUILD, new JSONObject().put("normal_verified", true));
        journal.outcome(PatchPhase.BUILDING, new JSONObject());
        return journal;
    }

    /**
     * Writes, through Python, a translated snapshot of <NAMES> into the session and a kept delta whose
     * pristine side differs; returns {name: [translated sha, pristine sha]}.
     */
    private static JSONObject fixture(Python python, File root, File session, File keep) throws Exception {
        Object scope = python.getModule("builtins").callAttr("dict");
        python.getModule("builtins").callAttr("exec",
            "import io, json, tarfile\n" +
            "from pathlib import Path\n" +
            "import pristine_delta\n" +
            "from mobile_snapshot import extract_snapshot\n" +
            "def make(session, keep, scratch):\n" +
            "    session, keep, scratch = Path(session), Path(keep), Path(scratch)\n" +
            "    pristine = {'1/1.info': b'{\"version\":\"1.6.0.1\"}', '1/1.db': b'index' * 300, '1/1_0.db': bytes(range(256)) * 40}\n" +
            "    translated = dict(pristine, **{'1/1.db': b'INDEX' + pristine['1/1.db'][5:], '1/1_0.db': b'EN' * 50 + pristine['1/1_0.db'][100:] + b'appended'})\n" +
            "    for folder, files in (('clean', pristine), ('staged', translated)):\n" +
            "        for name, data in files.items():\n" +
            "            if name.endswith('.db'):\n" +
            "                (scratch / folder / name).parent.mkdir(parents=True, exist_ok=True); (scratch / folder / name).write_bytes(data)\n" +
            "    delta = pristine_delta.make(scratch / 'clean', scratch / 'staged')\n" +
            "    pristine_delta.write(delta, keep / pristine_delta.DELTA_NAME)\n" +
            "    pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, delta.staged_hashes)\n" +
            "    archive = scratch / 'snapshot.tar'\n" +
            "    with tarfile.open(archive, 'w') as output:\n" +
            "        for name, data in translated.items():\n" +
            "            member = tarfile.TarInfo('packages/' + name); member.size = len(data); output.addfile(member, io.BytesIO(data))\n" +
            "    extract_snapshot(archive, session / 'snapshot')\n" +
            "    import hashlib\n" +
            "    return json.dumps({name: [hashlib.sha256(translated[name]).hexdigest(), hashlib.sha256(pristine[name]).hexdigest()] for name in translated})\n",
            scope);
        return new JSONObject(python.getModule("builtins").callAttr("eval", "make", scope)
            .call(session.getPath(), keep.getPath(), root.getPath()).toString());
    }

    private static Device translatedDevice(File session) throws Exception {
        Device device = new Device();
        for (String name : NAMES) device.files.put(name, Files.readAllBytes(new File(session, "snapshot/" + name).toPath()));
        return device;
    }

    @Test public void testInterruptedWriteBackRollsBackAndCompleteOneIsPristine() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File engine = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python python = Python.getInstance();
        python.getModule("android_bridge").callAttr("diagnostics", engine.getPath());
        File root = new File(context.getFilesDir(), "removal-probes/" + UUID.randomUUID());
        File keep = new File(root, "keep");
        assertTrue(keep.mkdirs());

        // Interrupted after the first file: rollback restores the translated snapshot.
        SessionJournal journal = applying(new File(root, "sessions"));
        JSONObject identities = fixture(python, new File(root, "scratch-1"), journal.getDirectory(), keep);
        JSONObject summary = new JSONObject(python.getModule("android_bridge").callAttr("build_removal",
            engine.getPath(), journal.getDirectory().getPath(), keep.getPath()).toString());
        assertEquals(2, summary.getJSONArray("removed").length());
        JSONObject hashes = new JSONObject(new String(Files.readAllBytes(
            new File(journal.getDirectory(), "staged-hashes.json").toPath()), StandardCharsets.UTF_8));
        assertEquals(identities.getJSONArray("1/1_0.db").getString(1), hashes.getString("1/1_0.db"));
        journal.outcome(PatchPhase.STAGED, new JSONObject());
        journal.intent("install_access", new JSONObject());
        journal.outcome(PatchPhase.APPLY_ACCESS_INSTALLED, new JSONObject());
        journal.outcome(PatchPhase.APPLYING, new JSONObject());
        Device device = translatedDevice(journal.getDirectory());
        Map<String, byte[]> translated = new HashMap<>(device.files);
        GameFileTransaction transaction = new GameFileTransaction(journal, device);
        transaction.verifyOriginals();
        device.failAt = 1;
        try {
            transaction.write("packages/1/1.db", new File(journal.getDirectory(), "out/1/1.db"), hashes.getString("1/1.db"), false);
            fail("Interruption not injected");
        } catch (IllegalStateException expected) { }
        assertEquals(identities.getJSONArray("1/1.db").getString(1), hash(device.files.get("packages/1/1.db")));
        journal.recoveryRequired("interrupted write-back"); journal.outcome(PatchPhase.RESTORING, new JSONObject());
        device.failAt = 0;
        new GameFileTransaction(journal, device).rollback();
        assertFalse(journal.getDirtyPackages());
        for (String name : NAMES) assertArrayEquals(name, translated.get(name), device.files.get(name));

        // Complete: every file the delta names is back at its pristine bytes.
        SessionJournal second = applying(new File(root, "sessions"));
        fixture(python, new File(root, "scratch-2"), second.getDirectory(), keep);
        python.getModule("android_bridge").callAttr("build_removal",
            engine.getPath(), second.getDirectory().getPath(), keep.getPath());
        second.outcome(PatchPhase.STAGED, new JSONObject());
        second.intent("install_access", new JSONObject());
        second.outcome(PatchPhase.APPLY_ACCESS_INSTALLED, new JSONObject());
        second.outcome(PatchPhase.APPLYING, new JSONObject());
        device = translatedDevice(second.getDirectory());
        hashes = new JSONObject(new String(Files.readAllBytes(
            new File(second.getDirectory(), "staged-hashes.json").toPath()), StandardCharsets.UTF_8));
        transaction = new GameFileTransaction(second, device);
        transaction.verifyOriginals();
        for (Iterator<String> names = hashes.keys(); names.hasNext(); ) {
            String name = names.next();
            transaction.write("packages/" + name, new File(second.getDirectory(), "out/" + name), hashes.getString(name), false);
        }
        transaction.finishApply(hashes);
        for (Iterator<String> names = identities.keys(); names.hasNext(); ) {
            String name = names.next();
            assertEquals(name, identities.getJSONArray(name).getString(1), hash(device.files.get("packages/" + name)));
        }
        // The session's delta is empty: promoting it deletes the patcher's delta, so the next run is a
        // first install.
        assertTrue(new File(keep, "delta.bin").isFile());
        python.getModule("android_bridge").callAttr("keep_delta", engine.getPath(), second.getDirectory().getPath(), keep.getPath());
        assertFalse(new File(keep, "delta.bin").exists());
    }
}
