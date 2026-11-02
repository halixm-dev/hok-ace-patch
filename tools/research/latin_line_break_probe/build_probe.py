"""Build the throwaway Latin line-break probe: the normal device patch plus a probe script edit.

Never ship this output. It runs `build_device_patch.main` with one extra `extra_text.SCRIPT_EDITS` entry
added in memory, so `tools/` stays untouched. Arguments are `build_device_patch.py`'s own:

    .venv\\Scripts\\python.exe tools\\research\\latin_line_break_probe\\build_probe.py [--v2 | --v3 | --v4] --runtime resources\\runtime ^
        --game <dump> --catalog resources\\catalog --work <work> --output <out> --apk <apk>

Without `--v2`: probe.lua in PVPRankDataClass (`6CB505C6553141B4`), run once at the first rank title.
With `--v2`: probe_v2.lua in UIPrefabClass (`3482BF89614B5ABB`, prime-only, so it reaches the phone through
the append pass), run on every `UIPrefabClass:Create`.
With `--v3`: probe_v3.lua in UIPrefabClass after the shipped flag reset, run once at the first `Create` that
has `AssetService` and a live `UI.Text`. It reads which `Font/NumberCharacters` the game serves and whether
`LoadLinebreakingRules(nil, nil, asset)` makes flag-on layout keep words whole.
With `--v4`: probe_v4.lua at the same place: the per-frame reset (LateUpdate through `CoroutineService`, and
`Canvas.preWillRenderCanvases` when it can be hooked), logging each frame the flag is on at the check.

`--check [--v2 | --v3 | --v4] <file>` instead prints whether the edit applies to a raw script read from a file, and
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


# After the shipped reset (`extra_text.SCRIPT_EDITS[UI_PREFAB_CLASS]`), which v3 is applied on top of.
V3_DEFS_ANCHOR = "local _setLineBreakFlag = nil\n"
V3_CALL_ANCHOR = "        end\n    end)\n    local resourcePath = self:vGetPath()\n"


def probe_edits(version: int) -> tuple[int, tuple[tuple[str, str], ...]]:
    if version in (3, 4):
        probe = pathlib.Path(__file__).with_name(f"probe_v{version}.lua").read_text(encoding="utf-8")
        return UI_PREFAB_CLASS, ((V3_DEFS_ANCHOR, probe + "\n" + V3_DEFS_ANCHOR),
                                 (V3_CALL_ANCHOR, V3_CALL_ANCHOR + f"    pcall(__LatinLineBreakProbeV{version})\n"))
    file_hash, old, new = probe_edit(version == 2)
    return file_hash, ((old, new),)


def probe_edit(v2: bool) -> tuple[int, str, str]:
    if v2:
        probe = pathlib.Path(__file__).with_name("probe_v2.lua").read_text(encoding="utf-8")
        return UI_PREFAB_CLASS, V2_ANCHOR, (probe + "\n" + V2_ANCHOR
                                            + "    pcall(__LatinLineBreakProbeV2, self, resourcePath)\n")
    probe = pathlib.Path(__file__).with_name("probe.lua").read_text(encoding="utf-8")
    return PVP_RANK_DATA, ANCHOR, probe + "\n" + ANCHOR + "    pcall(__LatinLineBreakProbe)\n"


def install(version: int) -> int:
    import extra_text

    file_hash, edits = probe_edits(version)
    extra_text.SCRIPT_EDITS[file_hash] = extra_text.SCRIPT_EDITS.get(file_hash, ()) + edits
    # SCRIPT_ASSETS is computed at import; the append pass and the rebuild transform read it from here.
    extra_text.SCRIPT_ASSETS = extra_text.SCRIPT_ASSETS | {file_hash}
    return file_hash


def check(path: pathlib.Path, version: int) -> None:
    import extra_text

    file_hash = install(version)
    raw = path.read_bytes()
    new = extra_text.rewrite_script(file_hash, raw, catalog=type("C", (), {"unique": {}})())
    if new is None or b"pcall(__LatinLineBreakProbe" not in new:
        sys.exit(f"probe edit does not apply to {path}")
    out = path.with_name(path.name + ".probe.lua")
    out.write_bytes(new)
    print(f"probe applies: {len(raw)} -> {len(new)} bytes, written to {out}")


def _version(flag: list[str]) -> int:
    return {"--v2": 2, "--v3": 3, "--v4": 4}.get(flag[0] if flag else "", 1)


def main() -> None:
    if sys.argv[1:2] == ["--check"]:
        check(pathlib.Path(sys.argv[-1]), _version(sys.argv[2:3]))
        return
    version = _version(sys.argv[1:2])
    if version != 1:
        del sys.argv[1]
    install(version)
    import build_device_patch

    build_device_patch.main()


if __name__ == "__main__":
    main()
