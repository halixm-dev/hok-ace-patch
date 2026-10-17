package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Rebuild from a kept pristine delta and its refusals, on private fixture files; no game operations. */
@RunWith(AndroidJUnit4.class)
public final class PristineDeltaProbeTest {
    @Test public void testRebuildLinkAndRefusals() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root = EngineAssets.INSTANCE.prepare(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python python = Python.getInstance();
        python.getModule("android_bridge").callAttr("diagnostics", root.getPath());
        python.getModule("builtins").callAttr("exec",
            "import shutil, tempfile\n" +
            "from pathlib import Path\n" +
            "import android_bridge, pristine_delta\n" +
            "def fixture(base):\n" +
            "    pristine = {'1/1_0.db': bytes(range(256)) * 64, '1/1.db': b'index' * 100, '2/2_0.db': b'other' * 100}\n" +
            "    staged = {'1/1_0.db': b'EN' * 30 + pristine['1/1_0.db'][60:] + b'appended', '1/1.db': b'INDEX' + pristine['1/1.db'][5:]}\n" +
            "    for folder, files in (('clean', pristine), ('out', staged)):\n" +
            "        for name, data in files.items():\n" +
            "            (base / folder / name).parent.mkdir(parents=True, exist_ok=True); (base / folder / name).write_bytes(data)\n" +
            "    keep = base / 'keep'\n" +
            "    delta = pristine_delta.make(base / 'clean', base / 'out')\n" +
            "    pristine_delta.write(delta, keep / pristine_delta.DELTA_NAME)\n" +
            "    pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, delta.staged_hashes)\n" +
            "    session = base / 'session'; packages = session / 'snapshot' / 'packages'\n" +
            "    shutil.copytree(base / 'clean', packages)\n" +
            "    for name, data in staged.items(): (packages / name).write_bytes(data)\n" +
            "    return pristine, session, keep\n" +
            "with tempfile.TemporaryDirectory() as temporary:\n" +
            "    base = Path(temporary)\n" +
            "    pristine, session, keep = fixture(base)\n" +
            "    before = {name: (session / 'snapshot/packages' / name).read_bytes() for name in pristine}\n" +
            "    restored = android_bridge._restore_pristine(session, keep)\n" +
            "    assert restored['mode'] == 'rebuilt' and sorted(restored['rebuilt']) == ['1/1.db', '1/1_0.db'], restored\n" +
            "    for name in restored['rebuilt']: assert (session / 'pristine' / name).read_bytes() == pristine[name], name\n" +
            "    for name, data in before.items(): assert (session / 'snapshot/packages' / name).read_bytes() == data, 'snapshot changed'\n" +
            "    builtin = session / 'game/WXQ_Data/Package/builtin'\n" +
            "    android_bridge._link_build_input(session, builtin, restored)\n" +
            "    for name, data in pristine.items(): assert (builtin / name).read_bytes() == data, name\n" +
            "    assert builtin.joinpath('2').is_symlink()\n" +
            "with tempfile.TemporaryDirectory() as temporary:\n" +
            "    base = Path(temporary)\n" +
            "    pristine, session, keep = fixture(base)\n" +
            "    target = session / 'snapshot/packages/1/1_0.db'\n" +
            "    data = bytearray(target.read_bytes()); data[100] ^= 1; target.write_bytes(bytes(data))\n" +
            "    try: android_bridge._restore_pristine(session, keep)\n" +
            "    except android_bridge.PatchError as error: assert 'Clear the game' in str(error), error\n" +
            "    else: raise AssertionError('a changed file was rebuilt')\n" +
            "with tempfile.TemporaryDirectory() as temporary:\n" +
            "    base = Path(temporary)\n" +
            "    pristine, session, keep = fixture(base)\n" +
            "    for name, data in pristine.items(): (session / 'snapshot/packages' / name).write_bytes(data + b'v2')\n" +
            "    restored = android_bridge._restore_pristine(session, keep)\n" +
            "    assert restored['mode'] == 'first' and restored['stale'] == 2, restored\n" +
            "    assert not (session / 'pristine').exists()\n" +
            "with tempfile.TemporaryDirectory() as temporary:\n" +
            "    base = Path(temporary)\n" +
            "    pristine, session, keep = fixture(base)\n" +
            "    (keep / pristine_delta.DELTA_NAME).unlink()\n" +
            "    try: android_bridge._restore_pristine(session, keep)\n" +
            "    except android_bridge.PatchError as error: assert 'already translated' in str(error), error\n" +
            "    else: raise AssertionError('a translated layer with no delta was accepted')\n" +
            "    shutil.rmtree(session / 'snapshot/packages'); shutil.copytree(base / 'clean', session / 'snapshot/packages')\n" +
            "    assert android_bridge._restore_pristine(session, keep)['mode'] == 'first'\n",
            python.getModule("builtins").callAttr("dict"));
    }
}
