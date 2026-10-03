"""Third patch pass: Chinese strings in assets the PC catalog has no localization table for.

* Any string that exactly matches a catalog translation (`catalog.unique`) gets the official English.
* The AI opponent name list is romanised with pinyin, because the catalog has no official translation
  for it.
* UI text components in Unity prefabs get the official English for exact matches, when a package is
  listed as carrying them.

Assets are rewritten with the same chunk count they already have (`device_extensions.write_assets`).

`SAFE_ASSETS` is an allowlist and `CANDIDATE_ASSETS` the measured queue for it: an asset joins the
allowlist only after a device cycle has looked at the screen it feeds, and a cycle turns one candidate
on for one run through `resolve_candidates` rather than by editing the allowlist.
"""
from __future__ import annotations

import re
import struct
import unicodedata
from pathlib import Path

import pb_text

# Protobuf list of the ~11k nicknames shown for AI opponents ("chessplayers") in matches.
BOT_NAME_ASSETS = {0x2D1113B0AD51A562}
# The assets this pass may rewrite. Every one was put on a phone and watched, because nothing about an
# asset predicts what rewriting it costs.
SAFE_ASSETS = BOT_NAME_ASSETS | {
    0xA1987F488164E53A,  # display-text table {id, text, #key#}
    0x1C8F7FFF7BDEF14D,  # post-match compliments
    0xB5D856BFDF22400D,  # rule pages
}
# Rewrites that were tried on device and withdrawn (2026-09-30 / 10-01). Each was a single-variable
# device cycle: the same build, with one more asset enabled, watching the screen it feeds.
#   0x5214339F97C419ED   task names: translating it makes a tournament replay SIGSEGV -- signal 11,
#                        pss ~1.3 GB, ~30 s into the replay, every time. The same build without it
#                        replays fine, which is what put it here.
#   0x10271B050169A7B7, 0x0FDA07B7C51E4AC5, 0xDEE91C1DE999F3AF, 0xD9A68213BB843F61   chessplayer
#                        skills: the chessplayer skill-description button disappears.
#   0x5B7E509D10BD722F, 0xA3B34BE9879BE25B, 0x721918D44EDAB146   mail / quiz / "not open yet"
#                        notices: no game button after pressing start, and a blank encyclopedia.
#   0x13429059252DC6EB, 0xE0FF23C02C95D892   package 4: these go through the in-place `write_assets`,
#                        which does not verify its own write, so package 4 stays pristine.
# The same class of edit broke the login screen (a Chinese string there is a lookup key rather than a
# label), the Card menu (grey placeholder cards: hero role guide DD11D75B / CA340C43 / BBFD4BE9 /
# CAC6E38D), and every package-19 prefab label tried (initial loading stalls; faction names rewrite as
# "stack corruption detected"). Not tried: guide triggers 9E141D55, buff definitions C11D0D14, nickname
# parts 87C2793F, damage-type tables 7B40D34D / 1BAEBF0F / EAF99621, 3F4DD9B1, newbie unlock rewards
# 41974B12, the small label tables 8B5C2394 / A07BC11B / 4CEF98BE / 63922EF4 / 7E3F57D7 / 3914DBBF /
# 14DEEB2E. A note claiming "verified on device" is only as good as the screens it was verified on.
# Those fifteen are the short forms. CANDIDATE_ASSETS resolves them to the hashes the packages carry
# and records each one's measurement -- distinct Chinese strings it holds (of the fields that carry
# them, since labels repeat) and how many of those the catalog has an official English for, which is the
# share this pass could translate and therefore what a cycle buys -- so a cycle starts from the numbers
# rather than from the note. Measured against the downloaded layer, game data 1.4.0.1, by
# tools/research/extra_text_candidates.py.
# The order is the order to run the cycles in: the four label tables first, because they are display
# labels the catalog mostly or entirely covers, and the other eleven only after a cycle says the class is
# safe. Those eleven are step, buff, nickname and damage identifiers the catalog reaches 1.5-9% of, so a
# cycle on one would add a handful of strings and risk a screen the note above already lists a synonym of.
CANDIDATE_ASSETS: dict[int, str] = {
    0x63922EF4D4C86526: "3 of 3, and a 90-byte asset -- Transmog / Treasure Hunt / Limited Time; the "
                        "cheapest honest signal there is. Its three keys are referenced by "
                        "`C7052167E428F9D5` (package 1, 137 bytes) with no date window, so a screen that "
                        "draws it is reachable -- unlike 3914DBBF below. Measured 2026-10-02.",
    0x4CEF98BEC79CB48C: "4 of 12 (15 fields) -- Tier / Hero Faction / Keyword / Wanxiang Quiz. Holds no "
                        "`#key#` rows at all: its values are inline, like the withdrawn config assets "
                        "rather than like a lookup table, which is why `translate_table` refuses it",
    0x7E3F57D727FA8625: "1 of 1 -- Props",
    # Unobservable, measured on device 2026-10-02. `3914DBBFECD1E54D` is a one-row lookup table,
    # `#07B0CCFD72A346C9#` -> 高光表情, and a sweep of all 277 packages finds that key referenced in
    # exactly one asset: `3644C4ACF0410B1E`, a 239-byte draw-type row windowed 2025-09-10 to 2025-10-10
    # whose icon is `ArtHub/Icon/System/ExternalGame/Draw/Icon_Draw_Type_RYXZ` (日月行者). The window
    # closed a year before this build, so no live screen can draw the label and a cycle cannot produce a
    # verdict for it. Do not spend a phone on this hash; the finding is the measurement.
    0x3914DBBFECD1E54D: "1 of 1 -- Highlight Expression; UNOBSERVABLE -- its only referencing row is a "
                        "draw type windowed 2025-09-10 to 2025-10-10, long expired (2026-10-02)",
    0x41974B124E0053E0: "15 of 25 (42 fields) -- the newbie unlock-reward list; only a new account sees it",
    0x7B40D34D9DF271FF: "3 of 53 (65 fields) -- Damage / Invincible / Magic Damage Can Crit; the other "
                        "50 are designer shorthand",
    0x1BAEBF0F2F2454FD: "3 of 49 (59 fields) -- the same family as above",
    0xEAF9962143676693: "3 of 53 (65 fields) -- the same family as above",
    0xA07BC11BA94A5969: "5 of 10 -- no screen identified yet",
    0x14DEEB2E14F20E3C: "2 of 3, in a 115 KB asset -- two labels for the price of a big one",
    0x8B5C239421E23186: "9 of 283 -- guide step names (S1 lineup - use button): logic, not labels",
    0x9E141D556DA884E7: "23 of 596 (632 fields) -- guide triggers: the same class",
    0xC11D0D1498204926: "35 of 587 (859 fields) -- buff definitions, mostly designer shorthand",
    0x87C2793FEEDCA60D: "20 of 678 (2199 fields) -- nickname parts, and 3% of them are labels",
    0x3F4DD9B1D383FD83: "1 of 2, and it is reachable (package 4) -- but that is the package the note "
                        "withdrew: its write path does not verify its own write",
}
# Values that are logic rather than labels. A skill-config message stores 空 (empty) in the slots that
# carry no skill, and the client reads that value back instead of treating it as text. Guarding it did
# not by itself fix the skill button -- withdrawing those assets did -- but the allowlist above was
# validated on device with this guard in place, so removing it needs its own cycle.
SKIPPED_STRINGS = {"空"}
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


class UnknownCandidate(ValueError):
    """Raised when a device cycle names an asset that is not on the measured candidate list."""


def resolve_candidates(selector: str) -> list[int]:
    """The candidate asset hashes <selector> names, for one device cycle.

    <selector> is one or more hexadecimal prefixes separated by commas, each at least four digits and
    each matching exactly one of CANDIDATE_ASSETS. A cycle turns on what was measured rather than what
    was typed, so a prefix that is ambiguous or names nothing is refused instead of guessed at.
    """
    resolved: list[int] = []
    for token in (part.strip().upper() for part in re.split(r"[,\s]+", selector) if part.strip()):
        if not re.fullmatch(r"[0-9A-F]{4,16}", token):
            raise UnknownCandidate(f"{token!r} is not a hexadecimal asset hash")
        matches = [file_hash for file_hash in CANDIDATE_ASSETS if f"{file_hash:016X}".startswith(token)]
        if len(matches) != 1:
            raise UnknownCandidate(f"{token!r} names {len(matches)} candidates, and a cycle enables one")
        if matches[0] not in resolved:
            resolved.append(matches[0])
    if not resolved:
        raise UnknownCandidate("no asset named")
    return resolved


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
        if text in SKIPPED_STRINGS:
            return None
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
        if text in SKIPPED_STRINGS:
            return None
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


def plan_package(package, catalog, skip: set[int], log=None,
                 candidates: frozenset[int] = frozenset()) -> dict[int, bytes]:
    """New raw bytes for every allowlisted protobuf asset in <package> that can be translated.

    <candidates> are the CANDIDATE_ASSETS a device cycle has turned on for this run. They join the
    allowlist for the run and are not added to it: `SAFE_ASSETS` grows only when a cycle's screen has
    been looked at, so no run can ship an asset that was never put on a phone.
    """
    from qts_relocate import read_raw
    from resource_tokens import expand_tokens

    allowed = SAFE_ASSETS | candidates
    slots = package.build_slot_map()
    jobs: dict[int, bytes] = {}
    for file_hash in slots:
        entry = package.entries.get(file_hash)
        if entry is None or file_hash in skip or file_hash not in allowed or entry.compression not in (1, 4):
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


def extend_text(game: Path, catalog, output: Path, log, skip_packages: set[str] = frozenset(),
                candidates: frozenset[int] = frozenset()) -> list[dict]:
    """Translate uncovered protobuf assets in every package of <game>; returns summary entries.

    <candidates> is the device cycle's enablement, passed through to `plan_package`.
    """
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
        jobs = plan_package(package, catalog, skip, log, candidates=candidates)
        if package_dir.name in UNITY_TEXT_PACKAGES:
            jobs.update(plan_unity_package(package, catalog))
        if not jobs:
            continue
        count = relocate_assets(package, output, jobs, log)
        if count:
            reports.append({"package_id": package.package_id, "mode": "extra-text",
                            "stage_report": {"status": "relocated", "replacement_count": count}})
    return reports
