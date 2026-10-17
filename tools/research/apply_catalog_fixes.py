r"""Re-apply this repo's catalog fixes and additions on top of whatever catalogs upstream ships.

Two kinds of change, both keyed by the Chinese source string in a catalog's `unique` map:

- the Indonesian fixes below (`CHANGE`, `ADD`): labels the user wants in English, and the 1.5.0.1 card
  texts the catalog only knew in their earlier wording, and the Multi-Faction/General talent texts
  and Summon talent texts
  (`SERIES_FIXES_ID`; `SERIES_FIXES_EN` repairs the English catalog's garbled Diversity Advantage and Twin Contract);
- `catalog_additions.json` beside this script: strings a game update added or rewrote that neither
  catalog has, each with an English (`en`) and an Indonesian (`id`) translation. It is generated from a
  scan of a pulled device dump and lists only strings the runtime's `validate_translation` accepts.
  An addition upstream has since translated is left to upstream and reported.

Edits only the named `unique` entries, byte-for-byte in the decompressed JSON, and checks that nothing
else changed. Idempotent: a fix already present is left as it is. Run from the project root after
merging an upstream `resources/catalog*/catalog.json.gz`:

    .venv\Scripts\python.exe -I -X utf8 tools\research\apply_catalog_fixes.py
"""
import gzip, io, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADDITIONS = json.loads((pathlib.Path(__file__).with_name("catalog_additions.json")).read_text(encoding="utf-8"))

_G = "<color=#99DEB0>{}</color>".format
# Diversity Advantage (多样性优势): both catalogs carry a garbled machine translation.
DIVERSITY_ZH = f"{_G('多阵营系列')}\n战斗开始时，若己方有{_G('至少2个')}阵营，所有英雄获得{_G('20')}×阵营数的等级。"
_TOTEM = "<a href=321>{}</a>".format(_G("╉图腾"))
_TOTEM_ID = "<a href=321>{}</a>".format(_G("╉Totem"))
_TEMP_LEVEL = "<a href=3130011>{}</a>".format
# Twin Contract (双生契约): both catalogs carry a garbled machine translation.
TWIN_CONTRACT_ZH = (f"{_G('召唤系列')}\n召唤单位（召唤物、图腾）时，额外获得{_G('100')}+召唤者等级×{_G('80%')}的"
                    f"{_TEMP_LEVEL(_G('═临时等级'))}，每回合前{_G('15')}个召唤单位获得{_G('╧完美复生')}。")
SERIES_FIXES_EN = {
    DIVERSITY_ZH: f"{_G('Multi-Faction Series')}\nAt the start of Battle, if you have {_G('at least 2')} Factions,"
                  f" All Heroes gain {_G('20')} × the number of Factions in levels.",
    TWIN_CONTRACT_ZH: f"{_G('Summon Series')}\nWhen summoning a unit (summons, Totems), gain an extra {_G('100')}"
                      f" + the summoner's Level × {_G('80%')} {_TEMP_LEVEL(_G('═Temporary Level'))}. The first"
                      f" {_G('15')} summoned units each Round gain {_G('╧Perfect Revive')}.",
}
SERIES_FIXES_ID = {
    DIVERSITY_ZH: f"{_G('Seri Multi-Faction')}\nDi awal Pertempuran, jika kamu punya {_G('minimal 2')} Faction,"
                  f" semua Hero mendapatkan Level sebanyak {_G('20')} × jumlah Faction.",
    f"{_G('多阵营系列')}\n回合开始时，你每有{_G('1个')}阵营，所有英雄等级{_G('+7')}。":
        f"{_G('Seri Multi-Faction')}\nDi awal Ronde, untuk setiap {_G('1')} Faction yang kamu miliki,"
        f" semua Hero mendapatkan {_G('+7')} Level.",
    f"{_G('多阵营系列')}\n场上每存在{_G('1个')}不同阵营，己方英雄物理攻击力和法术攻击力{_G('+10%')}。":
        f"{_G('Seri Multi-Faction')}\nUntuk setiap {_G('1')} Faction berbeda di papan, Hero kamu mendapatkan"
        f" {_G('+10%')} Physical Attack dan Magic Attack.",
    f"{_G('多阵营系列')}\n立即获得{_G('1张照影')}，回合开始时，每有{_G('1个')}阵营，获得{_G('1张照影')}。":
        f"{_G('Seri Multi-Faction')}\nLangsung dapatkan {_G('1 Shadow-Cast')}. Di awal Ronde, dapatkan"
        f" {_G('1 Shadow-Cast')} untuk setiap {_G('1 Faction')} yang kamu miliki.",
    f"{_G('通用系列')}\n回合开始时，随机获得{_G('4张')}你{_G('人数最多阵营')}的英雄牌。":
        f"{_G('Seri General')}\nDi awal Ronde, dapatkan {_G('4 Hero Card')} acak dari"
        f" {_G('Faction dengan Hero terbanyak')} kamu.",
    TWIN_CONTRACT_ZH: f"{_G('Seri Summon')}\nSaat memanggil unit (Summon, Totem), dapatkan tambahan {_G('100')}"
                      f" + Level pemanggil × {_G('80%')} {_TEMP_LEVEL(_G('═Temporary Level'))}. {_G('15')} unit"
                      f" Summon pertama setiap Ronde mendapatkan {_G('╧Perfect Revive')}.",
    f"{_G('召唤系列')}\n战斗中入场的召唤物存活{_G('8秒')}后，{_G('变为其召唤者（无卡牌效果）')}并保留等级，"
    f"每场战斗最多{_G('10次')}。":
        f"{_G('Seri Summon')}\nSummon yang masuk saat Pertempuran dan bertahan {_G('8 detik')}"
        f" {_G('berubah menjadi pemanggilnya (tanpa efek kartu)')} dan mempertahankan Level-nya."
        f" Maksimal {_G('10 kali')} per Pertempuran.",
    f"{_G('召唤系列')}\n每召唤{_G('1个')}单位（仅召唤物、{_TOTEM}），和召唤者同阵营的己方英雄获得{_G('2%')}"
    f"最大生命值（上限{_G('40%')}）。":
        f"{_G('Seri Summon')}\nSetiap kali {_G('1')} unit dipanggil (hanya Summon dan {_TOTEM_ID}), Hero sekutu"
        f" dari Faction yang sama dengan pemanggil mendapatkan {_G('2%')} Max HP (maksimal {_G('40%')}).",
    f"{_G('召唤系列')}\n每召唤{_G('1个')}单位（仅召唤物，{_TOTEM}），下回合开始时所有英雄等级{_G('+3')}。":
        f"{_G('Seri Summon')}\nUntuk setiap {_G('1')} unit yang dipanggil (hanya Summon dan {_TOTEM_ID}),"
        f" semua Hero mendapatkan {_G('+3')} Level di awal Ronde berikutnya.",
    f"{_G('召唤系列')}\n立即获得{_G('4张')}召唤、{_TOTEM}系列英雄牌。{_G(f'召唤单位时（含召唤物，{_TOTEM}）')}，"
    f"获得{_G('1张')}召唤、{_TOTEM}系列英雄牌（每回合最多{_G('4张')}）。":
        f"{_G('Seri Summon')}\nLangsung dapatkan {_G('4')} Hero Card seri Summon atau {_TOTEM_ID}."
        f" {_G(f'Saat memanggil unit (termasuk Summon dan {_TOTEM_ID})')}, dapatkan {_G('1')} Hero Card seri"
        f" Summon atau {_TOTEM_ID} (maksimal {_G('4')} per Ronde).",
}


def indonesian_fixes(u: dict) -> tuple[dict, dict]:
    """The Indonesian catalog's own CHANGE and ADD sets, derived from its current `unique` map <u>."""
    # Labels the user wants in English.
    change = {"棋手": "Chessplayer", "传承": "Inheritance", "阵营祝福": "Faction Blessing"}
    # The Combine keyword link (href=13, 合成) reads Combine everywhere else in the catalog; Yao's card said
    # "ditingkatkan". Only the link label changes.
    yao = "你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。"
    change[yao] = u[yao].replace("<b>ditingkatkan</b>", "<b>Combine</b>")
    assert "<b>Combine</b>" in change[yao]
    # The Multi-Faction and General talent cards: the series label read "Seri Wajah Multi-"/"Seri Multi- Faction"
    # and Diversity Advantage's text was machine-translation debris ("Di Leach2Oneone.♪ The camp").
    change.update(SERIES_FIXES_ID)

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


def apply(path: pathlib.Path, lang: str) -> None:
    raw = gzip.open(path).read()
    u = json.loads(raw)["unique"]
    change, add = indonesian_fixes(u) if lang == "id" else (dict(SERIES_FIXES_EN), {})
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
    if out != raw:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(out)
        path.write_bytes(buf.getvalue())
    print(f"{path.parent.name}: {changed} changed, {len(missing)} added "
          f"({sum(1 for k in missing if k in ADDITIONS)} from catalog_additions.json)")
    for zh in upstream:
        print(f"  upstream now translates {zh[:30]!r}; its translation kept")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["en", "id"]
    for lang in targets:
        apply(ROOT / "resources" / ("catalog" if lang == "en" else "catalog_id") / "catalog.json.gz", lang)
