"""Third patch pass: Chinese strings in assets the PC catalog has no localization table for.

* Any string that exactly matches a catalog translation (`catalog.unique`) gets the official English.
* The AI opponent name list is romanised with pinyin, because the catalog has no official translation
  for it.
* UI text components in Unity prefabs get the official English for exact matches, when a package is
  listed as carrying them.
* A Lua UI script that hard-codes a label (`SCRIPT_LABELS`) gets that one literal replaced, and one that
  joins words the Chinese way (`SCRIPT_EDITS`) gets that one literal edited.
* A lineup bin (`lineup_codes.LINEUP_BINS`), when a cycle enables it, gets the text inside its share
  codes and rows translated and its checksum resealed (`rewrite_config`).

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

import lineup_codes
import pb_text

# Protobuf list of the ~11k nicknames shown for AI opponents ("chessplayers") in matches.
BOT_NAME_ASSETS = {0x2D1113B0AD51A562}
# The config assets this pass may rewrite. Every one has to be put on a phone and watched, because nothing
# about an asset predicts what rewriting it costs. All four cleared before 2026-10-05 were withdrawn
# (below); a candidate joins only after a cycle clears it.
#   0xF79FB1A213A9DA90   ResSeasonAILineupDataBin, the Official recommendation lineups: share codes and
#                        row text translated, fields 1 and 4 resealed (`lineup_codes.rewrite_bin`).
#                        Cleared 2026-10-21, Xiaomi M2007J3SG, Android 12, data 1.6.0.1, English and
#                        Indonesian, each against its control: Newbie and Advanced read translated, a
#                        lineup's detail draws, Use puts it on the board, copy and import work, and a match
#                        ends without the QTS-failure popup. A lineup already in My lineups keeps the
#                        language it was added in until it is removed and added again (the server's copy).
#                        Data 1.7.0.1 (57 rows, plus TalentDesc, EffectCardDesc and Author): passed
#                        2026-10-22, same phone, English: names, descriptions, the author suffix and a
#                        lineup's detail read translated, no popup, no repair.
SAFE_ASSETS: frozenset[int] = frozenset({0xF79FB1A213A9DA90})
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
#   0xB5D856BFDF22400D   rule pages, which is `ResHelpSystemCfgDataBin`: rewriting it removes the back
#                        arrow and the title from the Announcement (news) screen, leaving no way out
#                        but the system back key's quit prompt. `UINewsMainClass:InitUI` reads this
#                        bin for its help button before it builds the header. Allowlisted on 2026-10-01
#                        against the replay alone; withdrawn 2026-10-05 after a device cycle (Indonesian
#                        build, 1.4.0.2) with only this asset left out brought the header back.
#   0x2D1113B0AD51A562, 0xA1987F488164E53A, 0x1C8F7FFF7BDEF14D   AI opponent nicknames, display-text table,
#                        post-match compliments: with these rewritten, every match ends in the client's
#                        QTS-failure popup (`Doctor:HasQtsFailure`, shown as `/未翻译UI/QTSFailureTips`
#                        because the game ships no text for that key). Two matches out of two on a build
#                        carrying them; none on the same build with all three left out (2026-10-05,
#                        Indonesian, 1.4.0.2). Not bisected further, so any one may be harmless; each
#                        one's way back is a CANDIDATE_ASSETS cycle. All four withdrawals here are config
#                        bins that store an MD5 the rewrite leaves stale, and the 2026-10-01 verdicts
#                        that cleared them watched the replay crash only.
#   0x9E45602F1857539D   card-pack covers (Encyclopedia > Diamond Frenzy > Starting Lineup: the
#                        `逆天改命卡包` header and each cover's hero label). Prime-only, so the cycle
#                        appended it (`transform.config`). Rewritten 60 of 60 strings, the grid draws
#                        **empty**: no header, no covers. The same build without it (the control,
#                        pushed first) draws the grid, and pushing the control's package 1 back brought
#                        it back. Device cycle 2026-10-16, English, data 1.6.0.1, Infinix X6853. The
#                        same reseal failure as the encyclopedia withdrawals above: the bin's content
#                        is fine, its stored checksum is not.
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
# The order is the order to run the cycles in: after the lineup bins, the four label tables, because they
# are display labels the catalog mostly or entirely covers, and the other eleven only after a cycle says
# the class is safe. Those eleven are step, buff, nickname and damage identifiers the catalog reaches 1.5-9% of, so a
# cycle on one would add a handful of strings and risk a screen the note above already lists a synonym of.
CANDIDATE_ASSETS: dict[int, str] = {
    # The other two lineup bins (`lineup_codes.LINEUP_BINS`), queued apart from the fifteen: their text
    # sits inside share codes, so `rewrite_config` translates them through `lineup_codes.rewrite_bin`,
    # which also reseals the checksum the withdrawn config bins were left with stale. Counts are distinct
    # Chinese strings in the codes and the row text fields, and how many `catalog.unique` (with the
    # catalog supplement's "Official lineups") translates, the same in English and Indonesian; measured
    # on both layers of game data 1.6.0.1, 2026-10-21. The third, `F79FB1A213A9DA90`, cleared its cycle
    # and is on `SAFE_ASSETS`.
    0x6A2B886E5DCF22DC: "94 of 94 (196 fields), both layers -- ResRecommendLineup, 18 share codes; no "
                        "screen identified yet; resealed",
    0xC0C56FEFDCA0EA5D: "36 of 36 (45 fields) override, 35 of 35 (76 fields) prime -- "
                        "ResHeroStrategyDataBin, hero strategy videos, 5 share codes and the test row "
                        "titles; resealed",
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
# Lua UI scripts that hard-code a display label instead of looking one up, so no table can reach it.
# Each entry is the exact source text with `{}` where the label sits, and the Chinese label. Only that
# literal is replaced, with the catalog's official translation; a script whose text does not hold it
# exactly once is left alone. These scripts sit in package 10, which the protobuf pass excludes, so
# they are named here one by one rather than found by a scan.
SCRIPT_LABELS: dict[int, tuple[tuple[str, str], ...]] = {
    # Encyclopedia > Effect Cards: the class an effect card with no faction falls in, drawn as the
    # filter chip, the filter button and the section title (`vClassIdToDescriptor`, id -1). Prime-only
    # in 1.4.0.2, so it reaches the phone through the append pass.
    0x9BD30F0DF58B1FBF: (('name = "{}"', "通用"),),
}
# Lua UI scripts whose own formatting is wrong for a translation: each entry is an exact source literal
# and its replacement, applied under the same once-only rule as SCRIPT_LABELS.
SCRIPT_EDITS: dict[int, tuple[tuple[str, str], ...]] = {
    # PVPRankDataClass (package 10): a rank title is the tier name and its sub-level numeral joined with
    # no space, which reads "至尊星耀III" in Chinese and "Supreme StarIII" translated (the lobby's rank
    # line, `vGetRankTitle`, and the simple form, `vGetTitleByRankOrLevel`). Device-verified 2026-10-18 on
    # 1.6.0.1: the lobby reads "Supreme Star III".
    0x6CB505C6553141B4: (
        ('string.format("%s%s", Localize.GetString(string.format("RankLevel%s", rank)), romanCArray[level])',
         'string.format("%s %s", Localize.GetString(string.format("RankLevel%s", rank)), romanCArray[level])'),
        ('string.format("%s%s", Localize.GetString(string.format(simple and "SimpleRankLevel%s" or '
         '"RankLevel%s", rank)), romanCArray[level])',
         'string.format("%s %s", Localize.GetString(string.format(simple and "SimpleRankLevel%s" or '
         '"RankLevel%s", rank)), romanCArray[level])'),
    ),
}
# Every Lua script the pass may write.
SCRIPT_ASSETS = frozenset(SCRIPT_LABELS) | frozenset(SCRIPT_EDITS)
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


def rewrite_script(file_hash: int, raw: bytes, catalog) -> bytes | None:
    """<raw> with the SCRIPT_LABELS literals of <file_hash> translated and its SCRIPT_EDITS applied, or
    None when nothing changes."""
    new = raw
    translate = official_only(catalog)
    for template, label in SCRIPT_LABELS.get(file_hash, ()):
        target = translate(label)
        # The label lands inside a Lua string literal, so anything that would end or escape it is refused.
        if not target or any(char in target for char in '"\\\r\n'):
            continue
        old, replacement = template.format(label).encode(), template.format(target).encode()
        if new.count(old) == 1:
            new = new.replace(old, replacement)
    for old, replacement in SCRIPT_EDITS.get(file_hash, ()):
        if new.count(old.encode()) == 1:
            new = new.replace(old.encode(), replacement.encode())
    return new if new != raw else None


def plan_scripts(package, skip: set[int]) -> dict[int, bytes]:
    """The SCRIPT_ASSETS <package>'s own copy carries, read raw, for `rewrite_script`."""
    from qts_relocate import read_raw

    wanted = [file_hash for file_hash in SCRIPT_ASSETS
              if file_hash not in skip and (entry := package.entries.get(file_hash)) is not None
              and entry.compression in (1, 4)]
    if not wanted:
        return {}
    slots = package.build_slot_map()
    found = {}
    for file_hash in wanted:
        if file_hash not in slots:
            continue
        raw = read_raw(package, slots, file_hash)
        if raw is not None:
            found[file_hash] = raw
    return found


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
                 candidates: frozenset[int] = frozenset(),
                 terms: dict[str, str] | None = None) -> dict[int, bytes]:
    """New raw bytes for every allowlisted protobuf asset in <package> that can be translated.

    <candidates> are the CANDIDATE_ASSETS a device cycle has turned on for this run. They join the
    allowlist for the run and are not added to it: `SAFE_ASSETS` grows only when a cycle's screen has
    been looked at, so no run can ship an asset that was never put on a phone.

    <terms> are the patch language's resource terms (`languages`); English when omitted.
    """
    from qts_relocate import read_raw

    allowed = SAFE_ASSETS | candidates
    wanted = {file_hash for file_hash in allowed
              if file_hash not in skip and (entry := package.entries.get(file_hash)) is not None
              and entry.compression in (1, 4)}
    if not wanted:
        return {}
    slots = package.build_slot_map()
    jobs: dict[int, bytes] = {}
    for file_hash in slots:
        if file_hash not in wanted:
            continue
        raw = read_raw(package, slots, file_hash)
        if raw is None:
            continue
        new = rewrite_config(file_hash, raw, catalog, log, terms)
        if new is not None:
            jobs[file_hash] = new
    return jobs


def rewrite_config(file_hash: int, raw: bytes, catalog, log=None,
                   terms: dict[str, str] | None = None) -> bytes | None:
    """<raw> of an enabled config asset translated, or None when nothing changes.

    The one rewrite both `plan_package` and `package_rebuild.make_transform` apply, so the two paths
    cannot disagree about an asset. A lineup bin (`lineup_codes.LINEUP_BINS`) keeps its text inside
    share codes the generic protobuf rewrite cannot see, and stores a checksum over its rows, so it
    goes through `lineup_codes.rewrite_bin`, which translates inside the codes and reseals the bin.
    Its resource tokens are expanded string by string before the reseal, because expanding them in
    the finished bin would leave the checksum stale. Every other asset goes through `pb_text.rewrite`.
    <terms> are the patch language's resource terms (`languages`); English when omitted.
    """
    from resource_tokens import RESOURCE_TOKENS, expand_resource_tokens, expand_tokens

    terms = terms or RESOURCE_TOKENS
    if file_hash in lineup_codes.LINEUP_BINS:
        official = official_only(catalog)

        def translate(text: str) -> str | None:
            target = official(text)
            return expand_resource_tokens(target, terms) if target else None

        try:
            new, changed = lineup_codes.rewrite_bin(file_hash, raw, translate)
        except lineup_codes.NotLineupBin as error:
            if log is not None:
                log(f"  {file_hash:016X}: lineup bin not translated ({error})")
            return None
        return new if changed else None
    if not pb_text.CJK.search(raw.decode("utf-8", "ignore")):
        return None
    try:
        new, changed = pb_text.rewrite(raw, translator_for(file_hash, catalog))
    except pb_text.NotMessage:
        return None
    # The replacement comes from the catalog verbatim, so it carries the same {Energy}-style tokens the
    # staged path has to expand; the client would otherwise render them in Chinese.
    return expand_tokens(new, log, terms) if changed else None


def extend_text(game: Path, catalog, output: Path, log, skip_packages: set[str] = frozenset(),
                candidates: frozenset[int] = frozenset(),
                terms: dict[str, str] | None = None) -> list[dict]:
    """Translate uncovered protobuf assets in every package of <game>; returns summary entries.

    <candidates> is the device cycle's enablement and <terms> the language's resource terms, both
    passed through to `plan_package`.
    """
    from device_extensions import relocate_assets
    from wxq_patch.qtsvfs import QtsPackage

    skip = set(catalog.known) | set(catalog.graphics)
    reports = []
    root = game / "WXQ_Data" / "Package" / "builtin"
    for package_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        if package_dir.name in skip_packages:
            continue
        try:
            package = QtsPackage(package_dir)
        except Exception:  # noqa: BLE001 - packages without a readable index are not ours to patch
            continue
        if len(package.shard_paths) != 1:
            continue
        # The named scripts are the one thing this pass writes in an excluded package.
        jobs = {file_hash: new for file_hash, raw in plan_scripts(package, skip).items()
                if (new := rewrite_script(file_hash, raw, catalog)) is not None}
        if package_dir.name not in EXCLUDED_PACKAGES:
            jobs.update(plan_package(package, catalog, skip, log, candidates=candidates, terms=terms))
        if package_dir.name in UNITY_TEXT_PACKAGES:
            jobs.update(plan_unity_package(package, catalog))
        if not jobs:
            continue
        count = relocate_assets(package, output, jobs, log)
        if count:
            reports.append({"package_id": package.package_id, "mode": "extra-text",
                            "stage_report": {"status": "relocated", "replacement_count": count}})
    return reports
