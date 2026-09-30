"""Third patch pass: Chinese strings in assets the PC catalog has no localization table for.

* Any string that exactly matches a catalog translation (`catalog.unique`) gets the official English.
* The AI opponent name list is romanised with pinyin, because the catalog has no official translation
  for it.
* UI text components in Unity prefabs get the official English for exact matches, when a package is
  listed as carrying them.

Assets are rewritten with the same chunk count they already have (`device_extensions.write_assets`).
"""
from __future__ import annotations

import re
import struct
import unicodedata
from pathlib import Path

import pb_text

# Protobuf list of the ~11k nicknames shown for AI opponents ("chessplayers") in matches.
BOT_NAME_ASSETS = {0x2D1113B0AD51A562}
# Only assets verified to hold display text. Replacing matching strings in the other config assets
# broke the login screen: some Chinese strings there are lookup keys rather than labels.
SAFE_ASSETS = BOT_NAME_ASSETS | {
    0xE0FF23C02C95D892,  # skin names and descriptions (package 4)
    0xA1987F488164E53A,  # display-text table {id, text, #key#}
}
# Display-only assets whose strings the PC catalog translates; each set verified on device
# (2026-09-29: loading reaches "Click to Enter Game", the Card menu renders).
# Stall initial loading, UI disappearing around 40-80%: newbie unlock rewards 41974B12, and one of
# the small label tables 8B5C2394 / A07BC11B / 4CEF98BE / 63922EF4 / 7E3F57D7 / 3914DBBF / 14DEEB2E.
# Break the Card menu, leaving grey placeholder cards: hero role guide DD11D75B / CA340C43 / BBFD4BE9
# / CAC6E38D.
# Not tried: guide triggers 9E141D55, buff definitions C11D0D14, nickname parts 87C2793F, damage-type
# tables 7B40D34D / 1BAEBF0F / EAF99621, 3F4DD9B1.
DISPLAY_ASSETS = {
    0x5B7E509D10BD722F,  # system mail titles and bodies
    0xA3B34BE9879BE25B,  # quiz questions and answers
    0x10271B050169A7B7, 0x0FDA07B7C51E4AC5, 0xDEE91C1DE999F3AF, 0xD9A68213BB843F61,  # chessplayer skills
    0x13429059252DC6EB,  # arena and skin flavour text (package 4)
    0x721918D44EDAB146,  # "not open yet" notices
    0x1C8F7FFF7BDEF14D,  # post-match compliments
    0x5214339F97C419ED,  # task names
    0xB5D856BFDF22400D,  # rule pages
}
SAFE_ASSETS |= DISPLAY_ASSETS
# Packages whose Unity prefabs carry UI labels (faction names, buttons). Empty, and it stays that way:
# rewriting every package-19 prefab label stalled the lobby's loading, and rewriting only the faction
# names in the 15 prefabs that show them crashes the game at start with "stack corruption detected"
# (tested 2026-09-29). Package-19 prefabs are left untouched.
UNITY_TEXT_PACKAGES: set[str] = set()
# Catalog translations that read a name as a word.
OFFICIAL_FIXES = {"蝉儿": "Chan'er"}

# Skill-editor labels (10) and gameplay scripts (14): Chinese there is logic, not display text.
EXCLUDED_PACKAGES = {"10", "14"}
_CJK_RUN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")


def pinyin_name(text: str) -> str:
    """Romanise the Chinese runs in <text>, for names the catalog does not translate."""
    from pypinyin import Style, lazy_pinyin

    def romanise(match: re.Match) -> str:
        syllables = lazy_pinyin(match.group(0), style=Style.NORMAL, v_to_u=True)
        return "".join(s.capitalize() for s in syllables)

    ascii_text = unicodedata.normalize("NFKC", text)
    return _CJK_RUN.sub(romanise, ascii_text).replace("ü", "u")


def translator_for(file_hash: int, catalog):
    """The translation for one string in one asset: official first, romanisation for bot names."""
    official = catalog.unique

    def translate(text: str) -> str | None:
        if text in OFFICIAL_FIXES:
            return OFFICIAL_FIXES[text]
        if text in official:
            return official[text]
        if file_hash in BOT_NAME_ASSETS:
            return pinyin_name(text)
        return None

    return translate


def official_only(catalog):
    """The catalog's official English for one string, with no romanisation fallback."""

    def translate(text: str) -> str | None:
        return OFFICIAL_FIXES.get(text) or catalog.unique.get(text)

    return translate


def plan_unity_package(package, catalog) -> dict[int, bytes]:
    """New raw bytes for Unity files whose UI components hold officially translated strings."""
    from qts_relocate import read_raw
    from unity_text import SerializedFile, UnsupportedFile

    slots = package.build_slot_map()
    translate = official_only(catalog)
    jobs: dict[int, bytes] = {}
    for file_hash in slots:
        entry = package.entries.get(file_hash)
        if entry is None or entry.compression not in (1, 4):
            continue
        raw = read_raw(package, slots, file_hash)
        if raw is None:
            continue
        try:
            new, changed = SerializedFile(raw).rewrite(translate)
        except (UnsupportedFile, struct.error, ValueError):
            continue
        if changed:
            jobs[file_hash] = new
    return jobs


def plan_package(package, catalog, skip: set[int], log=None) -> dict[int, bytes]:
    """New raw bytes for every allowlisted protobuf asset in <package> that can be translated."""
    from qts_relocate import read_raw
    from resource_tokens import expand_tokens

    slots = package.build_slot_map()
    jobs: dict[int, bytes] = {}
    for file_hash in slots:
        entry = package.entries.get(file_hash)
        if entry is None or file_hash in skip or file_hash not in SAFE_ASSETS or entry.compression not in (1, 4):
            continue
        raw = read_raw(package, slots, file_hash)
        if raw is None or not pb_text.CJK.search(raw.decode("utf-8", "ignore")):
            continue
        try:
            new, changed = pb_text.rewrite(raw, translator_for(file_hash, catalog))
        except pb_text.NotMessage:
            continue
        if changed:
            # The replacement comes from the catalog verbatim, so it carries the same {Energy}-style
            # tokens the staged path has to expand; the client would otherwise render them in Chinese.
            jobs[file_hash] = expand_tokens(new, log)
    return jobs


def extend_text(game: Path, catalog, output: Path, log, skip_packages: set[str] = frozenset()) -> list[dict]:
    """Translate uncovered protobuf assets in every package of <game>; returns summary entries."""
    from device_extensions import relocate_assets
    from wxq_patch.qtsvfs import QtsPackage

    skip = set(catalog.known) | set(catalog.graphics)
    reports = []
    root = game / "WXQ_Data" / "Package" / "builtin"
    for package_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        if package_dir.name in EXCLUDED_PACKAGES or package_dir.name in skip_packages:
            continue
        try:
            package = QtsPackage(package_dir)
        except Exception:  # noqa: BLE001 - packages without a readable index are not ours to patch
            continue
        if len(package.shard_paths) != 1:
            continue
        jobs = plan_package(package, catalog, skip, log)
        if package_dir.name in UNITY_TEXT_PACKAGES:
            jobs.update(plan_unity_package(package, catalog))
        if not jobs:
            continue
        count = relocate_assets(package, output, jobs, log)
        if count:
            reports.append({"package_id": package.package_id, "mode": "extra-text",
                            "stage_report": {"status": "relocated", "replacement_count": count}})
    return reports
