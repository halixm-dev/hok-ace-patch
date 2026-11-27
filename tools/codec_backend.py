"""Use the Rust compression and image codecs when their extension is available."""
from __future__ import annotations

import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_native():
    try:
        import hok_codecs
    except ImportError:
        path = Path(__file__).resolve().parents[1] / "build" / "native" / "hok_codecs.pyd"
        if sys.platform != "win32" or getattr(sys, "frozen", False) or not path.is_file():
            return None
        try:
            spec = spec_from_file_location("hok_codecs", path)
            hok_codecs = module_from_spec(spec)
            spec.loader.exec_module(hok_codecs)
        except ImportError:
            return None
        sys.modules["hok_codecs"] = hok_codecs
    return hok_codecs


_MODE = os.environ.get("HOK_CODECS", "")
_NATIVE = None if _MODE == "python" else _load_native()
if _MODE == "native" and _NATIVE is None:
    raise RuntimeError("the native codecs (hok_codecs) are not built")


def backend_name() -> str:
    return "native" if _NATIVE is not None else "python"


def _native_call(name: str, *args: bytes | int):
    if _NATIVE is not None:
        try:
            return getattr(_NATIVE, name)(*args)
        except (ValueError, OverflowError):
            if _MODE == "native":
                raise
    return None


def lz4_decompress(data: bytes, uncompressed_size: int) -> bytes:
    native = _native_call("lz4_decompress", data, uncompressed_size)
    if native is not None:
        return native
    import lz4.block

    return lz4.block.decompress(data, uncompressed_size=uncompressed_size)


def lz4_compress(data: bytes) -> bytes:
    native = _native_call("lz4_compress", data)
    if native is not None:
        return native
    import lz4.block

    return lz4.block.compress(data, mode="high_compression", compression=12, store_size=False)


def zstd_decompress(data: bytes, max_output_size: int) -> bytes:
    native = _native_call("zstd_decompress", data, max_output_size)
    if native is not None:
        return native
    import zstandard

    return zstandard.ZstdDecompressor().decompress(data, max_output_size=max_output_size)


def oodle_decompress(data: bytes, size: int) -> bytes:
    native = _native_call("oodle_decompress", data, size)
    if native is not None:
        return native
    import ooz

    return ooz.decompress(data, size)


def oodle_stored(data: bytes, decoder_type: int) -> bytes:
    if decoder_type == 0x0C:
        native = _native_call("oodle_stored", data)
        if native is not None:
            return native
    return b"".join(bytes((0xCC, decoder_type)) + data[i:i + 0x40000]
                    for i in range(0, len(data), 0x40000))


def _bgra_to_rgba(data: bytes) -> bytes:
    buf = bytearray(data)
    buf[0::4], buf[2::4] = buf[2::4], buf[0::4]
    return bytes(buf)


def decode_astc(data: bytes, width: int, height: int, bx: int, by: int) -> bytes:
    native = _native_call("decode_astc", data, width, height, bx, by)
    if native is not None:
        return native
    import texture2ddecoder

    return _bgra_to_rgba(texture2ddecoder.decode_astc(data, width, height, bx, by))


def decode_bc7(data: bytes, width: int, height: int) -> bytes:
    native = _native_call("decode_bc7", data, width, height)
    if native is not None:
        return native
    import texture2ddecoder

    return _bgra_to_rgba(texture2ddecoder.decode_bc7(data, width, height))


def encode_bc7(data: bytes) -> tuple[bytes, int] | None:
    """Return the Rust block and number of search modes tried when available."""
    return _native_call("encode_bc7", data)


def png_pixels(path: Path, size: tuple[int, int]) -> bytes | None:
    """Read RGBA pixels when the artwork has the expected dimensions."""
    if _NATIVE is not None:
        data = path.read_bytes()
        # Pillow applies different conversion rules to 16-bit grayscale.
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 29 and data[24] < 16:
            try:
                width, height, pixels = _NATIVE.decode_png(data)
            except ValueError:
                if _MODE == "native":
                    raise
            else:
                return pixels if (width, height) == size else None
    from PIL import Image

    with Image.open(path) as image:
        if image.size == size:
            return image.convert("RGBA").tobytes()
    return None
