package dev.halixm.hokacepatcher;

import android.content.Context;
import android.os.Bundle;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.net.*;
import java.security.MessageDigest;
import java.util.Arrays;
import static org.junit.Assert.*;

/** Temporary loopback-only development receiver, absent from the shipped application. */
@RunWith(AndroidJUnit4.class)
public final class ScratchReceiverTest {
    @Test public void receiveVerifiedInputs() throws Exception {
        Bundle args = InstrumentationRegistry.getArguments();
        String name = args.getString("session");
        String token = args.getString("token");
        assertNotNull(name); assertTrue(name.matches("[a-zA-Z0-9-]{1,64}"));
        assertNotNull(token); assertTrue(token.matches("[0-9a-f]{64}"));
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = new File(context.getFilesDir(), "scratch/" + name).getCanonicalFile();
        assertTrue("Use a fresh scratch session", root.mkdirs());
        try (ServerSocket server = new ServerSocket(37491, 1, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(60000);
            android.util.Log.i("HokAceProbe", "Scratch receiver ready");
            try (Socket socket = server.accept(); DataInputStream input = new DataInputStream(socket.getInputStream());
                 DataOutputStream output = new DataOutputStream(socket.getOutputStream())) {
                socket.setSoTimeout(60000);
                byte[] credential = new byte[64]; input.readFully(credential);
                assertEquals(token, new String(credential, java.nio.charset.StandardCharsets.US_ASCII));
                int count = input.readInt(); assertTrue(count > 0 && count <= 2000);
                long total = input.readLong(); assertTrue(total > 0 && total <= 8L * 1024 * 1024 * 1024);
                assertTrue("Insufficient scratch storage", root.getUsableSpace() > total + 512L * 1024 * 1024);
                output.writeByte(1); output.flush();
                byte[] buffer = new byte[1024 * 1024];
                long received = 0;
                for (int index = 0; index < count; index++) {
                    int length = input.readUnsignedShort(); assertTrue(length > 0 && length <= 512);
                    byte[] pathBytes = new byte[length]; input.readFully(pathBytes);
                    String path = new String(pathBytes, java.nio.charset.StandardCharsets.UTF_8);
                    assertFalse(path.startsWith("/")); assertFalse(path.contains("\\"));
                    File file = new File(root, path).getCanonicalFile();
                    assertTrue(file.getPath().startsWith(root.getPath() + File.separator));
                    long size = input.readLong(); assertTrue(size >= 0 && received + size <= total);
                    byte[] expected = new byte[32]; input.readFully(expected);
                    assertTrue(file.getParentFile().isDirectory() || file.getParentFile().mkdirs());
                    File partial = new File(file.getParentFile(), file.getName() + ".partial");
                    MessageDigest hash = MessageDigest.getInstance("SHA-256");
                    try (FileOutputStream stream = new FileOutputStream(partial)) {
                        long remaining = size;
                        while (remaining > 0) {
                            int bytes = input.read(buffer, 0, (int) Math.min(buffer.length, remaining));
                            assertTrue("Incomplete scratch file", bytes > 0);
                            stream.write(buffer, 0, bytes); hash.update(buffer, 0, bytes); remaining -= bytes;
                        }
                        stream.getFD().sync();
                    }
                    assertArrayEquals("Input digest mismatch: " + path, expected, hash.digest());
                    assertTrue(partial.renameTo(file));
                    received += size; output.writeByte(1); output.flush();
                }
                assertEquals(total, received);
                android.util.Log.i("HokAceProbe", "PASS: " + count + " scratch files, " + received + " bytes SHA-256 verified");
            }
        }
    }
}
