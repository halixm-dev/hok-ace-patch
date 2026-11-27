"""The title cases of leaves_tap.py: ``sprite_table``, ``card_titles`` and ``hand_card_titles`` on the
package-19 and package-15 assets the title passes read, from a pristine and a patched dump, as they are
and changed.

``--titles <folder>`` holds ``<layer>/<package>/<HASH>.bin`` (``clean`` and ``game``), copied into
``<dir>/titles``. A changed asset is recorded as its edit, not its bytes: ``cut`` (keep that many
bytes), then ``flips`` (``[offset, byte]`` pairs), or ``drop`` (the package lacks it) and ``empty``.
A changed layout is recorded whole. Results over 2 KiB are recorded as their SHA-256.

Run alone, it writes only these cases:

    .venv\\Scripts\\python.exe rust\\harness\\title_cases.py <dir> --titles <folder>

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import copy
import hashlib
import random
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import card_titles  # noqa: E402
import hand_card_titles  # noqa: E402
import sprite_table  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
LAYERS = ("clean", "game")
MOVED = LAYERS + ("inverted",)  # inverted: the titles moved back to their pristine boxes (_invert)


def _blob(data: bytes) -> str:
    return data.hex() if len(data) <= 2048 else "sha256:" + hashlib.sha256(data).hexdigest()


def _edited(data: bytes, edit: dict) -> bytes | None:
    if edit.get("drop"):
        return None
    if edit.get("empty"):
        return b""
    out = bytearray(data[: edit["cut"]] if "cut" in edit else data)
    for at, byte in edit.get("flips", []):
        if at < len(out):
            out[at] = byte
    return bytes(out)


def _flips(rng: random.Random, size: int, count: int, lo: int = 0, hi: int | None = None) -> list[list[int]]:
    hi = size if hi is None else min(hi, size)
    lo = max(lo, 0)
    return [[rng.randrange(lo, hi), rng.randrange(256)] for _ in range(count)] if hi > lo else []


# --- sprite_table -----------------------------------------------------------------------------------

SIZES = ((1024, None), (2048, None), (1024, 512), (64, None), (1, 1), (0, None))


def _rects(data: bytes, width: int, height: int | None) -> list:
    return [[name, list(rect)] for name, rect in sprite_table.sprite_rects(data, width, height).items()]


def _record(name: str, rect: tuple[float, ...], length: int | None = None) -> bytes:
    raw = name.encode()
    head = bytes([len(raw) if length is None else length]) + b"\0\0\0" + raw
    return head + b"\0" * (-len(head) % 4) + struct.pack("<4f", *rect)


SYNTHETIC = {
    "plain": _record("Image_12345", (1, 2, 3, 4)),
    "two": _record("Image_12345", (1, 2, 3, 4)) + _record("Image_1234567890", (10.5, 20.75, 30.25, 40.5)),
    "dup": _record("Image_12345", (1, 2, 3, 4)) + _record("Image_12345", (5, 6, 7, 8)),
    "wrong-length": _record("Image_12345", (1, 2, 3, 4), length=0x0C) + _record("Image_54321", (1, 1, 1, 1)),
    "eleven-digits": _record("Image_12345678901", (1, 2, 3, 4), length=0x10),
    "four-digits": _record("Image_1234", (1, 2, 3, 4), length=0x0A),
    "short-tail": _record("Image_12345", (1, 2, 3, 4))[:-1],
    "edge": _record("Image_12345", (0, 0, 1024, 1024)) + _record("Image_22345", (1023.9, 1023.9, 0.1, 0.1)),
    "outside": _record("Image_12345", (1024, 0, 1, 1)) + _record("Image_22345", (0, 0, 0, 5))
    + _record("Image_32345", (-0.0, -1, 3, 3)) + _record("Image_42345", (1, 1, 1025, 1)),
    "nan": _record("Image_12345", (float("nan"), 0, 1, 1)) + _record("Image_22345", (0, 0, float("inf"), 1)),
    "unaligned": b"x" + _record("Image_123456", (1, 2, 3, 4)) + b"yz" + _record("Image_7654321", (3, 3, 3, 3)),
    "overlap": b"\x0b\x00\x00\x00Image_\x0b\x00\x00\x00Image_12345" + b"\0" * 20,
    "negative-y": _record("Image_12345", (2.5, 0.5, 3.75, 1.25)),
    "empty": b"",
}


def _sprite_table(rec, out: Path, assets: dict) -> None:
    rng = random.Random(41)
    pattern = sprite_table.NAME
    for layer in LAYERS:
        for asset, path in sorted(assets[layer]["19"].items()):
            relative = f"titles/{layer}/19/{asset:016X}.bin"
            data = path.read_bytes()
            for width, height in SIZES:
                rec.call("st_rects", {"file": relative, "width": width, "height": height},
                         lambda d=data, w=width, h=height: _rects(d, w, h))
            starts = [m.start() for m in pattern.finditer(data)]
            if not starts:
                continue
            for index in range(12):
                at = rng.choice(starts)
                edit = {"flips": [[min(len(data) - 1, at + rng.choice((0, 1, 4, 9, 11, 13, 16, 18, 20, 24, 28))),
                                   rng.choice((0, 0x0B, 0x0C, 0x31, 0x39, 0x41, 0x7F, 0x80, 0xFF))]
                                  for _ in range(rng.randint(1, 3))]}
                if index % 4 == 3:
                    edit["cut"] = at + rng.randrange(8, 40)
                changed = _edited(data, edit)
                rec.call("st_rects", {"file": relative, "edit": edit, "width": 1024, "height": None},
                         lambda d=changed: _rects(d, 1024, None))
    for name, data in SYNTHETIC.items():
        for width, height in SIZES:
            rec.call("st_rects", {"bytes": data.hex(), "width": width, "height": height, "case": name},
                     lambda d=data, w=width, h=height: _rects(d, w, h))


# --- card_titles ------------------------------------------------------------------------------------

def _fields(obj: bytes) -> list:
    name, at, rect = card_titles.sprite_fields(obj)
    return [name, [at["rect"], at["vertices"], at["texture_rect"], at["uv_transform"]],
            struct.pack("<4f", *rect).hex()]


def _sprite_fields(rec, layout: dict) -> None:
    rng = random.Random(43)
    table_hash = int(layout["sprite_table"], 16)
    for layer in MOVED:
        relative = f"titles/{layer}/19/{table_hash:016X}.bin"
        data = (_OUT / relative).read_bytes()
        for path_id, start, size in card_titles._objects(data, card_titles.SPRITE_CLASS):
            obj = data[start:start + size]
            args = {"file": relative, "start": start, "size": size}
            rec.call("ct_fields", args, lambda o=obj: _fields(o))
            for index in range(3):
                edit = {"flips": _flips(rng, size, rng.randint(1, 3), 0, min(size, 160) if index < 2 else size)}
                if index == 2:
                    edit["cut"] = rng.randrange(size)
                rec.call("ct_fields", {**args, "edit": edit}, lambda o=_edited(obj, edit): _fields(o))
    for body in (b"", b"\x04\x00\x00\x00ab", b"\xff\xff\xff\xff" + b"\0" * 120, b"\x02\x00\x00\x00\xe7\x8e" + b"\0" * 300,
                 struct.pack("<i", -8) + b"\0" * 200, b"\x03\x00\x00\x00abc\x00" + b"\x01" * 300):
        rec.call("ct_fields", {"bytes": body.hex()}, lambda o=body: _fields(o))


def _relayout_result(read, layout: dict):
    jobs = card_titles.relayout(read, layout)
    return None if jobs is None else [[f"{asset:016X}", _blob(raw)] for asset, raw in jobs.items()]


def _layouts(real: dict) -> dict[str, dict]:
    found: dict[str, dict] = {}

    def variant(name: str, change) -> None:
        layout = copy.deepcopy(real)
        change(layout)
        found[name] = layout

    titles = list(real["titles"])
    art = list(real["art"])
    boxes = list(real["boxes"])
    first, second = titles[0], titles[1]
    variant("art-rect", lambda l: l["art"][art[0]].__setitem__(0, l["art"][art[0]][0] + 1))
    variant("art-short", lambda l: l["art"][art[1]].pop())
    variant("art-int", lambda l: l["art"].__setitem__(art[0], [int(v) for v in l["art"][art[0]]]))
    variant("was", lambda l: l["titles"][first]["was"].__setitem__(1, 7.0))
    variant("now", lambda l: l["titles"][second]["now"].__setitem__(2, 150.0))
    variant("now-fraction", lambda l: l["titles"][first].__setitem__("now", [v + 0.25 for v in l["titles"][first]["now"]]))
    variant("now-int", lambda l: l["titles"][first].__setitem__("now", [int(v) for v in l["titles"][first]["now"]]))
    variant("now-short", lambda l: l["titles"][second]["now"].pop())
    variant("now-long", lambda l: l["titles"][second]["now"].append(1.0))
    variant("now-huge", lambda l: l["titles"][first]["now"].__setitem__(2, 1e39))
    variant("now-missing", lambda l: l["titles"][first].pop("now"))
    variant("was-missing", lambda l: l["titles"][second].pop("was"))
    variant("title-dropped", lambda l: l["titles"].pop(first))
    variant("art-dropped", lambda l: l["art"].pop(art[0]))
    variant("title-extra", lambda l: l["titles"].__setitem__("Image_99999", {"text": "X", "was": [0.0, 0.0, 1.0, 1.0],
                                                                           "now": [0.0, 0.0, 1.0, 1.0]}))
    variant("art-extra", lambda l: l["art"].__setitem__("Image_99999", [0.0, 0.0, 1.0, 1.0]))
    variant("box-path", lambda l: l["boxes"][boxes[0]].__setitem__("path_id", l["boxes"][boxes[0]]["path_id"] + 1))
    variant("box-path-float", lambda l: l["boxes"][boxes[0]].__setitem__("path_id", float(l["boxes"][boxes[0]]["path_id"])))
    variant("box-was", lambda l: l["boxes"][boxes[1]].__setitem__("was", [1.0, 2.0]))
    variant("box-sprite", lambda l: l["boxes"][boxes[2]].__setitem__("sprite", "Image_00000"))
    variant("box-path-missing", lambda l: l["boxes"][boxes[3]].pop("path_id"))
    variant("box-unknown", lambda l: l["boxes"].__setitem__("0123456789ABCDEF", dict(l["boxes"][boxes[0]])))
    variant("box-bad-hash", lambda l: l["boxes"].__setitem__("XYZ", dict(l["boxes"][boxes[0]])))
    variant("boxes-empty", lambda l: l.__setitem__("boxes", {}))
    variant("boxes-missing", lambda l: l.pop("boxes"))
    variant("titles-missing", lambda l: l.pop("titles"))
    variant("table-bad", lambda l: l.__setitem__("sprite_table", "zz"))
    variant("table-prefixed", lambda l: l.__setitem__("sprite_table", "0x" + l["sprite_table"].lower()))
    variant("same-table", lambda l: l.__setitem__("timi_atlas", l["sprite_table"]))
    variant("table-is-box", lambda l: l.__setitem__("timi_atlas", boxes[0]))
    variant("swapped", lambda l: l.update(sprite_table=l["timi_atlas"], timi_atlas=l["sprite_table"]))
    return found


def _relayout(rec, layout: dict) -> None:
    rng = random.Random(47)

    def reader(layer: str, edits: dict):
        def read(asset: int):
            path = _OUT / "titles" / layer / "19" / f"{asset:016X}.bin"
            data = path.read_bytes() if path.is_file() else None
            edit = edits.get(f"{asset:016X}")
            return data if edit is None or data is None else _edited(data, edit)
        return read

    def call(layer: str, changed: dict | None, edits: dict) -> None:
        args = {"layer": layer, "layout": changed, "edits": edits}
        rec.call("ct_relayout", args, lambda: _relayout_result(reader(layer, edits), changed or layout))

    for layer in MOVED:
        call(layer, None, {})
        call(layer, _inverse(layout), {})
        for changed in _layouts(layout).values():
            call(layer, changed, {})
        targets = [layout["sprite_table"], layout["timi_atlas"], *list(layout["boxes"])[:4]]
        for target in targets:
            size = (_OUT / "titles" / layer / "19" / f"{target}.bin").stat().st_size
            for edit in ({"drop": True}, {"empty": True}, {"cut": size // 2}, {"cut": 47}, {"cut": size - 1},
                         {"flips": _flips(rng, size, 2, 0, 48)}, {"flips": _flips(rng, size, 3, 48, 400)},
                         {"flips": _flips(rng, size, 4)}, {"flips": _flips(rng, size, 1, size - 200)}):
                call(layer, None, {target: edit})
        for _ in range(30):
            target = rng.choice(targets)
            size = (_OUT / "titles" / layer / "19" / f"{target}.bin").stat().st_size
            call(layer, None, {target: {"flips": _flips(rng, size, rng.randint(1, 6))}})


# --- hand_card_titles -------------------------------------------------------------------------------

def _edit_summary(edits: dict) -> list:
    return [[f"{asset:016X}", e.source, e.target, list(e.box), hashlib.sha256(e.blocks).hexdigest()]
            for asset, e in edits.items()]


def _hand(rec) -> None:
    rng = random.Random(53)
    rec.call("hc_load", {"catalog": "resources/catalog"}, lambda: _edit_summary(hand_card_titles.load_edits(CATALOG)))
    rec.call("hc_load", {"catalog": "rust/harness/no-catalog"},
             lambda: _edit_summary(hand_card_titles.load_edits(ROOT / "rust" / "harness" / "no-catalog")))
    rec.call("ct_load_layout", {"catalog": "resources/catalog"}, lambda: card_titles.load_layout(CATALOG))
    rec.call("ct_load_layout", {"catalog": "rust/harness/no-catalog"},
             lambda: card_titles.load_layout(ROOT / "rust" / "harness" / "no-catalog"))
    edits = hand_card_titles.load_edits(CATALOG)
    hashes = list(edits)
    for layer in LAYERS:
        for asset, edit in edits.items():
            relative = f"titles/{layer}/15/{asset:016X}.bin"
            data = (_OUT / relative).read_bytes()
            variants: list[dict] = [{}, {"edit": {"flips": _flips(rng, len(data), 1)}}, {"edit": {"cut": len(data) - 16}}]
            variants.append({"other": f"{rng.choice(hashes):016X}"})
            digest = hashlib.sha256(data).hexdigest()
            x0, y0, x1, y1 = edit.box
            for box in ([x0, y0, x1, y1 + 1], [x1, y0, x0, y1], [-1, y0, x1, y1], [x0, y0, 102, y1],
                        [x0, y0, x1, 142], [x0, y1, x1, y1]):
                variants.append({"source": digest, "box": box})
            variants.append({"source": digest, "blocks_cut": len(edit.blocks) - 1})
            variants.append({"source": digest, "target": "0" * 64})
            for variant in variants:
                def run(variant=variant, data=data, edit=edit):
                    used = edits[int(variant["other"], 16)] if "other" in variant else edit
                    used = hand_card_titles.TitleEdit(
                        variant.get("source", used.source), variant.get("target", used.target),
                        tuple(variant.get("box", used.box)),
                        used.blocks[: variant["blocks_cut"]] if "blocks_cut" in variant else used.blocks)
                    raw = _edited(data, variant["edit"]) if "edit" in variant else data
                    result = used.apply(raw)
                    return None if result is None else _blob(result)
                rec.call("hc_apply", {"file": relative, "asset": f"{asset:016X}", **variant}, run)


_OUT = Path()


def _copy_inputs(out: Path, titles: Path) -> dict:
    assets: dict = {}
    for layer in LAYERS:
        assets[layer] = {}
        for package in ("19", "15"):
            target = out / "titles" / layer / package
            target.mkdir(parents=True, exist_ok=True)
            found = {}
            for path in sorted((titles / layer / package).glob("*.bin")):
                shutil.copyfile(path, target / path.name)
                found[int(path.stem, 16)] = target / path.name
            assets[layer][package] = found
    return assets


def _inverse(layout: dict) -> dict:
    """The layout that moves each title from its new box back to its pristine one."""
    back = copy.deepcopy(layout)
    for title in back["titles"].values():
        title["was"], title["now"] = title["now"], title["was"]
    for box in back["boxes"].values():
        _x, _y, w, h = layout["titles"][box["sprite"]]["now"]
        box["was"] = [w, h]
    return back


def _invert(out: Path, layout: dict) -> None:
    """Write <out>/titles/inverted/19: the dump's package-19 assets with the titles at their pristine boxes."""
    source, target = out / "titles" / "clean" / "19", out / "titles" / "inverted" / "19"
    target.mkdir(parents=True, exist_ok=True)

    def read(asset: int):
        path = source / f"{asset:016X}.bin"
        return path.read_bytes() if path.is_file() else None

    jobs = card_titles.relayout(read, _inverse(layout))
    if not jobs:
        raise SystemExit(f"the inverse layout moved nothing: {jobs!r}")
    for path in source.glob("*.bin"):
        shutil.copyfile(path, target / path.name)
    for asset, raw in jobs.items():
        (target / f"{asset:016X}.bin").write_bytes(raw)
    for asset, box in layout["boxes"].items():  # each Title box back at its own pristine size
        path = target / f"{asset}.bin"
        _x, _y, w, h = layout["titles"][box["sprite"]]["was"]
        moved = card_titles._move_box(path.read_bytes(), {"path_id": box["path_id"], "was": [w, h]},
                                      tuple(box["was"]))
        if moved is None:
            raise SystemExit(f"box {asset} did not move back")
        path.write_bytes(moved)
    print(f"inverted {len(jobs)} assets")


def record(rec, out: Path, titles: list[Path]) -> None:
    global _OUT
    if not titles:
        return
    _OUT = out
    assets = _copy_inputs(out, titles[0])
    layout = card_titles.load_layout(CATALOG)
    _invert(out, layout)
    _sprite_table(rec, out, assets)
    _sprite_fields(rec, layout)
    _relayout(rec, layout)
    _hand(rec)


def main() -> int:
    import argparse

    import leaves_tap

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dir", type=Path)
    parser.add_argument("--titles", type=Path, required=True)
    args = parser.parse_args()
    args.dir.mkdir(parents=True, exist_ok=True)
    rec = leaves_tap.Recorder(args.dir)
    record(rec, args.dir, [args.titles])
    rec.handle.close()
    print(f"recorded {rec.count} calls in {args.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
