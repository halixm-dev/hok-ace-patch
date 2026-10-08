r"""Re-apply this branch's Indonesian catalog fixes on top of whatever catalog upstream ships.

Edits only the named `unique` entries, byte-for-byte in the decompressed JSON, and checks that nothing
else changed. Idempotent: a fix already present is left as it is. Run from the project root after
merging an upstream `resources/catalog_id/catalog.json.gz`:

    .venv\Scripts\python.exe -I -X utf8 tools\research\apply_catalog_fixes.py
"""
import gzip, io, json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "resources/catalog_id/catalog.json.gz"
raw = gzip.open(path).read()
before = json.loads(raw)
u = before["unique"]

# Labels the user wants in English.
CHANGE = {"棋手": "Chessplayer", "传承": "Inheritance", "阵营祝福": "Faction Blessing"}
# The Combine keyword link (href=13, 合成) reads Combine everywhere else in the catalog; Yao's card said
# "ditingkatkan". Only the link label changes.
YAO = "你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。"
CHANGE[YAO] = u[YAO].replace("<b>ditingkatkan</b>", "<b>Combine</b>")
assert "<b>Combine</b>" in CHANGE[YAO]

# Card texts the 1.5.0.1 update rewrote; the catalog only knows the earlier wording.
ADD = {
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
ADD[new_zh] = old_id.replace("{810299Diamond:0}", "{810299Diamond:0|0}")

out = raw
for zh, value in CHANGE.items():
    if u[zh] == value:
        continue
    old = f'{json.dumps(zh, ensure_ascii=False)}: {json.dumps(u[zh], ensure_ascii=False)}'.encode()
    assert out.count(old) == 1, zh
    out = out.replace(old, f'{json.dumps(zh, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)}'.encode())
missing = {k: v for k, v in ADD.items() if k not in u}
for zh in ADD:
    assert zh not in u or u[zh] == ADD[zh], f"upstream now translates {zh!r}; review it"
anchor = b'"unique": {'
assert out.count(anchor) == 1
out = out.replace(anchor, anchor + b"".join(
    f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}, ".encode() for k, v in missing.items()))
expected = json.loads(raw)
expected["unique"].update(CHANGE)
expected["unique"].update(ADD)
assert json.loads(out) == expected, "something other than the named entries changed"
if out != raw:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as g:
        g.write(out)
    open(path, "wb").write(buf.getvalue())
for k in list(CHANGE) + list(ADD):
    print(repr(k[:30]), "->", repr(expected["unique"][k][:90]))
