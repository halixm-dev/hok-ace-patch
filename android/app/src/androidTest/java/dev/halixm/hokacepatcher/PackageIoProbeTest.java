package dev.halixm.hokacepatcher;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Exercise packaged optimizations on tiny app-private fixtures; never access the game. */
@RunWith(AndroidJUnit4.class)
public final class PackageIoProbeTest {
    private JSONObject run(String script) throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String root = EngineAssets.INSTANCE.prepare(context).getAbsolutePath();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python python = Python.getInstance();
        python.getModule("android_bridge").callAttr("engine_preflight", root);
        PyObject builtins = python.getModule("builtins");
        PyObject scope = builtins.callAttr("dict");
        scope.callAttr("__setitem__", "scratch_root", context.getCacheDir().getAbsolutePath());
        builtins.callAttr("exec", script, scope);
        String report = scope.callAttr("__getitem__", "result_json").toString();
        android.util.Log.i("HokAceProbe", report);
        return new JSONObject(report);
    }

    @Test public void testChangedRegionWritesAndRootSplit() throws Exception {
        JSONObject result = run("""
            import json, struct, tempfile
            from pathlib import Path
            from unittest.mock import patch
            from qts_relocate import Shard, FILE_GROWTH, btree_offsets, _read_btree_offsets

            with tempfile.TemporaryDirectory(dir=scratch_root, prefix='package-io-') as folder:
                path = Path(folder) / '1_0.db'
                size = 4 * 1024 * 1024
                data = bytearray(size)
                struct.pack_into('<II', data, 8, size, size)
                struct.pack_into('<I', data, 0x10, 0x1000)
                struct.pack_into('<I', data, 0x18, 0x3000)
                struct.pack_into('<II', data, 0x30, 0x8000, 0x1000)
                struct.pack_into('<6I', data, 0x8000, 0x20, 1, 1, 1, 0, 0x20)
                struct.pack_into('<6I', data, 0x8018, 0x1000, 0x2000, 0x1000, 0, 0, 0)
                struct.pack_into('<4I', data, 0x2ff0, 0x1000, 0, 0xffffffff, 3 << 16)
                path.write_bytes(data)
                shard = Shard(path)
                assert shard.data == data
                shard.data[-1] = 19
                original_open = Path.open
                writes = []
                class CountedFile:
                    def __init__(self, handle): self.handle = handle
                    def __enter__(self):
                        self.handle.__enter__()
                        return self
                    def __exit__(self, *args): return self.handle.__exit__(*args)
                    def __getattr__(self, name): return getattr(self.handle, name)
                    def write(self, value):
                        count = self.handle.write(value)
                        writes.append(count)
                        return count
                def counted_open(path, *args, **kwargs):
                    return CountedFile(original_open(path, *args, **kwargs))
                with patch.object(Path, 'open', counted_open):
                    shard.save()
                    first_write = sum(writes)
                    writes.clear()
                    shard.save()
                    repeat_write = sum(writes)
                assert first_write == 65536, first_write
                assert repeat_write == 0, repeat_write
                assert path.read_bytes() == shard.data
                offsets = {}
                for key in range(1, 601):
                    record = struct.pack('<IiIQ', 0, -1, 32, key) + bytes(12)
                    offsets[key] = {shard.append_record(record, key)}
                expected_size = max(size, (shard.data_end + FILE_GROWTH - 1) // FILE_GROWTH * FILE_GROWTH)
                expected = bytearray(shard.data)
                expected.extend(bytes(max(0, expected_size - len(expected))))
                struct.pack_into('<II', expected, 8, shard.data_end, expected_size)
                shard.save()
                assert path.read_bytes() == expected
                assert btree_offsets(Shard(path)) == offsets
                assert _read_btree_offsets(path) == offsets
                shard.data.extend(b'views released')
                result_json = json.dumps({'first_write_bytes': first_write,
                    'repeat_write_bytes': repeat_write, 'btree_keys': len(offsets),
                    'legacy_bytes_equal': True, 'scratch_only': True})
            """);
        assertEquals(65536, result.getInt("first_write_bytes"));
        assertEquals(0, result.getInt("repeat_write_bytes"));
        assertEquals(600, result.getInt("btree_keys"));
        assertTrue(result.getBoolean("legacy_bytes_equal"));
    }

    @Test public void testSmallAstcReuseMatchesNative() throws Exception {
        JSONObject result = run("""
            import hashlib, json
            import mobile_graphics as graphics
            rgba = bytes((7, 38, 69, 255)) * (16 * 16)
            graphics._encode_astc_cached.cache_clear()
            first = graphics.encode_astc(rgba, 16, 16, 4, 4)
            second = graphics.encode_astc(rgba, 16, 16, 4, 4)
            native = graphics._encode_astc(rgba, 16, 16, 4, 4)
            assert first == second == native
            info = graphics._encode_astc_cached.cache_info()
            assert info.hits == 1 and info.misses == 1
            graphics._encode_astc_cached.cache_clear()
            result_json = json.dumps({'cache_hits': info.hits, 'cache_misses': info.misses,
                'same_native_bytes': True, 'sha256': hashlib.sha256(first).hexdigest()})
            """);
        assertEquals(1, result.getInt("cache_hits"));
        assertTrue(result.getBoolean("same_native_bytes"));
    }
}
