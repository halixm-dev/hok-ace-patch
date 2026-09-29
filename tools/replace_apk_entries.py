from __future__ import annotations

import argparse
import copy
import shutil
import zipfile
from pathlib import Path


SIGNATURE_SUFFIXES = (".RSA", ".DSA", ".EC", ".SF", ".MF")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replace", action="append", nargs=2, metavar=("ZIP_PATH", "FILE"))
    args = parser.parse_args()
    replacements = {name: Path(path) for name, path in args.replace or []}

    with zipfile.ZipFile(args.source, "r") as source, zipfile.ZipFile(
        args.output, "w", allowZip64=True
    ) as output:
        source_names = {item.filename for item in source.infolist()}
        missing = replacements.keys() - source_names
        if missing:
            raise KeyError(f"APK entries not found: {sorted(missing)}")

        for item in source.infolist():
            upper = item.filename.upper()
            if upper.startswith("META-INF/") and upper.endswith(SIGNATURE_SUFFIXES):
                continue
            replacement = replacements.get(item.filename)
            output_item = copy.copy(item)
            with output.open(output_item, "w", force_zip64=True) as destination:
                try:
                    if replacement is None:
                        with source.open(item, "r") as original:
                            shutil.copyfileobj(original, destination, length=1024 * 1024)
                    else:
                        with replacement.open("rb") as translated:
                            shutil.copyfileobj(translated, destination, length=1024 * 1024)
                except Exception as error:
                    raise RuntimeError(f"failed to copy APK entry {item.filename!r}") from error


if __name__ == "__main__":
    main()
