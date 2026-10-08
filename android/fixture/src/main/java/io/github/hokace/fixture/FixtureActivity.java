package io.github.hokace.fixture;

import android.app.Activity;
import android.os.Bundle;
import android.os.ResultReceiver;
import android.net.Uri;
import android.widget.TextView;
import java.io.InputStream;
import java.security.MessageDigest;

/** Disposable private-data target for shell run-as diagnostics. */
public final class FixtureActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView text = new TextView(this);
        text.setText("Disposable HOK ACE run-as fixture. Contains no game data.");
        setContentView(text);
        ResultReceiver receiver = getIntent().getParcelableExtra("result");
        Uri uri = getIntent().getData();
        if (receiver != null && uri != null) {
            new Thread(() -> {
                Bundle result = new Bundle();
                try {
                    if (!"content".equals(uri.getScheme()) ||
                        !"dev.halixm.hokacepatcher.recovery".equals(uri.getAuthority()))
                        throw new IllegalArgumentException("Unsupported diagnostic URI");
                    MessageDigest hash = MessageDigest.getInstance("SHA-256");
                    long bytes = 0;
                    try (InputStream input = getContentResolver().openInputStream(uri)) {
                        if (input == null) throw new IllegalStateException("No provider stream");
                        byte[] buffer = new byte[1024 * 1024];
                        int count;
                        while ((count = input.read(buffer)) >= 0) {
                            bytes += count;
                            if (bytes > 3L * 1024 * 1024 * 1024) throw new IllegalStateException("Stream too large");
                            hash.update(buffer, 0, count);
                        }
                    }
                    StringBuilder hex = new StringBuilder();
                    for (byte value : hash.digest()) hex.append(String.format("%02x", value & 255));
                    result.putString("sha256", hex.toString()); result.putLong("bytes", bytes);
                    receiver.send(0, result);
                    runOnUiThread(() -> text.setText("Recovery URI read/hash passed; no APK installed."));
                } catch (Exception error) {
                    result.putString("error", error.toString()); receiver.send(1, result);
                }
            }, "recovery-uri-probe").start();
        }
    }
}
