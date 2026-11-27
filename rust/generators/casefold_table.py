"""Write the casefold table the Rust core's `pyos::casefold` reads (`rust/hokace/core/src/pyos.rs`).

The PC engine names a game's receipts folder by ``sha256(str(game.resolve()).casefold())``
(`adaptive.receipt_root`, mirrored by `tools/engine_hooks.game_id`), and `launcher_metadata` matches
launcher entries by a casefolded name. Rust's standard library has no casefold, and its
``char::to_lowercase`` is what ``str.lower()`` gives one character at a time. The table lists every
character whose ``str.casefold()`` differs from ``str.lower()`` in this Python (3.12, Unicode 15.0),
sorted by code point, so the port looks each one up and lower-cases the rest.

    .venv\\Scripts\\python.exe rust\\generators\\casefold_table.py [--check]

``--check`` fails when the committed table is stale.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import unicodedata

OUTPUT = pathlib.Path(__file__).resolve().parents[1] / "hokace" / "core" / "src" / "pyos_casefold.rs"


def render() -> str:
    rows = []
    for code in range(sys.maxunicode + 1):
        char = chr(code)
        folded = char.casefold()
        if folded != char.lower():
            target = "".join(f"\\u{{{ord(c):04X}}}" for c in folded)
            rows.append(f"    ('\\u{{{code:04X}}}', \"{target}\"),")
    head = (
        f"// Generated from CPython {sys.version_info.major}.{sys.version_info.minor} "
        f"(Unicode {unicodedata.unidata_version}): every character whose `str.casefold()` differs from\n"
        "// `str.lower()`, sorted, by `rust/generators/casefold_table.py`.\n\n"
        "const CASEFOLD: &[(char, &str)] = &[\n"
    )
    return head + "\n".join(rows) + "\n];\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the committed table is stale")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != text:
            print(f"{OUTPUT} is stale; re-run without --check", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({text.count(chr(10)) - 5} characters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
