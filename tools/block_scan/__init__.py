"""Which 4x4 blocks of a decoded atlas no longer show their target: the scan before a re-encode.

``mobile_graphics._reencode`` asks it once per atlas, over every block the edit touched. It is its own
package so the scan can run natively (``rust/stale_blocks-rs``) while the rest of ``tools/`` stays Python;
where the native module is absent (source runs, the Android app) these definitions run as written.
"""
from __future__ import annotations


def premultiplied_diff(left: bytes | bytearray, right: bytes | bytearray, at: int) -> int:
    """Largest channel difference between two RGBA pixels once each is weighted by its own alpha."""
    la, ra = left[at + 3], right[at + 3]
    worst = abs(la - ra)
    for channel in range(3):
        worst = max(worst, abs(left[at + channel] * la - right[at + channel] * ra) // 255)
    return worst


def block_mismatch(target: bytes | bytearray, device: bytes, decided: bytes | bytearray, block: int,
                   blocks_x: int, width: int) -> float:
    """Mean premultiplied difference between target and device over a block's decided pixels."""
    raw_row, column = (block // blocks_x) * 4, (block % blocks_x) * 4
    total = count = 0
    for row in range(raw_row, raw_row + 4):
        for x in range(column, column + 4):
            if decided[row * width + x]:
                total += premultiplied_diff(target, device, (row * width + x) * 4)
                count += 1
    return total / count if count else 0.0


def stale_blocks(target: bytes, device: bytes, decided: bytes, blocks: list[int], width: int,
                 threshold: float) -> list[int]:
    """The <blocks>, in order, whose decided pixels differ from <device> by more than <threshold> on average.

    <target> and <device> are bottom-up RGBA8 of one <width>-pixel-wide image, <decided> one byte per pixel
    (non-zero where the target was drawn), <blocks> raw-order 4x4 block indices.
    """
    blocks_x = width // 4
    return [block for block in blocks
            if block_mismatch(target, device, decided, block, blocks_x, width) > threshold]
# >>> rust-anything: stale-blocks-rs is on. `rust-anything disable ../../rust/stale-blocks-rs` removes this block.
def _rust_anything_stale_blocks_rs():
    import importlib, os, sys
    mode = os.environ.get("RUST_ANYTHING_MODE")
    if mode == "old" or os.environ.get("RUST_ANYTHING_UNIT_STALE_BLOCKS") == "original":
        return
    at = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../rust/stale-blocks-rs/python"))
    sys.path.insert(0, at)
    try:
        native = importlib.import_module("stale_blocks_rs")
    except ImportError:
        if mode == "new":
            raise
        return
    finally:
        sys.path.remove(at)
    globals().update({name: getattr(native, name) for name in ["stale_blocks"]})


_rust_anything_stale_blocks_rs()
del _rust_anything_stale_blocks_rs
# <<< rust-anything: stale-blocks-rs
