r"""Re-apply this repo's catalog fixes and additions on top of whatever catalogs upstream ships.

Three kinds of change, all keyed by the Chinese source string in a catalog's `unique` map:

- the Indonesian fixes below (`CHANGE`, `ADD`): labels the user wants in English, and the 1.5.0.1 card
  texts the catalog only knew in their earlier wording;
- `catalog_rewrites.json` beside this script: entries both catalogs have but carry as garbled machine
  translation ("♪ Time for your Hero ♪", "At least.2One."), each rewritten in Indonesian (`id`) and,
  where the English is garbled too, in English (`en`). It covers every Diamond Frenzy talent text (the
  121 entries headed `…系列`), whose headings read `<name> Series` and `Seri <name>`, and a review of
  every card text (the card text tables' 1,544 entries): keyword links keep one name each (`╪Clash`,
  `╈Exit`, `╧Perfect Revive`, `╉Afterlife Totem`), 阵营 reads Faction, and the Indonesian follows the
  wording rules in docs/features/indonesian-language.md. Every rewrite passes the runtime's
  `validate_translation`;
- `catalog_additions.json` beside this script: strings a game update added or rewrote that neither
  catalog has, each with an English (`en`) and an Indonesian (`id`) translation. It is generated from a
  scan of a pulled device dump and lists only strings the runtime's `validate_translation` accepts.
  An addition upstream has since translated is left to upstream and reported.
- `catalog_english_fixes.json` beside this script: whole English strings mapped to their corrected form,
  for a slip upstream repeats across hundreds of entries. It holds the verb uses of "Usage" (使用): a Hero
  Card or a count of cards is played ("play a Hero Card", "Play 8 different Cards"), every other card and
  everything else is used ("use a Tactics Card", "Use on a friendly Hero", "use Ancient Coins"), as the
  catalog's own reviewed strings read, and the noun uses ("Usage Rules", "upon Usage") stay. It also
  capitalises the auction-round label, which upstream writes "auction" (第2回合, 首轮拍卖, … in the
  match HUD's round line); `catalog_rewrites.json` carries the Indonesian "lelang" the same way, as
  "Lelang". It applies to the English catalog's `unique` values and
  to each `english_updates` row's new text, never to the row's previous text, which identifies the row.

Edits only the named `unique` entries, byte-for-byte in the decompressed JSON, and checks that nothing
else changed. Idempotent: a fix already present is left as it is. Run from the project root after
merging an upstream `resources/catalog*/catalog.json.gz`:

    .venv\Scripts\python.exe -I -X utf8 tools\research\apply_catalog_fixes.py
"""
import gzip, io, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADDITIONS = json.loads((pathlib.Path(__file__).with_name("catalog_additions.json")).read_text(encoding="utf-8"))
REWRITES = json.loads((pathlib.Path(__file__).with_name("catalog_rewrites.json")).read_text(encoding="utf-8"))
ENGLISH_FIXES = json.loads(
    (pathlib.Path(__file__).with_name("catalog_english_fixes.json")).read_text(encoding="utf-8"))


def indonesian_fixes(u: dict) -> tuple[dict, dict]:
    """The Indonesian catalog's own CHANGE and ADD sets, derived from its current `unique` map <u>."""
    # Labels the user wants in English.
    change = {"棋手": "Chessplayer", "传承": "Inheritance", "阵营祝福": "Faction Blessing"}
    # The Combine keyword link (href=13, 合成) reads Combine everywhere else in the catalog; Yao's card said
    # "ditingkatkan". Only the link label changes.
    yao = "你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。"
    change[yao] = u[yao].replace("<b>ditingkatkan</b>", "<b>Combine</b>")
    assert "<b>Combine</b>" in change[yao]

    # Card texts the 1.5.0.1 update rewrote; the catalog only knows the earlier wording.
    add = {
        "指定1名英雄，场上和其品阶相同的英雄等级+4。":
            "Pilih 1 Hero. Tingkatkan Level semua Hero di papan dengan Tier yang sama sebesar 4.",
        "指定场上1名10级以上的英雄，将其等级随机分配给其他英雄中等级最低的3名（不会分配给同一英雄）。":
            "Tunjuk 1 Hero Level 10 atau lebih dan bagikan Level-nya secara acak ke 3 Hero lain dengan Level terendah"
            " (tidak bisa diberikan ke Hero yang sama).",
    }
    # Build Snowman: 1.5.0.1 made the two Diamond amounts and the Diamond counter placeholders. Derived from
    # the catalog's own translation of the old wording so it follows upstream's latest phrasing.
    old_zh = ("持有时每场战斗后累积奖励：\n胜利：钻石<color=#99DEB0>+10</color>、全体英雄等级<color=#99DEB0>+20</color>\n"
              "失败：钻石<color=#99DEB0>+3</color>、全体英雄等级<color=#99DEB0>+60</color>\n"
              "平局不计入。打出后领取全部累积（当前钻石{810299Diamond:0}，等级{810299Level:0}）。")
    new_zh = (old_zh.replace("钻石<color=#99DEB0>+10<", "钻石<color=#99DEB0>+{0|10}<")
                    .replace("钻石<color=#99DEB0>+3<", "钻石<color=#99DEB0>+{0|3}<")
                    .replace("{810299Diamond:0}", "{810299Diamond:0|0}"))
    old_id = u[old_zh]
    for amount in ("10", "3"):
        marker = f"<color=#99DEB0>+{amount}</color>"
        # The Diamond amount is the first occurrence on its line (the Level amount follows it).
        lines = old_id.split("\n")
        line = 1 if amount == "10" else 2
        assert marker in lines[line], (amount, lines)
        lines[line] = lines[line].replace(marker, f"<color=#99DEB0>+{{0|{amount}}}</color>", 1)
        old_id = "\n".join(lines)
    assert old_id.count("{810299Diamond:0}") == 1
    add[new_zh] = old_id.replace("{810299Diamond:0}", "{810299Diamond:0|0}")
    for zh in add:
        assert zh not in u or u[zh] == add[zh], f"upstream now translates {zh!r}; review it"
    return change, add


def english_fixes(out: bytes) -> tuple[bytes, int]:
    """<out> with `ENGLISH_FIXES` applied to `unique` values and `english_updates` new texts; and the count.

    The catalog is plain `json.dumps` output, so it is re-serialised whole; the round trip is checked
    first, and afterwards that only those two fields changed.
    """
    data = json.loads(out)
    assert json.dumps(data, ensure_ascii=False).encode() == out, "catalog no longer round-trips through json"
    unique, rows = data["unique"], data["english_updates"]
    fixed = 0
    for zh, value in unique.items():
        if value in ENGLISH_FIXES:
            unique[zh] = ENGLISH_FIXES[value]
            fixed += 1
    for row in rows:
        if row[3] in ENGLISH_FIXES:
            row[3] = ENGLISH_FIXES[row[3]]
            fixed += 1
    before = json.loads(out)
    assert [r[:3] + r[4:] for r in rows] == [r[:3] + r[4:] for r in before["english_updates"]]
    assert unique.keys() == before["unique"].keys()
    assert {k: v for k, v in data.items() if k not in ("unique", "english_updates")} == \
        {k: v for k, v in before.items() if k not in ("unique", "english_updates")}
    return json.dumps(data, ensure_ascii=False).encode(), fixed


def apply(path: pathlib.Path, lang: str) -> None:
    raw = gzip.open(path).read()
    u = json.loads(raw)["unique"]
    change, add = indonesian_fixes(u) if lang == "id" else ({}, {})
    for zh, entry in REWRITES.items():
        if lang in entry:
            assert zh in u, f"upstream no longer has {zh!r}; drop its rewrite"
            change[zh] = entry[lang]
    upstream = [zh for zh, entry in ADDITIONS.items() if lang in entry and zh in u and u[zh] != entry[lang]]
    for zh, entry in ADDITIONS.items():
        if lang in entry and zh not in u:
            add[zh] = entry[lang]

    out = raw
    changed = 0
    for zh, value in change.items():
        if u[zh] == value:
            continue
        changed += 1
        old = f'{json.dumps(zh, ensure_ascii=False)}: {json.dumps(u[zh], ensure_ascii=False)}'.encode()
        assert out.count(old) == 1, zh
        out = out.replace(old, f'{json.dumps(zh, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)}'.encode())
    missing = {k: v for k, v in add.items() if k not in u}
    anchor = b'"unique": {'
    assert out.count(anchor) == 1
    out = out.replace(anchor, anchor + b"".join(
        f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}, ".encode() for k, v in missing.items()))
    expected = json.loads(raw)
    expected["unique"].update(change)
    expected["unique"].update(add)
    assert json.loads(out) == expected, "something other than the named entries changed"
    fixed = 0
    if lang == "en":
        out, fixed = english_fixes(out)
    if out != raw:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(out)
        path.write_bytes(buf.getvalue())
    print(f"{path.parent.name}: {changed} changed, {len(missing)} added "
          f"({sum(1 for k in missing if k in ADDITIONS)} from catalog_additions.json), "
          f"{fixed} strings fixed from catalog_english_fixes.json")
    for zh in upstream:
        print(f"  upstream now translates {zh[:30]!r}; its translation kept")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["en", "id"]
    for lang in targets:
        apply(ROOT / "resources" / ("catalog" if lang == "en" else "catalog_id") / "catalog.json.gz", lang)
