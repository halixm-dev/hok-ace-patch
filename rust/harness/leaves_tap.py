"""Record the Wave 3 pipeline leaves for the Rust port to replay (rust/MAP.md, wave 3).

Covers ``languages``, ``terminology``, ``catalog_supplement``, ``catalog_updates``,
``resource_tokens``, ``axml_set_debuggable``, ``axml_label``, ``broken_list``, ``config_bin``, ``pb_text``,
``lineup_codes``, ``unity_text``, ``sprite_table``, ``card_titles`` and ``hand_card_titles``, from these
sources:

- the ``AndroidManifest.xml`` of each ``--apk`` and each ``--broken-list`` file, as they are, cut
  short and with bytes changed (axml_cases.py; a manifest whose chunk walk would never end is left
  out, since Python spins on it);
- the config bins in each ``--config-bins`` folder (``*.bin``, a lineup bin named ``<layer>-<HASH>.bin``)
  and the staged replacements, as they are, cut short and with bytes changed, with generated share
  codes, deflate streams and Unity SerializedFiles (lineup_cases.py);
- the package-19 and package-15 assets the title passes read, in ``--titles`` as
  ``<layer>/<package>/<HASH>.bin``, as they are, with the titles moved back, and changed (title_cases.py);
- each shipped catalog through the load edits in ``engine_hooks._load_catalog_hook``'s order
  (supplement, admitted tables, glossary, update rows), each step's result and the edited catalog;
- every catalog string holding a brace through ``expand_resource_tokens`` in both languages' terms,
  and every staged replacement under ``--replacements`` (and each cut short) through
  ``expand_tokens_in_message``;
- generated cases: glossary rewrites beside unusual characters, supplement files and pairs that the
  loader and ``check`` refuse, update rows on synthetic catalogs, protobuf framing and its errors,
  ``expand_staged`` on a fixture folder, and the language lookups.

Each line of ``<dir>/calls.jsonl`` is ``{"fn", "args", "result"}``; bytes are hex, and a result is
``{"ok": ...}`` or ``{"error": "Class: message"}``. The edited catalogs are ``<dir>/<name>.json.gz``.

    .venv\\Scripts\\python.exe rust\\harness\\leaves_tap.py <dir> [--replacements <folder> ...]
        [--apk <apk> ...] [--broken-list <BrokenList.db> ...] [--config-bins <folder> ...]
        [--titles <folder>]
    cargo run --release -p hokace-core --example leaves_replay -- <dir>

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import catalog_supplement  # noqa: E402
import catalog_updates  # noqa: E402
import languages  # noqa: E402
import resource_tokens  # noqa: E402
import terminology  # noqa: E402

CATALOGS = ROOT / "resources"


class Recorder:
    def __init__(self, folder: Path) -> None:
        self.handle = (folder / "calls.jsonl").open("w", encoding="utf-8", newline="\n")
        self.count = 0

    def call(self, fn: str, args: dict, call) -> None:
        try:
            result = {"ok": call()}
        except Exception as error:  # noqa: BLE001 - the error is the recording
            result = {"error": f"{type(error).__name__}: {error}"}
        self.handle.write(json.dumps({"fn": fn, "args": args, "result": result}, ensure_ascii=False) + "\n")
        self.count += 1


def _catalogs(rec: Recorder, out: Path) -> list[dict]:
    datas = []
    for language in languages.LANGUAGES.values():
        folder = CATALOGS / language.catalog
        with gzip.open(folder / "catalog.json.gz", "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        datas.append(json.loads(json.dumps(data)))
        steps = {}
        steps["supplement"] = catalog_supplement.apply(data, language.code)
        steps["admit"] = catalog_updates.admit_tables(data)
        steps["terminology"] = list(terminology.apply(data, language.terms).items())
        steps["updates"] = catalog_updates.apply(data, language.code)
        with gzip.open(out / f"{language.catalog}.json.gz", "wt", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        rec.call("load_edits", {"catalog": language.catalog, "code": language.code}, lambda steps=steps: steps)
        source = datas[-1]
        for code in ("en", "id"):
            rec.call("entries", {"catalog": language.catalog, "code": code},
                     lambda source=source, code=code: list(catalog_supplement.entries(
                         dict(source["unique"]), code).items()))
        rec.call("derived", {"catalog": language.catalog},
                 lambda source=source: list(catalog_supplement.derived(source["unique"]).items()))
    return datas


def _tokens(rec: Recorder, datas: list[dict], replacements: list[Path]) -> None:
    texts = sorted({text for data in datas for pair in data["unique"].items() for text in pair if "{" in text})
    tables = {code: language.resource_terms for code, language in languages.LANGUAGES.items()}
    for code, terms in tables.items():
        rec.call("expand_resource_tokens_all", {"code": code, "texts": texts},
                 lambda terms=terms: [resource_tokens.expand_resource_tokens(text, terms) for text in texts])
    extra = ["", "{", "{Energy}", "a{Energy}b", "1{LordExp}+2", "}{LordHp}-x", "{Energy}-{0}", "{Energy}+²",
             "{Energy}+½", "{Energy}{Energy}", "{LordHp}{LordExp}", "é{Energy}é", "{Energy}́", "{Ene{Energy}rgy}",
             "{Energy}+", "{Energy}-", "Z{Energy}", "_{Energy}_", "9{LordHp}9"]
    for code, terms in tables.items():
        for text in extra:
            rec.call("expand_resource_tokens", {"code": code, "text": text},
                     lambda terms=terms, text=text: resource_tokens.expand_resource_tokens(text, terms))
    for folder in replacements:
        for path in sorted(folder.rglob("*.assets")):
            raw = path.read_bytes()
            for cut in (len(raw), len(raw) // 2, len(raw) - 1):
                for code in tables:
                    rec.call("expand_file", {"code": code, "path": str(path), "cut": cut},
                             lambda data=raw[:cut], code=code: _hashed(data, tables[code]))


def _expanded(data: bytes, terms) -> list:
    out, count = resource_tokens.expand_tokens_in_message(data, terms)
    return [out.hex(), count]


def _hashed(data: bytes, terms) -> list:
    out, count = resource_tokens.expand_tokens_in_message(data, terms)
    return [hashlib.sha256(out).hexdigest(), count]


def _field(number: int, wire: int, payload: bytes) -> bytes:
    key = resource_tokens._encode_varint(number << 3 | wire)
    if wire == 2:
        return key + resource_tokens._encode_varint(len(payload)) + payload
    return key + payload


def _messages() -> list[bytes]:
    text = "Gain{Energy}now".encode()
    inner = _field(1, 2, text) + _field(2, 0, b"\x05")
    cases = [
        b"", text, _field(1, 2, text), _field(1, 2, inner), _field(3, 2, _field(1, 2, inner)),
        _field(1, 2, b"\x01" + "{Energy}".encode()),  # control character: walked as a message, fails
        _field(1, 2, "{Energy}\x01".encode()), _field(1, 2, b"\xff{Energy}"),
        _field(1, 1, b"12345678") + _field(2, 2, text), _field(1, 5, b"1234") + _field(2, 2, text),
        _field(1, 1, b"1234") + text, _field(1, 5, b"12") + text, b"\x00" + text, b"\x0b" + text,
        b"\x0f" + text, _field(1, 0, b"\x80" * 9 + b"\x01") + _field(2, 2, text),
        _field(1, 0, b"\x80" * 10 + b"\x01") + _field(2, 2, text), b"\x80" * 11 + text,
        _field(1, 2, text)[:-1], b"\x0a\x80\x00" + "{Energy}".encode() + _field(2, 2, text),
        b"\x0a\xff\xff\xff\xff\xff\xff\xff\xff\x7f{Energy}", _field(1, 2, "{Energy}{LordExp}{LordHp}".encode()),
        _field(1, 2, b"{Energy}" + b"\x00"), _field(1, 2, "{0|1}{Energy}\t\n\r".encode()),
        _field(2, 2, _field(1, 2, b"\x00\x01")) + _field(3, 2, "x{LordHp}".encode()),
    ]
    nested = _field(1, 2, text)
    for _ in range(20):
        nested = _field(1, 2, nested + b"\x10\x01")
    cases.append(nested)
    rng = random.Random(3)
    for _ in range(300):
        base = bytearray(rng.choice(cases[2:]))
        for _ in range(rng.randint(1, 3)):
            if base:
                base[rng.randrange(len(base))] = rng.randrange(256)
        cases.append(bytes(base))
    return cases


def _generated(rec: Recorder, out: Path) -> None:
    for terms_name, terms in (("en", languages.ENGLISH.terms), ("id", languages.LANGUAGES["id"].terms)):
        targets = [
            "plunder", "Plunder", "PLUNDER", "plunderé", "éplunder", "plundeŕ", "plunder²", "²plunder",
            "plunder‍x", "drainſ", "ſiphon", "ſiphons the drain", "╊plunder", "╊drains", "x╊seized",
            "<plunder>", "{plunder}", "<a>plunder</a>", "Soul Snatch snatch", "soul snatch Snatch",
            "Readiness and readiness", "╬Siap", "Siap", "steal╊", "Prepare series", "Prepare Series",
            "blazing series", "Temporary Level Series", "Shield seri", "ÉPrepare Series", "Momentum Secret Technique",
            "Harness Momentum Secret Technique", "Pray, praying, prayers", "chess  -player", "Chess Players",
            "pemain catur", "Chessplayers", "Supreme Decisions", "keputusan final", "CaptureCard", "to capture",
            "Ready", "ready", "Kejang", "PIunder", "Xiaotu’s Blessing", "Little Tu's Assist", "the Rabbit Aid",
            "God's Moment", "", "dränage drain_ drain-", "drain1 1drain", "déblazing series", "Ǆa series",
        ]
        for index, term in enumerate(terms):
            for target in targets:
                rec.call("rewrite", {"terms": terms_name, "index": index, "target": target},
                         lambda term=term, target=target: term.rewrite(term.source + "x", target))
    for code in ("en", "id"):
        rec.call("apply_terms_empty", {"code": code},
                 lambda: list(terminology.apply({"unique": {"夺取": "plunder"}}, ()).items()))
    # supplement files the loader refuses
    folder = out / "supplement-fixtures"
    folder.mkdir(exist_ok=True)
    files = {
        "ok.json": '[{"note": "n", "texts": {"a": ["x", "y"]}}, {"note": "m", "texts": {"b": ["1", "2"]}}]',
        "dup-key.json": '[{"note": "n", "texts": {"a": ["x", "y"], "a": ["x", "y"]}}]',
        "dup-note.json": '[{"note": "n", "note": "m", "texts": {}}]',
        "dup-across.json": '[{"note": "n", "texts": {"a": ["x", "y"]}}, {"note": "m", "texts": {"a": ["1", "2"]}}]',
        "bad-pair.json": '[{"note": "n", "texts": {"a": ["x"]}}]',
        "bad-type.json": '[{"note": "n", "texts": {"a\'b": ["x", 1]}}]',
    }
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
        rec.call("supplement_load", {"file": name}, lambda name=name: _load(folder, name))
    pairs = [{"a{0}": "b{0}"}, {"a{0}": "b"}, {"<b>x</b>%s": "%s<b>y</b>"}, {"%d%s": "%s"}, {"{a}{b}": "{b}{a}"},
             {"x": "{y}", "z": "z", "w": "<i>"}]
    for pair in pairs:
        rec.call("check", {"pairs": list(pair.items())}, lambda pair=pair: catalog_supplement.check(pair))
    rec.call("chinese_number", {}, lambda: [catalog_supplement.chinese_number(n) for n in range(1, 101)])
    uniques = [
        {}, {"逆天改命": "Defy Fate", "逆天改命(李白)": "Defy Fate (Li Bai)", "逆天改命(李信)": "Defy Fate Li Xin",
             "河洛": "Heluo", "李白": "", "契约·甲(乙)": "Contract: A (B)", "契约·丙(丁)": "Pact C",
             "<color=#fff>某卡包</color>": "<color=#fff>Some Pack</color>", "<color=#fff>某某卡包</color>": "plain"},
        {"<b>╬整备系列</b>\n效果{0}": "<b>Prepare Series</b>\nEffect {0}", "a系列\nb": "A Series\n ",
         "c系列\nd\ne": "C Series\nD", "e系列\nf": "E Series\nF{1}", "完美橱窗": " perfect showcase. ",
         "乔汐": "Qiao Xi", "乔汐上大分": "Own", "姜导上大分": "", "姜导": "Jiang"},
    ]
    for unique in uniques:
        for code in ("en", "id"):
            rec.call("entries_synthetic", {"unique": list(unique.items()), "code": code},
                     lambda unique=unique, code=code: list(catalog_supplement.entries(dict(unique), code).items()))
    datas = [
        {}, {"table_hashes": ["DD5B5EDFBB69FEED"]},
        {"table_hashes": ["DD5B5EDFBB69FEED", "C13DF45E3492CA0C", "39E980368CABE4A4"],
         "unique": {catalog_updates.YAO_SOURCE: "Combine!"},
         "english_updates": [["C13DF45E3492CA0C", "#FBF327E86456E964#", catalog_updates.YAO_PREVIOUS, "old"]]},
        {"table_hashes": ["C13DF45E3492CA0C"], "unique": {catalog_updates.YAO_SOURCE: catalog_updates.YAO_PREVIOUS}},
        {"table_hashes": ["C13DF45E3492CA0C"], "unique": {catalog_updates.YAO_SOURCE: ""}},
    ]
    for data in datas:
        for code in ("en", "id"):
            rec.call("updates", {"data": data, "code": code}, lambda data=data, code=code: _updates(data, code))
    terms = languages.ENGLISH.resource_terms
    for data in _messages():
        rec.call("expand_tokens_in_message", {"code": "en", "data": data.hex()},
                 lambda data=data: _expanded(data, terms))
        rec.call("expand_tokens", {"code": "en", "data": data.hex()}, lambda data=data: _expand_logged(data, terms))
    staged = out / "staged-fixture"
    shutil.rmtree(staged, ignore_errors=True)
    for name, files in (("a", {"2.assets": _field(1, 2, b"x{Energy}"), "1.ASSETS": b"\x00",
                               "3.assets": _field(1, 2, b"none"), "4.bin": _field(1, 2, b"{Energy}")}),
                        ("b", {"9.assets": _field(1, 2, b"{LordHp}{LordExp}")})):
        (staged / name).mkdir(parents=True)
        for file_name, content in files.items():
            (staged / name / file_name).write_bytes(content)
    before = {str(p.relative_to(staged)): p.read_bytes().hex() for p in sorted(staged.rglob("*")) if p.is_file()}
    rec.call("expand_staged", {"folders": ["a", "b"], "code": "id", "before": before},
             lambda: _staged(staged, ["a", "b"], languages.LANGUAGES["id"].resource_terms))
    for code in ("en", "id", "fr", "", "EN"):
        rec.call("languages_get", {"code": code}, lambda code=code: languages.get(code).catalog)
    for name in ("catalog", "catalog_id", "catalog_id/", "other", "x/catalog_id", ""):
        rec.call("for_catalog", {"path": name}, lambda name=name: languages.for_catalog(Path(name)).code)
    payload = out / "payload-fixture"
    shutil.rmtree(payload, ignore_errors=True)
    for path in ("catalog/A.blocks", "catalog/B.blocks", "catalog_id/A.blocks", "catalog_id/previews/A.png"):
        (payload / path).parent.mkdir(parents=True, exist_ok=True)
        (payload / path).write_bytes(b"x")
    for catalog in ("catalog", "catalog_id", "other"):
        for name in ("A.blocks", "B.blocks", "C.blocks", "previews/A.png"):
            rec.call("payload_path", {"catalog": catalog, "name": name},
                     lambda catalog=catalog, name=name: Path(languages.payload_path(payload / catalog, name))
                     .relative_to(payload).as_posix())


def _load(folder: Path, name: str):
    old = catalog_supplement._data_dir
    catalog_supplement._data_dir = lambda: folder
    try:
        return list(catalog_supplement._load(name).items())
    finally:
        catalog_supplement._data_dir = old


def _updates(data: dict, code: str):
    data = json.loads(json.dumps(data))
    admitted = catalog_updates.admit_tables(data)
    added = catalog_updates.apply(data, code)
    return [admitted, added, data]


def _expand_logged(data: bytes, terms):
    lines: list[str] = []
    out = resource_tokens.expand_tokens(data, lines.append, terms)
    return [out.hex(), lines]


def _staged(root: Path, names: list[str], terms):
    lines: list[str] = []
    plans = [(None, root / name, {}) for name in names]
    changed = resource_tokens.expand_staged(plans, lines.append, terms)
    after = {str(p.relative_to(root)): p.read_bytes().hex() for p in sorted(root.rglob("*")) if p.is_file()}
    return [changed, lines, after]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dir", type=Path)
    parser.add_argument("--replacements", type=Path, action="append", default=[])
    parser.add_argument("--apk", type=Path, action="append", default=[])
    parser.add_argument("--broken-list", type=Path, action="append", default=[])
    parser.add_argument("--config-bins", type=Path, action="append", default=[])
    parser.add_argument("--titles", type=Path, action="append", default=[])
    args = parser.parse_args()
    args.dir.mkdir(parents=True, exist_ok=True)
    rec = Recorder(args.dir)
    datas = _catalogs(rec, args.dir)
    _tokens(rec, datas, args.replacements)
    with tempfile.TemporaryDirectory():
        _generated(rec, args.dir)
    import axml_cases

    axml_cases.record(rec, args.dir, args.apk, args.broken_list)
    import lineup_cases

    lineup_cases.record(rec, args.dir, args.config_bins, args.replacements)
    import title_cases

    title_cases.record(rec, args.dir, args.titles)
    rec.handle.close()
    print(f"recorded {rec.count} calls in {args.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
