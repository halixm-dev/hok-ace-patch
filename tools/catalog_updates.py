"""Exact updates for previously installed translations and for untranslated format rows, merged into
the catalog in memory.

Each update names measured catalog tables, row keys and the full previous text. The runtime's
english_updates path checks all three before replacing a value, so reruns need no pristine data.
"""
from __future__ import annotations

# Measured in both layers of package 1 on 2026-10-17 (game data 1.6.0.1).
YAO_ROWS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("23C9A9DEBB3BF40C", ("#FCC727E86456E964#", "#FCC762A70B7CDE1F#")),
    ("28D9F8B02CAA94E2", ("#23F727E86456E964#", "#23F762A70B7CDE1F#")),
    ("3D889D9ABCEDE2A8", ("#5AD127E86456E964#", "#5AD162A70B7CDE1F#")),
    ("4476EC307E0F2142", ("#801D27E86456E964#", "#801D62A70B7CDE1F#")),
    ("57C03656175B0904", ("#6D3B27E86456E964#", "#6D3B62A70B7CDE1F#")),
    ("9799DF91AB4F4FA3", ("#5A2E27E86456E964#", "#5A2E62A70B7CDE1F#")),
    ("9C4EC654D5454B46", ("#182527E86456E964#", "#182562A70B7CDE1F#")),
    ("9CAA7228F782AB5A", ("#BC6D27E86456E964#", "#BC6D62A70B7CDE1F#")),
    ("A07B2B9F994FB0ED", ("#6E6027E86456E964#", "#6E6062A70B7CDE1F#")),
    ("A336359CD92A858E", ("#8E5527E86456E964#", "#8E5562A70B7CDE1F#")),
    ("C13DF45E3492CA0C", ("#FBF327E86456E964#", "#FBF362A70B7CDE1F#")),
)
YAO_SOURCE = "你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。"
YAO_PREVIOUS = "Your Heroes gain +1 Level when <a href=13><color=#ffffff>╦<b>upgraded</b></color></a>."

# A match's Card Stats panel draws each line as the operation (CardStaticsOperate_Buy 购买, _Use 使用)
# and the card name joined with no space, which reads "购买狂铁" in Chinese and "BuyBiron" translated.
# The format row holds no Chinese, so only an exact row update reaches it, and it applies to every
# language. Measured in package 1 (prime-only) on 2026-10-30 (game data 1.8.0.1).
CARD_OPERATE_ROW = ("DD5B5EDFBB69FEED", "Dps_CardOperate")
CARD_OPERATE_PREVIOUS = "<color=#ffffff>{0}</color><color=#FFFFFFB2>{1}</color>"
CARD_OPERATE_TARGET = "<color=#ffffff>{0}</color> <color=#FFFFFFB2>{1}</color>"


def apply(data: dict, code: str) -> int:
    """Add missing exact update rows after terminology; upstream update rows win.

    Indonesian already uses Combine, so it needs no Yao migration. Only known catalog tables may
    receive updates. Yao's target comes from the current catalog, keeping future wording authoritative.
    The Card Stats row has no Chinese source to carry, so it leaves index 4 out; measured, the runtime
    refuses the row as `invalid_translation` with an empty source there.
    """
    rows = data.setdefault("english_updates", [])
    existing = {tuple(row[:3]) for row in rows}
    known = set(data.get("table_hashes", []))
    added = 0

    def add(row: list[str]) -> None:
        nonlocal added
        if row[0] in known and tuple(row[:3]) not in existing:
            rows.append(row)
            existing.add(tuple(row[:3]))
            added += 1

    add([*CARD_OPERATE_ROW, CARD_OPERATE_PREVIOUS, CARD_OPERATE_TARGET])
    target = data.get("unique", {}).get(YAO_SOURCE)
    if code != "en" or not target or target == YAO_PREVIOUS:
        return added
    for asset, keys in YAO_ROWS:
        for key in keys:
            add([asset, key, YAO_PREVIOUS, target, YAO_SOURCE])
    return added
