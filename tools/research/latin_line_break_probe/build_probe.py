"""Build the throwaway Latin line-break probe: the normal device patch plus a probe script edit.

Never ship this output. It runs `build_device_patch.main` with one extra `extra_text.SCRIPT_EDITS` entry
added in memory, so `tools/` stays untouched. Arguments are `build_device_patch.py`'s own:

    .venv\\Scripts\\python.exe tools\\research\\latin_line_break_probe\\build_probe.py [--v2] --runtime resources\\runtime ^
        --game <dump> --catalog resources\\catalog --work <work> --output <out> --apk <apk>

Without `--v2`: probe.lua in PVPRankDataClass (`6CB505C6553141B4`), run once at the first rank title.
With `--v2`: probe_v2.lua in UIPrefabClass (`3482BF89614B5ABB`, prime-only, so it reaches the phone through
the append pass), run on every `UIPrefabClass:Create`.

`--check [--v2] <file>` instead prints whether the edit applies to a raw script read from a file, and
writes the edited script beside it as `<file>.probe.lua`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

PVP_RANK_DATA = 0x6CB505C6553141B4
ANCHOR = "function PVPRankDataClass:vGetRankTitle(rank, level, uid, eloLineIdx)\n"
UI_PREFAB_CLASS = 0x3482BF89614B5ABB
V2_ANCHOR = ("function UIPrefabClass:Create(mediator, parentPrefabClass, parentTf, argument, customID, addCanvas, "
             "localScale, lifeType)\n    local resourcePath = self:vGetPath()\n")


def probe_edit(v2: bool) -> tuple[int, str, str]:
    if v2:
        probe = pathlib.Path(__file__).with_name("probe_v2.lua").read_text(encoding="utf-8")
        return UI_PREFAB_CLASS, V2_ANCHOR, (probe + "\n" + V2_ANCHOR
                                            + "    pcall(__LatinLineBreakProbeV2, self, resourcePath)\n")
    probe = pathlib.Path(__file__).with_name("probe.lua").read_text(encoding="utf-8")
    return PVP_RANK_DATA, ANCHOR, probe + "\n" + ANCHOR + "    pcall(__LatinLineBreakProbe)\n"


def install(v2: bool) -> int:
    import extra_text

    file_hash, old, new = probe_edit(v2)
    extra_text.SCRIPT_EDITS[file_hash] = extra_text.SCRIPT_EDITS.get(file_hash, ()) + ((old, new),)
    # SCRIPT_ASSETS is computed at import; the append pass and the rebuild transform read it from here.
    extra_text.SCRIPT_ASSETS = extra_text.SCRIPT_ASSETS | {file_hash}
    return file_hash


def check(path: pathlib.Path, v2: bool) -> None:
    import extra_text

    file_hash = install(v2)
    raw = path.read_bytes()
    new = extra_text.rewrite_script(file_hash, raw, catalog=type("C", (), {"unique": {}})())
    if new is None or b"pcall(__LatinLineBreakProbe" not in new:
        sys.exit(f"probe edit does not apply to {path}")
    out = path.with_name(path.name + ".probe.lua")
    out.write_bytes(new)
    print(f"probe applies: {len(raw)} -> {len(new)} bytes, written to {out}")


def main() -> None:
    if sys.argv[1:2] == ["--check"]:
        check(pathlib.Path(sys.argv[-1]), sys.argv[2:3] == ["--v2"])
        return
    v2 = sys.argv[1:2] == ["--v2"]
    if v2:
        del sys.argv[1]
    install(v2)
    import build_device_patch

    build_device_patch.main()


if __name__ == "__main__":
    main()
