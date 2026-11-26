"""Check the PC edition's two BC7 encoder backends against each other, from source; no game needed.

Run from the project root after `app\\build_exe.py --native-only` (or `build.bat`):

    .venv\\Scripts\\python.exe tools\\research\\check_bc7_native.py [--blocks 400]

Fails unless all of these hold:

- with the extension hidden, the backend resolves to Python, `encode_block` still reaches mode 7 on
  the smoke test's fixture and gives its bytes, and naming ``native`` (`HOK_BC7_ENCODER`) raises;
- with the extension, native and Python give the same bytes and decoded pixels in every
  hand-written mode (6, 5, 4 with each index mode, 7) on the fixture, the hand-made cases and
  <blocks> seeded random blocks (`bc7_corpus._synthetic_inputs`), and `encode_block` gives the
  same bytes through each backend;
- both backends refuse an input that is not 64 bytes with ValueError, and native refuses a mode it
  does not have.

The game's own blocks are checked by `bc7_corpus.py replay --backend native --final`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bc7_mode6  # noqa: E402
from bc7_corpus import MODES, _synthetic_inputs  # noqa: E402


def _fixture() -> tuple[bytes, bytes]:
    source = (ROOT / "app" / "hok_patcher.py").read_text(encoding="utf-8")
    block = source[source.index("MODE7_FIXTURE = ("):]
    block = block[:block.index("\n)\n") + 3]
    scope: dict = {}
    exec(block, scope)  # noqa: S102 - two bytes.fromhex literals from this repo's own source
    return scope["MODE7_FIXTURE"]


def _reset(name: str | None = None) -> None:
    bc7_mode6._BACKEND.clear()
    for counter in (bc7_mode6.SEARCH_CALLS, bc7_mode6.MODE7_CALLS):
        for key in counter:
            counter[key] = 0
    if name is None:
        os.environ.pop(bc7_mode6.ENCODER_ENV, None)
    else:
        os.environ[bc7_mode6.ENCODER_ENV] = name


def _pixels(raw: bytes):
    return [tuple(raw[i:i + 4]) for i in range(0, 64, 4)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--blocks", type=int, default=400)
    args = parser.parse_args()
    failures: list[str] = []
    raw, expected = _fixture()

    # Without the extension: the Python fallback, and no silent fallback when native is named.
    loader = bc7_mode6._load_native
    bc7_mode6._load_native = lambda: None
    try:
        _reset()
        if bc7_mode6.backend_name() != "python":
            failures.append("absent extension: backend is not python")
        if bc7_mode6.encode_block(_pixels(raw)) != expected or bc7_mode6.MODE7_CALLS["python"] != 1:
            failures.append("absent extension: encode_block did not reach Python mode 7 with the fixture's bytes")
        _reset("native")
        try:
            bc7_mode6.backend_name()
            failures.append("absent extension: HOK_BC7_ENCODER=native did not raise")
        except RuntimeError:
            pass
    finally:
        bc7_mode6._load_native = loader
    print("absent extension: Python fallback" + (" FAILED" if failures else " ok"))

    # With the extension: byte parity in each mode, and through encode_block.
    _reset("native")
    if bc7_mode6.backend_name() != "native":
        failures.append("the native extension did not load (build it with app\\build_exe.py --native-only)")
        print("\n".join(failures))
        return 1
    native, python = bc7_mode6.mode_backend("native"), bc7_mode6.mode_backend("python")
    inputs = [raw] + _synthetic_inputs(random_blocks=args.blocks)
    for mode, index_mode in MODES:
        for n, block in enumerate(inputs):
            got, want = native(block, mode, index_mode), python(block, mode, index_mode)
            if got != want:
                part = "bytes" if got[0] != want[0] else "decoded pixels"
                failures.append(f"mode {mode}/{index_mode} {part} differ on input {n} {block.hex()}: "
                                f"{want[0].hex()} vs {got[0].hex()}")
                break
    finals = {}
    for name in ("native", "python"):
        _reset(name)
        finals[name] = [bc7_mode6.encode_block(_pixels(block)) for block in inputs]
        print(f"encode_block via {name}: searched {bc7_mode6.SEARCH_CALLS}, mode 7 {bc7_mode6.MODE7_CALLS}")
    if finals["native"] != finals["python"]:
        failures.append("encode_block differs between backends")
    if finals["native"][0] != expected:
        failures.append("encode_block does not give the fixture's bytes")
    for name, encode in (("native", native), ("python", python)):
        for size in (0, 63, 65):
            try:
                encode(bytes(size), 6)
                failures.append(f"{name}: {size} bytes accepted")
            except ValueError:
                pass
    for mode, index_mode in ((3, 0), (8, 0), (6, 1), (4, 2)):
        try:
            native(bytes(64), mode, index_mode)
            failures.append(f"native: mode {mode}/{index_mode} accepted")
        except ValueError:
            pass
    _reset()
    print(f"{len(inputs)} blocks x {len(MODES)} modes: " + ("PASS" if not failures else "FAIL"))
    for failure in failures:
        print("  " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
