"""Check exact-input reuse at the real encode_astc/native-compressor boundary."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import mobile_graphics as graphics


class AstcReuse(unittest.TestCase):
    def setUp(self) -> None:
        self.clear()
        self.addCleanup(self.clear)
        self.context = Mock()
        self.context.compress.return_value = b"encoded"
        context_patch = patch.object(graphics, "_context", return_value=self.context)
        context_patch.start()
        self.addCleanup(context_patch.stop)

    @staticmethod
    def clear() -> None:
        cached = getattr(graphics, "_encode_astc_cached", None)
        if cached:
            cached.cache_clear()

    def encode(self, pixels: bytes = bytes(256), width: int = 8, height: int = 8,
               bx: int = 4, by: int = 4) -> bytes:
        return graphics.encode_astc(pixels, width, height, bx, by)

    def test_identical_inputs_encode_once(self) -> None:
        first = self.encode()
        self.assertEqual(self.encode(), first)
        self.assertEqual(self.context.compress.call_count, 1)

    def test_changed_pixels_are_encoded(self) -> None:
        self.encode()
        self.encode(bytes([1]) + bytes(255))
        self.assertEqual(self.context.compress.call_count, 2)

    def test_changed_geometry_is_encoded(self) -> None:
        self.encode()
        self.encode(width=16, height=4)
        self.assertEqual(self.context.compress.call_count, 2)

    def test_changed_footprint_is_encoded(self) -> None:
        self.encode()
        self.encode(bx=8, by=8)
        self.assertEqual(self.context.compress.call_count, 2)

    def test_large_images_are_not_retained(self) -> None:
        pixels = bytes(1024 * 1024)
        self.encode(pixels, 512, 512)
        self.encode(pixels, 512, 512)
        self.assertEqual(self.context.compress.call_count, 2)

    def test_small_input_limit(self) -> None:
        self.encode(bytes(4096), 32, 32)
        self.encode(bytes(4096), 32, 32)
        self.encode(bytes(8192), 64, 32)
        self.encode(bytes(8192), 64, 32)
        self.assertEqual(self.context.compress.call_count, 3)

    def test_failure_is_not_cached(self) -> None:
        self.context.compress.side_effect = [RuntimeError("encode failed"), b"retry"]
        with self.assertRaisesRegex(RuntimeError, "encode failed"):
            self.encode()
        self.assertEqual(self.encode(), b"retry")
        self.assertEqual(self.context.compress.call_count, 2)

    def test_cache_evicts_old_inputs(self) -> None:
        self.encode()
        for number in range(1, 1025):
            self.encode(number.to_bytes(4, "little") + bytes(252))
        before = self.context.compress.call_count
        self.assertEqual(graphics._encode_astc_cached.cache_info().currsize, graphics.ASTC_CACHE_ENTRIES)
        self.encode()
        self.assertEqual(self.context.compress.call_count, before + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
