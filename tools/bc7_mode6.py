"""A small BC7 encoder for the PC edition's regioned atlases (`mobile_graphics.port_atlas`).

The PC edition stores its UI atlases as BC7. A port re-encodes only the 4x4 blocks whose pixels it
changed, so this encodes one block at a time and nothing more. Each block goes first to etcpak's
native BC7 encoder (`etcpak.compress_bc7`); a block it leaves further than `NATIVE_GOOD_ENOUGH` from
its pixels is tried in this module's own modes, cheapest first, and the closest of all is kept:

- **mode 6**: one RGBA line, 7-bit endpoints with a p-bit each, 4-bit indices; colored art;
- **mode 5**: an RGB line and a separate alpha line, 2-bit indices each, 8-bit alpha endpoints;
- **mode 4**: an RGB line with 2-bit indices and an alpha line with 3-bit indices (or the reverse); a
  white or flat label's antialiased edge, where the color barely moves and the alpha does;
- **mode 7**: two RGBA lines split by one of the 64 two-subset partitions; a glyph edge between two
  colors.

The native encoder minimizes plain RGBA error, so it spends precision on the color of nearly
transparent pixels, which the premultiplied measure below ignores; on anti-aliased label edges this
module's modes come closer. Both decode through texture2ddecoder in the checks.

The game's own encoder used modes 4, 5 and 7 for most of the label blocks it wrote (13C19E4E4486B31C,
2026-11-20), so a mode-6-only encoder, which ties alpha to color on one line, cannot reach them: it
missed the Career atlas's English by a mean of 28.8 premultiplied levels. Errors are measured as the
port measures them (`mobile_graphics.BLOCK_MATCH_MEAN`): each pixel's color weighted by its alpha, so
the color of a transparent pixel costs nothing.

The Python modes alone cost about 3.7 ms a block, which made BC7 the slow step of a PC catalog build
(lab notebook, 2026-11-20); etcpak was added for that, and the hand-written modes remain for the
blocks it cannot bring within the match threshold.

Those modes and the search over them run natively (`crates/hok_bc7`, Rust) when that extension
loads; the Python below is the reference they must match byte for byte. Native mode 7 cut a cold PC
catalog build from 80 s to 28 s, and native modes 6, 5 and 4 cut it further (lab notebook,
2026-11-26, "PC BC7 modes 6, 5 and 4 in Rust"). `ENCODER_ENV` requires one backend or the other.

Started from the azydev fork's mode-6 encoder (hok-ace-patcher 1.10.1.3, `tools/bc7_mode6.py`).
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

BLOCK_BYTES = 16
WEIGHTS2 = (0, 21, 43, 64)
WEIGHTS3 = (0, 9, 18, 27, 37, 46, 55, 64)
WEIGHTS = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)  # BC7's 4-bit index weights
REFINE_PASSES = 3  # least-squares endpoint refinements per line
GOOD_ENOUGH = 1.0  # a block this close (mean premultiplied levels) skips the remaining modes
NATIVE_GOOD_ENOUGH = 6.0  # a native block this close is kept: `mobile_graphics.BLOCK_MATCH_MEAN`
NATIVE_UBER_LEVEL = 2  # etcpak's search depth, 0-4; 4 came no closer on the title atlas's hardest blocks
MODE7_TRIES = 4  # mode-7 partitions fitted in full, the best by `_spread` first
# BC7's 64 two-subset partitions (bit i set: pixel i is in subset 1) and the anchor pixel of subset 1.
# Read back from texture2ddecoder's own decoder (2026-11-20); they are the format specification's tables.
PARTITIONS2 = (
    0xCCCC, 0x8888, 0xEEEE, 0xECC8, 0xC880, 0xFEEC, 0xFEC8, 0xEC80, 0xC800, 0xFFEC, 0xFE80, 0xE800,
    0xFFE8, 0xFF00, 0xFFF0, 0xF000, 0xF710, 0x008E, 0x7100, 0x08CE, 0x008C, 0x7310, 0x3100, 0x8CCE,
    0x088C, 0x3110, 0x6666, 0x366C, 0x17E8, 0x0FF0, 0x718E, 0x399C, 0xAAAA, 0xF0F0, 0x5A5A, 0x33CC,
    0x3C3C, 0x55AA, 0x9696, 0xA55A, 0x73CE, 0x13C8, 0x324C, 0x3BDC, 0x6996, 0xC33C, 0x9966, 0x0660,
    0x0272, 0x04E4, 0x4E40, 0x2720, 0xC936, 0x936C, 0x39C6, 0x639C, 0x9336, 0x9CC6, 0x817E, 0xE718,
    0xCCF0, 0x0FCC, 0x7744, 0xEE22,
)
ANCHORS2 = (
    15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 2, 8, 2, 2, 8, 8, 15,
    2, 8, 2, 2, 8, 8, 2, 2, 15, 15, 6, 8, 2, 8, 15, 15, 2, 8, 2, 2, 2, 15, 15, 6,
    6, 2, 6, 8, 15, 15, 2, 2, 15, 15, 15, 15, 15, 2, 2, 15,
)
TRANSPARENT_WEIGHT = 1e-3  # a fully transparent pixel's color still nudges a line, barely
# The hand-written modes' backend: "native" requires the Rust extension (`crates/hok_bc7`), "python"
# forces the reference below; unset, native when it loads, else Python. Checks set it so no fallback
# passes.
ENCODER_ENV = "HOK_BC7_ENCODER"
_BACKEND: dict = {}  # the chosen backend, resolved once by `backend_name`
SEARCH_CALLS = {"native": 0, "python": 0}  # blocks each backend searched past etcpak in this process
MODE7_CALLS = {"native": 0, "python": 0}  # of those, the blocks that reached mode 7

Pixel = tuple[int, int, int, int]
# A quantizer: an endpoint as floats -> (its code for packing, its decoded 8-bit values).
Quantizer = Callable[[list[float]], tuple[object, list[int]]]


def _lerp(low: int, high: int, weight: int) -> int:
    return ((64 - weight) * low + weight * high + 32) >> 6


def _nearest(value: float, bits: int, expand: Callable[[int], int]) -> tuple[int, int]:
    """The <bits>-bit code whose expansion is nearest <value>, and that expansion."""
    top = (1 << bits) - 1
    guess = max(0, min(top, round(value * top / 255)))
    best = min((code for code in (guess - 1, guess, guess + 1) if 0 <= code <= top),
               key=lambda code: abs(expand(code) - value))
    return best, expand(best)


def _quantizer(bits: int) -> Quantizer:
    """Plain <bits>-bit endpoints, expanded by bit replication as the BC7 decoder does."""
    def expand(code: int) -> int:
        code <<= 8 - bits
        return code | (code >> bits)

    def quantize(endpoint: list[float]) -> tuple[object, list[int]]:
        pairs = [_nearest(value, bits, expand) for value in endpoint]
        return [code for code, _ in pairs], [value for _, value in pairs]

    return quantize


def _quantize_pbit(endpoint: list[float]) -> tuple[object, list[int]]:
    """Mode 6's 7-bit values with one shared p-bit, whichever p-bit comes closer."""
    choices = []
    for pbit in (0, 1):
        values = [max(0, min(127, round((value - pbit) / 2))) for value in endpoint]
        actual = [value * 2 + pbit for value in values]
        error = sum((wanted - got) ** 2 for wanted, got in zip(endpoint, actual))
        choices.append((error, values, pbit, actual))
    _, values, pbit, actual = min(choices, key=lambda choice: choice[0])
    return (values, pbit), actual


def _expand6(value: int) -> int:
    return (value << 2) | (value >> 4)


def _quantize_pbit5(endpoint: list[float]) -> tuple[object, list[int]]:
    """Mode 7's 5-bit values with one p-bit, expanded from the 6 bits they make together."""
    choices = []
    for pbit in (0, 1):
        codes, actual = [], []
        for value in endpoint:
            code = min(range(32), key=lambda q: abs(_expand6((q << 1) | pbit) - value))
            codes.append(code)
            actual.append(_expand6((code << 1) | pbit))
        error = sum((wanted - got) ** 2 for wanted, got in zip(endpoint, actual))
        choices.append((error, codes, pbit, actual))
    _, codes, pbit, actual = min(choices, key=lambda choice: choice[0])
    return (codes, pbit), actual


QUANTIZE_5 = _quantizer(5)
QUANTIZE_6 = _quantizer(6)
QUANTIZE_7 = _quantizer(7)
QUANTIZE_8 = _quantizer(8)


def _initial(points: list[list[float]], importance: list[list[float]]) -> tuple[list[float], list[float]]:
    """Endpoints at the ends of the weighted principal axis through <points>."""
    dims = len(points[0])
    weight = [max(row) for row in importance]
    total = sum(weight) or 1.0
    mean = [sum(w * p[c] for w, p in zip(weight, points)) / total for c in range(dims)]
    centred = [[p[c] - mean[c] for c in range(dims)] for p in points]
    cov = [[sum(w * q[i] * q[j] for w, q in zip(weight, centred)) for j in range(dims)] for i in range(dims)]
    axis = [cov[i][i] for i in range(dims)]
    if not any(axis):
        return list(mean), list(mean)
    for _ in range(8):
        axis = [sum(cov[i][j] * axis[j] for j in range(dims)) for i in range(dims)]
        norm = max(abs(value) for value in axis)
        if not norm:
            return list(mean), list(mean)
        axis = [value / norm for value in axis]
    length = sum(value * value for value in axis)
    spans = [sum(q[c] * axis[c] for c in range(dims)) / length
             for q, w in zip(centred, weight) if w > TRANSPARENT_WEIGHT]
    low, high = (min(spans), max(spans)) if spans else (0.0, 0.0)
    return ([max(0.0, min(255.0, mean[c] + axis[c] * low)) for c in range(dims)],
            [max(0.0, min(255.0, mean[c] + axis[c] * high)) for c in range(dims)])


def _assign(points: list[list[float]], importance: list[list[float]], weights: tuple[int, ...],
            low: list[int], high: list[int]) -> tuple[list[int], float]:
    """Each point's nearest palette index between decoded endpoints, and the weighted squared error."""
    dims = len(low)
    palette = [[_lerp(low[c], high[c], weight) for c in range(dims)] for weight in weights]
    indices = []
    total = 0.0
    for point, imp in zip(points, importance):
        best_index, best_error = 0, None
        for index, colour in enumerate(palette):
            error = 0.0
            for c in range(dims):
                delta = colour[c] - point[c]
                error += imp[c] * delta * delta
            if best_error is None or error < best_error:
                best_index, best_error = index, error
        indices.append(best_index)
        total += best_error
    return indices, total


def _refine(points: list[list[float]], importance: list[list[float]], weights: tuple[int, ...],
            indices: list[int]) -> tuple[list[float], list[float]]:
    """Least-squares endpoints for fixed <indices>, channel by channel."""
    dims = len(points[0])
    low, high = [0.0] * dims, [0.0] * dims
    fractions = [weights[index] / 64 for index in indices]
    for c in range(dims):
        aa = ab = bb = ra = rb = mass = moment = 0.0
        for f, point, imp in zip(fractions, points, importance):
            s = imp[c]
            aa += s * (1 - f) ** 2
            ab += s * f * (1 - f)
            bb += s * f * f
            ra += s * (1 - f) * point[c]
            rb += s * f * point[c]
            mass += s
            moment += s * point[c]
        determinant = aa * bb - ab * ab
        if determinant < 1e-9:
            low[c] = high[c] = moment / mass if mass else 0.0
        else:
            low[c] = (ra * bb - rb * ab) / determinant
            high[c] = (rb * aa - ra * ab) / determinant
        low[c], high[c] = max(0.0, min(255.0, low[c])), max(0.0, min(255.0, high[c]))
    return low, high


def _fit(points: list[list[float]], importance: list[list[float]], weights: tuple[int, ...],
         quantize: Quantizer, anchor: int = 0) -> tuple[object, object, list[int], list[int], list[int]]:
    """The best quantized line through <points>: ``(code0, code1, decoded0, decoded1, indices)``.

    The anchor's index (``points[anchor]``) always has its top bit clear, swapping the endpoints if
    needed, because the stream stores it one bit short.
    """
    low, high = _initial(points, importance)
    best = None
    for _ in range(REFINE_PASSES + 1):
        (code0, decoded0), (code1, decoded1) = quantize(low), quantize(high)
        indices, error = _assign(points, importance, weights, decoded0, decoded1)
        if best is None or error < best[0]:
            best = (error, code0, code1, decoded0, decoded1, indices)
        low, high = _refine(points, importance, weights, indices)
    _error, code0, code1, decoded0, decoded1, indices = best
    top = len(weights) - 1
    if indices[anchor] > top // 2:
        code0, code1, decoded0, decoded1 = code1, code0, decoded1, decoded0
        indices = [top - index for index in indices]
    return code0, code1, decoded0, decoded1, indices


class _Bits:
    """BC7's bit stream: fields written least significant bit first."""

    def __init__(self) -> None:
        self.value = self.position = 0

    def write(self, value: int, width: int) -> None:
        self.value |= value << self.position
        self.position += width

    def indices(self, indices: list[int], width: int, anchors: tuple[int, ...] = (0,)) -> None:
        for i, index in enumerate(indices):
            self.write(index, width - 1 if i in anchors else width)

    def bytes(self) -> bytes:
        assert self.position == 128
        return self.value.to_bytes(BLOCK_BYTES, "little")


def mismatch(pixels: list[Pixel], decoded: list[tuple[int, ...]]) -> float:
    """Mean premultiplied difference, as `block_scan.block_mismatch` measures a block."""
    total = 0
    for (r, g, b, a), (dr, dg, db, da) in zip(pixels, decoded):
        total += max(abs(a - da), abs(r * a - dr * da) // 255, abs(g * a - dg * da) // 255,
                     abs(b * a - db * da) // 255)
    return total / 16


def _importance(pixels: list[Pixel]) -> tuple[list[list[float]], list[list[float]]]:
    """Per-pixel weights for the color channels (alpha squared) and for alpha (one)."""
    colour = [[max(TRANSPARENT_WEIGHT, (p[3] / 255) ** 2)] * 3 for p in pixels]
    return colour, [[1.0] for _ in pixels]


def _mode6(pixels: list[Pixel]) -> tuple[bytes, list[tuple[int, ...]]]:
    colour, alpha = _importance(pixels)
    points = [list(map(float, p)) for p in pixels]
    importance = [c + a for c, a in zip(colour, alpha)]
    (values0, pbit0), (values1, pbit1), low, high, indices = _fit(points, importance, WEIGHTS, _quantize_pbit)
    bits = _Bits()
    bits.write(1 << 6, 7)
    for channel in range(4):
        bits.write(values0[channel], 7)
        bits.write(values1[channel], 7)
    bits.write(pbit0, 1)
    bits.write(pbit1, 1)
    bits.indices(indices, 4)
    decoded = [tuple(_lerp(low[c], high[c], WEIGHTS[i]) for c in range(4)) for i in indices]
    return bits.bytes(), decoded


def _separate(pixels: list[Pixel], mode: int, index_mode: int = 0) -> tuple[bytes, list[tuple[int, ...]]]:
    """Mode 5 or mode 4: an RGB line and an alpha line, rotation 0.

    Mode 4's <index_mode> 0 gives the color 2-bit indices and the alpha 3-bit ones; 1 the reverse.
    """
    colour, alpha = _importance(pixels)
    rgb = [[float(c) for c in p[:3]] for p in pixels]
    alphas = [[float(p[3])] for p in pixels]
    if mode == 5:
        colour_weights, alpha_weights, colour_q, alpha_q, colour_bits, alpha_bits = (
            WEIGHTS2, WEIGHTS2, QUANTIZE_7, QUANTIZE_8, 7, 8)
    else:
        colour_weights, alpha_weights = (WEIGHTS2, WEIGHTS3) if index_mode == 0 else (WEIGHTS3, WEIGHTS2)
        colour_q, alpha_q, colour_bits, alpha_bits = QUANTIZE_5, QUANTIZE_6, 5, 6
    c0, c1, clow, chigh, cidx = _fit(rgb, colour, colour_weights, colour_q)
    a0, a1, alow, ahigh, aidx = _fit(alphas, alpha, alpha_weights, alpha_q)
    bits = _Bits()
    bits.write(1 << mode, mode + 1)
    bits.write(0, 2)  # rotation: none
    if mode == 4:
        bits.write(index_mode, 1)
    for channel in range(3):
        bits.write(c0[channel], colour_bits)
        bits.write(c1[channel], colour_bits)
    bits.write(a0[0], alpha_bits)
    bits.write(a1[0], alpha_bits)
    # The 2-bit index set comes first in the stream, whichever channel it belongs to.
    if colour_weights is WEIGHTS2:
        bits.indices(cidx, 2)
        bits.indices(aidx, 2 if alpha_weights is WEIGHTS2 else 3)
    else:
        bits.indices(aidx, 2)
        bits.indices(cidx, 3)
    decoded = [tuple(_lerp(clow[c], chigh[c], colour_weights[ci]) for c in range(3))
               + (_lerp(alow[0], ahigh[0], alpha_weights[ai]),) for ci, ai in zip(cidx, aidx)]
    return bits.bytes(), decoded


def _spread(pixels: list[Pixel], members: list[int], importance: list[list[float]]) -> float:
    """Weighted squared spread of <members> around their mean: a cheap guess at a subset's error."""
    total = 0.0
    for c in range(4):
        mass = sum(importance[i][c] for i in members)
        if not mass:
            continue
        mean = sum(importance[i][c] * pixels[i][c] for i in members) / mass
        total += sum(importance[i][c] * (pixels[i][c] - mean) ** 2 for i in members)
    return total


def _mode7_python(pixels: list[Pixel]) -> tuple[bytes, list[tuple[int, ...]]]:
    """Two RGBA lines, split by the best of the 64 two-subset partitions; 2-bit indices.

    The reference for the native port (`crates/hok_bc7`), which must give the same bytes.
    """
    colour, alpha = _importance(pixels)
    importance = [c + a for c, a in zip(colour, alpha)]
    subsets = [([i for i in range(16) if not mask >> i & 1], [i for i in range(16) if mask >> i & 1])
               for mask in PARTITIONS2]
    ranked = sorted(range(64), key=lambda p: _spread(pixels, subsets[p][0], importance)
                    + _spread(pixels, subsets[p][1], importance))
    best = None
    for partition in ranked[:MODE7_TRIES]:
        decoded: list = [None] * 16
        indices = [0] * 16
        lines = []
        for members, anchor in zip(subsets[partition], (0, ANCHORS2[partition])):
            points = [list(map(float, pixels[i])) for i in members]
            code0, code1, low, high, found = _fit(points, [importance[i] for i in members], WEIGHTS2,
                                                  _quantize_pbit5, members.index(anchor))
            lines.append((code0, code1))
            for i, index in zip(members, found):
                indices[i] = index
                decoded[i] = tuple(_lerp(low[c], high[c], WEIGHTS2[index]) for c in range(4))
        error = mismatch(pixels, decoded)
        if best is None or error < best[0]:
            best = (error, partition, lines, indices, decoded)
    _error, partition, lines, indices, decoded = best
    bits = _Bits()
    bits.write(1 << 7, 8)
    bits.write(partition, 6)
    endpoints = [lines[0][0], lines[0][1], lines[1][0], lines[1][1]]
    for channel in range(4):
        for codes, _pbit in endpoints:
            bits.write(codes[channel], 5)
    for _codes, pbit in endpoints:
        bits.write(pbit, 1)
    bits.indices(indices, 2, (0, ANCHORS2[partition]))
    return bits.bytes(), decoded


def _load_native():
    """The native encoder module (`hok_bc7`), or None when it is not built.

    Frozen, it ships beside the other modules. From source it is imported when on the path, else
    read from `build/native/hok_bc7.pyd`, where `app/build_exe.py` puts it. A build older than the
    native search (mode 7 alone) counts as not built.
    """
    try:
        import hok_bc7
        return hok_bc7 if hasattr(hok_bc7, "encode_search") else None
    except ImportError:
        pass
    if getattr(sys, "frozen", False):
        return None
    built = Path(__file__).resolve().parents[1] / "build" / "native" / "hok_bc7.pyd"
    if not built.is_file():
        return None
    from importlib.machinery import ExtensionFileLoader
    from importlib.util import module_from_spec, spec_from_loader

    loader = ExtensionFileLoader("hok_bc7", str(built))
    module = module_from_spec(spec_from_loader("hok_bc7", loader))
    loader.exec_module(module)
    if not hasattr(module, "encode_search"):
        return None
    sys.modules["hok_bc7"] = module
    return module


def _python_mode_bytes(rgba: bytes, mode: int, index_mode: int = 0) -> tuple[bytes, bytes]:
    if len(rgba) != 64:
        raise ValueError(f"a BC7 block needs 64 RGBA bytes, got {len(rgba)}")
    if mode not in (4, 5, 6, 7) or index_mode not in (0, 1) or (index_mode and mode != 4):
        raise ValueError(f"no BC7 mode {mode} with index mode {index_mode}")
    pixels = [tuple(rgba[i:i + 4]) for i in range(0, 64, 4)]
    if mode == 6:
        block, decoded = _mode6(pixels)
    elif mode in (4, 5):
        block, decoded = _separate(pixels, mode, index_mode)
    else:
        block, decoded = _mode7_python(pixels)
    return block, bytes(c for pixel in decoded for c in pixel)


def mode_backend(name: str | None = None) -> Callable[..., tuple[bytes, bytes]]:
    """``encode_mode(rgba, mode, index_mode=0) -> (block, decoded RGBA)`` for <name>.

    <name> is ``native`` or ``python``; with none, the backend `ENCODER_ENV` selects. ``native``
    raises when the extension is absent, so a check that names it never passes on the fallback.
    """
    name = name or backend_name()
    if name == "python":
        return _python_mode_bytes
    if name != "native":
        raise ValueError(f"unknown BC7 encoder backend {name!r}")
    module = _load_native()
    if module is None:
        raise RuntimeError("the native BC7 encoder (hok_bc7) is not built")
    return module.encode_mode


def mode7_backend(name: str | None = None) -> Callable[[bytes], bytes]:
    """Mode 7 alone as ``encode_mode7(rgba: bytes) -> bytes`` for <name>, as `mode_backend`."""
    encode = mode_backend(name)
    return lambda rgba: encode(rgba, 7)[0]


def backend_name() -> str:
    """The backend `encode_block` searches with, chosen once: `ENCODER_ENV` if set, else native
    when it loads."""
    if not _BACKEND:
        wanted = os.environ.get(ENCODER_ENV, "").strip().lower()
        if wanted not in ("", "native", "python"):
            raise ValueError(f"{ENCODER_ENV}={wanted!r}: expected native or python")
        if wanted == "python" or (not wanted and _load_native() is None):
            _BACKEND["name"], _BACKEND["module"] = "python", None
        else:
            mode_backend("native")  # raises when the extension is absent
            _BACKEND["name"], _BACKEND["module"] = "native", _load_native()
    return _BACKEND["name"]


def _mode7(pixels: list[Pixel]) -> tuple[bytes, list[tuple[int, ...]]]:
    """The Python search's mode 7, counted."""
    MODE7_CALLS["python"] += 1
    return _mode7_python(pixels)


def _mode5(pixels: list[Pixel]) -> tuple[bytes, list[tuple[int, ...]]]:
    return _separate(pixels, 5)


def _mode4(pixels: list[Pixel]) -> tuple[bytes, list[tuple[int, ...]]]:
    return _separate(pixels, 4, 0)


def _mode4_colour3(pixels: list[Pixel]) -> tuple[bytes, list[tuple[int, ...]]]:
    return _separate(pixels, 4, 1)


# Cheapest first; `encode_block` stops at the first that comes within GOOD_ENOUGH. The native
# search (`hok_bc7.encode_search`) runs the same order.
ENCODERS = (_mode6, _mode5, _mode4, _mode4_colour3, _mode7)


def _params():
    import etcpak

    params = etcpak.BC7CompressBlockParams()
    params.m_uber_level = NATIVE_UBER_LEVEL
    return params


_NATIVE_PARAMS: list = []  # etcpak's settings, made once


def _native(pixels: list[Pixel]) -> bytes:
    """etcpak's BC7 block for the 16 RGBA pixels (RGBA in, row order kept, measured 2026-11-20)."""
    import etcpak

    if not _NATIVE_PARAMS:
        _NATIVE_PARAMS.append(_params())
    return etcpak.compress_bc7(bytes(c for pixel in pixels for c in pixel), 4, 4, _NATIVE_PARAMS[0])


def _decode(block: bytes) -> list[tuple[int, ...]]:
    """The block's 16 RGBA pixels as texture2ddecoder (BGRA out) reads them.

    Not etcpak's own `decompress_bc7`: in 0.9.15 it raised MemoryError or crashed the process on a
    single 4x4 block (2026-11-20).
    """
    import texture2ddecoder

    raw = texture2ddecoder.decode_bc7(block, 4, 4)
    return [(raw[i + 2], raw[i + 1], raw[i], raw[i + 3]) for i in range(0, 64, 4)]


def encode_block(pixels: list[Pixel]) -> bytes:
    """One BC7 block for 16 RGBA pixels in row order (the texture's own row order)."""
    if len(pixels) != 16:
        raise ValueError("BC7 block needs 16 RGBA pixels")
    native = _native(pixels)
    best = (mismatch(pixels, _decode(native)), native)
    if best[0] <= NATIVE_GOOD_ENOUGH:
        return native
    name = backend_name()
    SEARCH_CALLS[name] += 1
    if name == "native":
        found, tried = _BACKEND["module"].encode_search(bytes(c for pixel in pixels for c in pixel), best[0])
        if tried == len(ENCODERS):
            MODE7_CALLS["native"] += 1
        return native if found is None else found
    for encode in ENCODERS:
        block, decoded = encode(pixels)
        error = mismatch(pixels, decoded)
        if best is None or error < best[0]:
            best = (error, block)
        if best[0] <= GOOD_ENOUGH:
            break
    return best[1]
