package dev.halixm.hokacepatcher;

import android.os.ParcelFileDescriptor;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.json.JSONArray;
import org.json.JSONObject;

/** In-memory/private-file provider simulation. Never connects a device or invokes a shell. */
final class PrivateRecoveryPolicy {
    static String apply(IPrivilegedDeviceService device, Map<String, ?> live, String session, String operation,
                        String relative, ParcelFileDescriptor policy, ParcelFileDescriptor source,
                        long length, String sha256) {
        try {
            GameFilePolicy.INSTANCE.session(session);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            try (java.io.InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
                    ParcelFileDescriptor.dup(policy.getFileDescriptor()))) {
                byte[] buffer = new byte[4096]; int count;
                while ((count = input.read(buffer)) >= 0) {
                    output.write(buffer, 0, count);
                    if (output.size() > ArtifactReceipts.MAX_JSON) throw new IllegalStateException("Oversized policy");
                }
            }
            JSONObject files = RecoveryFilePolicy.INSTANCE.parse(ArtifactReceipts.INSTANCE.parse(output.toByteArray()));
            boolean whole = operation.equals("audit"), watchdog = operation.equals("clear_watchdog");
            Set<String> selected = new HashSet<>();
            for (java.util.Iterator<String> it = files.keys(); it.hasNext();) {
                String name = it.next();
                if (whole || (watchdog ? name.startsWith("Watchdog/") : name.equals(relative))) selected.add(name);
            }
            if (!whole && !watchdog && !selected.contains(relative)) throw new IllegalStateException("Unknown target");
            if (whole || watchdog) for (String name : live.keySet())
                if ((whole || name.startsWith("Watchdog/")) && !selected.contains(name))
                    throw new IllegalStateException("Unexpected live file");
            for (String name : selected) {
                JSONObject entry = files.getJSONObject(name);
                Object actual = live.get(name);
                if (actual == null) {
                    if (!entry.getBoolean("absent")) throw new IllegalStateException("Unexpected missing file");
                    continue;
                }
                byte[] bytes = actual instanceof File ? Files.readAllBytes(((File) actual).toPath()) : (byte[]) actual;
                StringBuilder hash = new StringBuilder();
                for (byte b : MessageDigest.getInstance("SHA-256").digest(bytes)) hash.append(String.format("%02x", b & 255));
                boolean matches = false; JSONArray states = entry.getJSONArray("states");
                for (int i = 0; i < states.length(); i++) {
                    JSONObject state = states.getJSONObject(i);
                    matches |= state.getLong("bytes") == bytes.length && state.getString("sha256").equals(hash.toString());
                }
                if (!matches) throw new IllegalStateException("Unexpected live bytes: " + name);
            }
            if (operation.equals("write")) return device.writeGameFile(session, relative, source, length, sha256);
            if (watchdog) device.clearGameWatchdog();
            if (operation.equals("delete")) live.remove(relative);
            return "verified";
        } catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new RuntimeException(error); }
    }
}
