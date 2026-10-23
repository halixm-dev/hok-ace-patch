"""Build the throwaway Latin line-break probe: the normal device patch plus probe.lua in PVPRankDataClass.

Never ship this output. It runs `build_device_patch.main` with one extra `extra_text.SCRIPT_EDITS` entry
added in memory, so `tools/` stays untouched. Arguments are `build_device_patch.py`'s own:

    .venv\\Scripts\\python.exe .scratch\\latin-line-breaks\\probe\\build_probe.py --runtime resources\\runtime ^
        --game <dump> --catalog resources\\catalog --work <work> --output <out> --apk <apk>

`--check` instead prints whether the edit applies to a raw script read from a file, and writes the edited
script beside it as `<file>.probe.lua`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

PVP_RANK_DATA = 0x6CB505C6553141B4
ANCHOR = "function PVPRankDataClass:vGetRankTitle(rank, level, uid, eloLineIdx)\n"


def probe_edit() -> tuple[str, str]:
    probe = (pathlib.Path(__file__).with_name("probe.lua")).read_text(encoding="utf-8")
    return ANCHOR, probe + "\n" + ANCHOR + "    pcall(__LatinLineBreakProbe)\n"


def install() -> None:
    import extra_text

    extra_text.SCRIPT_EDITS[PVP_RANK_DATA] = extra_text.SCRIPT_EDITS.get(PVP_RANK_DATA, ()) + (probe_edit(),)


def check(path: pathlib.Path) -> None:
    import extra_text

    install()
    raw = path.read_bytes()
    new = extra_text.rewrite_script(PVP_RANK_DATA, raw, catalog=type("C", (), {"unique": {}})())
    if new is None or b"__LatinLineBreakProbe" not in new:
        sys.exit(f"probe edit does not apply to {path}")
    out = path.with_name(path.name + ".probe.lua")
    out.write_bytes(new)
    print(f"probe applies: {len(raw)} -> {len(new)} bytes, written to {out}")


def main() -> None:
    if sys.argv[1:2] == ["--check"]:
        check(pathlib.Path(sys.argv[2]))
        return
    install()
    import build_device_patch

    build_device_patch.main()


if __name__ == "__main__":
    main()
