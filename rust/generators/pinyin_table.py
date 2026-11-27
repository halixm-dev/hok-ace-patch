"""Write the pinyin table the Rust core romanises names with (`rust/DECISIONS.md`, ADR-014).

``tools/extra_text.pinyin_name`` romanises a run of Chinese with
``lazy_pinyin(run, style=Style.NORMAL, v_to_u=True)``. That call splits the run into the longest
phrases pypinyin's phrase dictionary knows (its mmseg cut) and reads each phrase, or each remaining
character, in NORMAL style. The table holds both dictionaries already in that style, read back through
``lazy_pinyin`` itself, so the Rust port needs only the cut and a lookup:

    C<TAB><character><TAB><syllable>
    P<TAB><phrase><TAB><syllable> <syllable> ...

Lines are sorted, the file is gzip'd with no timestamp, and the first line names the pypinyin version,
so the output is the same bytes on every run. Re-run after every pypinyin bump; ``--check`` fails when
the committed table is stale.

    .venv\\Scripts\\python.exe rust\\generators\\pinyin_table.py [--check]
"""
from __future__ import annotations

import argparse
import gzip
import io
import pathlib
import sys

import pypinyin
from pypinyin import Style, lazy_pinyin
from pypinyin.phrases_dict import phrases_dict
from pypinyin.pinyin_dict import pinyin_dict

ROOT = pathlib.Path(__file__).resolve().parents[2]
TABLE = ROOT / "rust" / "hokace" / "core" / "data" / "pinyin.tsv.gz"


def _read(text: str) -> list[str]:
    return lazy_pinyin(text, style=Style.NORMAL, v_to_u=True)


def table_bytes() -> bytes:
    lines = []
    for code in pinyin_dict:
        character = chr(code)
        syllables = _read(character)
        if len(syllables) != 1 or "\t" in syllables[0] or " " in syllables[0]:
            raise ValueError(f"U+{code:04X} reads as {syllables!r}, not one syllable")
        lines.append(f"C\t{character}\t{syllables[0]}")
    for phrase in phrases_dict:
        syllables = _read(phrase)
        if len(syllables) != len(phrase) or any(" " in s or "\t" in s for s in syllables):
            raise ValueError(f"{phrase!r} reads as {syllables!r}, not one syllable per character")
        lines.append(f"P\t{phrase}\t{' '.join(syllables)}")
    text = f"# pypinyin {pypinyin.__version__}, Style.NORMAL, v_to_u=True\n" + "\n".join(sorted(lines)) + "\n"
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="", compresslevel=9) as packed:
        packed.write(text.encode("utf-8"))
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail when the committed table is stale")
    args = parser.parse_args()
    data = table_bytes()
    if args.check:
        current = TABLE.read_bytes() if TABLE.is_file() else b""
        print("pinyin table is current" if current == data else f"stale: re-run {pathlib.Path(__file__).name}")
        return 0 if current == data else 1
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_bytes(data)
    print(f"wrote {TABLE.relative_to(ROOT)} ({len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
