"""The pixel and byte comparisons ``check_graphics.py`` makes over whole textures.

They are their own package so they can run natively (``rust/pixel-diff-rs``) while the rest of the check
stays Python; where the native module is absent these definitions run as written. Research code: the exe,
the APK and ``tools/`` never import it.
"""
from __future__ import annotations


def mean_abs_diff(left: bytes, right: bytes) -> float:
    """Mean absolute byte difference over the shorter of the two, divided by the length of <left>."""
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def outside_ranges(raw: bytes, new: bytes, ranges: list[tuple[int, int]]) -> int:
    """How many bytes differ between <raw> and <new> outside every half-open (start, end) of <ranges>."""
    return sum(
        1 for index, (before, after) in enumerate(zip(raw, new))
        if before != after and not any(start <= index < end for start, end in ranges)
    )


def sprite_diff(image: bytes, width: int, height: int, box, pixels: bytes) -> float:
    """Mean premultiplied difference between a decoded texture's top-down <box> and <pixels>."""
    x0, y0, x1, y1 = box
    total = count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            at, src = ((height - 1 - y) * width + x) * 4, ((y - y0) * (x1 - x0) + x - x0) * 4
            total += max(
                [abs(image[at + 3] - pixels[src + 3])]
                + [abs(image[at + c] * image[at + 3] - pixels[src + c] * pixels[src + 3]) // 255
                   for c in range(3)])
            count += 1
    return total / count
# >>> rust-anything: mean-abs-diff-rs is on. `rust-anything disable ../../../rust/mean-abs-diff-rs` removes this block.
def _rust_anything_mean_abs_diff_rs():
    import importlib, os, sys
    mode = os.environ.get("RUST_ANYTHING_MODE")
    if mode == "old" or os.environ.get("RUST_ANYTHING_UNIT_MEAN_ABS_DIFF") == "original":
        return
    at = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../rust/mean-abs-diff-rs/python"))
    sys.path.insert(0, at)
    try:
        native = importlib.import_module("mean_abs_diff_rs")
    except ImportError:
        if mode == "new":
            raise
        return
    finally:
        sys.path.remove(at)
    globals().update({name: getattr(native, name) for name in ["mean_abs_diff"]})


_rust_anything_mean_abs_diff_rs()
del _rust_anything_mean_abs_diff_rs
# <<< rust-anything: mean-abs-diff-rs
# >>> rust-anything: outside-ranges-rs is on. `rust-anything disable ../../../rust/outside-ranges-rs` removes this block.
def _rust_anything_outside_ranges_rs():
    import importlib, os, sys
    mode = os.environ.get("RUST_ANYTHING_MODE")
    if mode == "old" or os.environ.get("RUST_ANYTHING_UNIT_OUTSIDE_RANGES") == "original":
        return
    at = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../rust/outside-ranges-rs/python"))
    sys.path.insert(0, at)
    try:
        native = importlib.import_module("outside_ranges_rs")
    except ImportError:
        if mode == "new":
            raise
        return
    finally:
        sys.path.remove(at)
    globals().update({name: getattr(native, name) for name in ["outside_ranges"]})


_rust_anything_outside_ranges_rs()
del _rust_anything_outside_ranges_rs
# <<< rust-anything: outside-ranges-rs
