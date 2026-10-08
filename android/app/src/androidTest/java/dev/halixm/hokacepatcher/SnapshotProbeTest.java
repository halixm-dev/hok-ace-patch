package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Test private snapshot parsing and refusal paths; no privileged/game operations. */
@RunWith(AndroidJUnit4.class)
public final class SnapshotProbeTest {
    @Test public void testSnapshotIntegrityAndUnsafeArchives() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python python = Python.getInstance();
        python.getModule("android_bridge").callAttr("diagnostics", root.getPath());
        python.getModule("builtins").callAttr("exec",
            "import io, tarfile, tempfile\n" +
            "from pathlib import Path\n" +
            "from mobile_snapshot import extract_snapshot, verify_snapshot\n" +
            "with tempfile.TemporaryDirectory() as temporary:\n" +
            "    base = Path(temporary); archive = base / 'source.tar'\n" +
            "    with tarfile.open(archive, 'w') as output:\n" +
            "        for name, data in [('packages/1/1.info', b'{\"version\":\"1.4.0.2\"}'), ('packages/1/1.db', b'index'), ('Watchdog/PatchList.db', b'watchdog')]:\n" +
            "            member = tarfile.TarInfo(name); member.size = len(data); output.addfile(member, io.BytesIO(data))\n" +
            "    result = extract_snapshot(archive, base / 'snapshot')\n" +
            "    assert verify_snapshot(base / 'snapshot') == result\n" +
            "    (base / 'snapshot/packages/1/1.db').write_bytes(b'changed')\n" +
            "    try: verify_snapshot(base / 'snapshot')\n" +
            "    except ValueError: pass\n" +
            "    else: raise AssertionError('changed source accepted')\n" +
            "    for index, name in enumerate(['../escape', 'packages/1/2.db', 'packages/1/1.db']):\n" +
            "        with tarfile.open(archive, 'w') as output:\n" +
            "            member = tarfile.TarInfo(name)\n" +
            "            if index == 2: member.type = tarfile.SYMTYPE; member.linkname = '/etc/passwd'\n" +
            "            output.addfile(member)\n" +
            "        try: extract_snapshot(archive, base / ('refused-' + str(index)))\n" +
            "        except ValueError: pass\n" +
            "        else: raise AssertionError('unsafe archive accepted')\n" +
            "        assert not (base / ('refused-' + str(index))).exists()\n",
            python.getModule("builtins").callAttr("dict"));
    }
}
