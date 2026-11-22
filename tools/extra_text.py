"""Third patch pass: Chinese strings in assets the PC catalog has no localization table for.

* Any string that exactly matches a catalog translation (`catalog.unique`) gets the official English.
* The AI opponent name list is romanised with pinyin, because the catalog has no official translation
  for it.
* UI text components in Unity prefabs get the official English for exact matches, when a package is
  listed as carrying them.
* A Lua UI script that hard-codes a label (`SCRIPT_LABELS`) gets that one literal replaced, and one that
  joins or wraps words the Chinese way (`SCRIPT_EDITS`) gets that one literal edited. An edit that
  translates text the server sends reads a table of known texts the pass writes into the script from the
  catalog (`SCRIPT_TRANSLATIONS`).
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

import config_bin
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
#   0x9E924AAB5066EE19   the Super Weekend room perks (the room screen's event line): rows translated
#                        through the supplement, fields 1 and 4 resealed (`_resealed`). Cleared
#                        2026-11-21, Redmi Note 9 Pro (ebad528e), Root push, data 1.11.0.2, English: the
#                        room reads "Double Diamonds from card flips 2/3，Shared Score with no Intimacy
#                        limit", the counter advanced over the matches played, a match ended without the
#                        QTS-failure popup, and no package was repaired. Mobile edition only: no PC cycle
#                        yet, so it is not on `PC_SAFE_ASSETS` and stays on `CANDIDATE_ASSETS` for one.
SAFE_ASSETS: frozenset[int] = frozenset({0xF79FB1A213A9DA90, 0x9E924AAB5066EE19})
# The PC edition's own allowlist (AGENTS.md, "Allowlist per edition"): a config bin a device cycle cleared
# stays untranslated on the PC edition until a PC cycle clears it there, so `pc_catalog` carries only
# these, plus a PC cycle's one candidate (`resolve_candidates`). Empty: neither mobile bin has had a PC
# cycle. The room perks bin passed `--pc-selftest` on a copy (2026-11-21), which is not a screen.
PC_SAFE_ASSETS: frozenset[int] = frozenset()
# The package a config bin sits in on the PC edition; one it lacks is found by a logged scan of every index.
CONFIG_PC_PACKAGE = "1"
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
    # The Super Weekend room perks, queued 2026-11-21 ahead of the rest because the event is time-limited
    # and its room line shows only while it runs. Package 1, 293 B, the same bytes on the phone (1.10.1.2)
    # and the PC edition (1.11.0.2); absent at 1.8.0.1. Seven rows of (id, name, sort); the room screen
    # joins the active names with `，` and fills `%d/%d`. A sealed config bin, so `rewrite_config` reseals
    # it after the generic rewrite (`_resealed`). None of the seven is in the catalog; the supplement's
    # "Super Weekend room perks" section supplies them in both languages. Cleared on the phone 2026-11-21
    # and on `SAFE_ASSETS`; it stays here for the PC cycle it still owes (`PC_SAFE_ASSETS`).
    0x9E924AAB5066EE19: "7 of 7 (7 fields), via the supplement -- Super Weekend room perks (翻牌钻石翻倍 "
                        "%d/%d, 有分同享不限亲密度, ...), the room screen's event line; sealed, resealed; "
                        "mobile cleared 2026-11-21, PC cycle owed",
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


def _exit_button_label(class_name: str) -> tuple[str, str]:
    """The edit that has a match-end ranking toast's RefreshBtnText set its "Exit now" button's label.

    The prefab's own default (`现在退出`, package 19, which is never rewritten) is all the button shows:
    the script binds no text for it, while `PVPSettleNowQuitBtnTxt` in `DD5B5EDFBB69FEED` holds the
    catalog's "Exit now" and nothing reads it. So the label is looked up under the button and filled from
    that key, guarded, before the function's own work.
    """
    head = f"function {class_name}:RefreshBtnText()\n"
    return (head,
            head
            + "    pcall(function()\n"
              "        local label = self.widgetCommonBtn_Style3_Big:GetComponentInChildren("
              "typeof(CS.Timi.TimiText), true)\n"
              "        if CommonUtility:NotNull(label) then\n"
              '            label.text = Localize.GetString("PVPSettleNowQuitBtnTxt")\n'
              "        end\n"
              "    end)\n")


# The Card screen's faction tab item (`UICollectionCampTabItemClass`): the head of CMLTSetData, and its
# last line, after the name is set.
_CAMP_TAB_SET_DATA = ("---@param arg Data4UICollectionCampTabItemClass\n"
                      "function UICollectionCampTabItemClass:CMLTSetData(arg)\n")
_CAMP_TAB_SET_SELECT = "    self:SetSelect(self._relationId == arg.selectRelationId)\nend\n"
# The Card screen's faction tab bar (`UICollectionTopCampTabClass`): the line that spreads the cells, and
# the global it records that spacing in for the tabs.
_CAMP_TAB_SPACE = ("            self.layout.space = CSVector2((self.list:GetWidth() - (#viewData) * 195)"
                   " / (#viewData - 1), 0)\n")
_CAMP_TAB_SPACE_GLOBAL = "HOKACE_CampTabSpace"


def _camp_tab_names_fit() -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """The edits, on the tab item and on the bar, that give every Card-screen faction tab name one
    shared size that fits.

    `UICollectionTopCampTabClass` gives every tab a 195-unit cell and spreads the cells across the bar,
    so a cell never grows with its label, and the prefab's name keeps one size and overflows: no
    two-character Chinese name does, but "Three Kingdoms" runs over the next tab's icon. A tab's icon and
    name sit centred in the cell, so they may spill into the space between cells; the bar's edit records
    that space in `HOKACE_CampTabSpace` as it spreads the cells. Each tab, once its name is set,
    measures on its own label every name the bar shows (the season's factions, as the bar lists them,
    and All) against its cell plus that space, less the icon, plus 16 units, and takes the size the
    tightest one needs (never below 16); with no space recorded it fits the bare cell. The 16 units are
    tuned on a 2400 x 1080 phone (2026-11-11): the label's preferred width runs wider than the drawn
    text, so a clear gap to the next tab remains; a 40-unit margin left the names barely above 16, and
    an 8-unit one at about 21. Every tab measures the same names, so all reach the same size
    without waiting on each other: the tabs are list items created asynchronously, and a fit run from
    the bar found none of them bound on the phone (2026-11-11). The prefab's size is kept by each label's instance id,
    because list items are reused; the tab's own name is put back whatever happens; a failure is logged
    as a Unity warning and leaves the tab as the game drew it.
    """
    helper = ("local _campTabNameSize = {}\n\n"
              "local function _campTabNames()\n"
              "    local names = { Localize.GetString(\"HeroCollect_Filter_RelationAll\") }\n"
              "    local seasonId = HeroCollectData:GetSeasonId()\n"
              "    for _, relationId in pairs(HeroCollectData:GetTgtSeasonRelationArray(seasonId)) do\n"
              "        local relationCfg = PBDataManager.ResRelationConfDataBin.Get(relationId)\n"
              "        if relationCfg then\n"
              "            names[#names + 1] = relationCfg.RelationName\n"
              "        end\n"
              "    end\n"
              "    return names\n"
              "end\n\n"
              "local function _fitCampTabName(item)\n"
              "    local label = item.name\n"
              "    local own = label and label.text\n"
              "    local ok, err = pcall(function()\n"
              "        local size = _campTabNameSize[label:GetInstanceID()]\n"
              "        if size == nil then\n"
              "            size = label.fontSize\n"
              "            _campTabNameSize[label:GetInstanceID()] = size\n"
              "        end\n"
              "        label.fontSize = size\n"
              f"        local space = math.max(tonumber(rawget(_G, \"{_CAMP_TAB_SPACE_GLOBAL}\")) or 0, 0)\n"
              "        local room = 195 + space - item.teamImage.rectTransform.rect.width + 16\n"
              "        local scale = 1\n"
              "        for _, name in ipairs(_campTabNames()) do\n"
              "            label.text = name\n"
              "            local width = label.preferredWidth\n"
              "            if room > 0 and width > room then\n"
              "                scale = math.min(scale, room / width)\n"
              "            end\n"
              "        end\n"
              "        label.fontSize = math.max(math.floor(size * scale), 16)\n"
              "    end)\n"
              "    if own ~= nil then\n"
              "        pcall(function() label.text = own end)\n"
              "    end\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE camp tab fit: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n")
    item = ((_CAMP_TAB_SET_DATA, helper + _CAMP_TAB_SET_DATA),
            (_CAMP_TAB_SET_SELECT, "    _fitCampTabName(self)\n" + _CAMP_TAB_SET_SELECT))
    bar = ((_CAMP_TAB_SPACE, _CAMP_TAB_SPACE + "            pcall(function() rawset(_G, "
            f"\"{_CAMP_TAB_SPACE_GLOBAL}\", self.layout.space.x) end)\n"),)
    return item, bar


# The lobby's bottom-right buttons (`UILobbyBtnItemClass`): the head of CMLTSetData, and the line that
# sets the name.
_LOBBY_BTN_SET_DATA = ("---@param data LobbyMenuItemData\n"
                       "function UILobbyBtnItemClass:CMLTSetData(data, index, selected)\n")
_LOBBY_BTN_SET_NAME = "    self:SetIcon(cfg.IconEnum)\n    self:SetName(cfg.Name)\n"


def _lobby_btn_names_fit() -> tuple[tuple[str, str], ...]:
    """The edit that gives the lobby's bottom-right button names (Chessplayer, Card, Lineup) one shared
    size.

    Each name sits in a 111-unit `Txt_Title` box set to best fit (33 at most), so "Chessplayer" shrinks
    to about 20 while "Card" and "Lineup" stay at 33. Each button turns best fit off, lets its name
    overflow the box (still centred), and measures every name the row shows at the prefab's largest
    size. The row is the buttons bound so far, in their `Sort` order: the list creates its items
    asynchronously, so each new button records itself and refits every recorded one. Any two
    neighbours, side by side, must fit within one cell (the button's own width) less a 16-unit gap, so
    the names never reach into the 57 units between cells; the size shrinks only as far as the tightest
    pair needs (never below 16), about 21 on a 2400 x 1080 phone. Letting the names use that spacing
    too put all three at 33, with "Chessplayer" about 23 px short of "Card"; the user preferred the
    smaller size (2026-11-11). The prefab's size is kept by each label's instance id, because list items are reused, the
    button's own name is put back, and a failure leaves the button as the game drew it, logged as a
    Unity warning.
    """
    helper = ("local _lobbyBtnNameSize = {}\n"
              "local _lobbyBtnItems = setmetatable({}, { __mode = \"k\" })\n\n"
              "local function _lobbyBtnNames()\n"
              "    local entries = {}\n"
              "    for item in pairs(_lobbyBtnItems) do\n"
              "        local cfg = item.cfg\n"
              "        if cfg and CommonUtility:NotNull(item.name) and not string.isNullOrEmpty(cfg.Name) then\n"
              "            entries[#entries + 1] = cfg\n"
              "        end\n"
              "    end\n"
              "    table.sort(entries, function(a, b) return a.Sort < b.Sort end)\n"
              "    return entries\n"
              "end\n\n"
              "local function _fitLobbyBtnName(item)\n"
              "    local label = item.name\n"
              "    local own = label and label.text\n"
              "    local ok, err = pcall(function()\n"
              "        local size = _lobbyBtnNameSize[label:GetInstanceID()]\n"
              "        if size == nil then\n"
              "            size = label.resizeTextForBestFit and label.resizeTextMaxSize or label.fontSize\n"
              "            _lobbyBtnNameSize[label:GetInstanceID()] = size\n"
              "        end\n"
              "        label.resizeTextForBestFit = false\n"
              "        label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow\n"
              "        label.fontSize = size\n"
              "        local widths = {}\n"
              "        for _, cfg in ipairs(_lobbyBtnNames()) do\n"
              "            label.text = cfg.Name\n"
              "            widths[#widths + 1] = label.preferredWidth\n"
              "        end\n"
              "        local room = item._rootTf.rect.width - 16\n"
              "        local scale = 1\n"
              "        for i = 1, #widths - 1 do\n"
              "            local need = (widths[i] + widths[i + 1]) / 2\n"
              "            if room > 0 and need > room then\n"
              "                scale = math.min(scale, room / need)\n"
              "            end\n"
              "        end\n"
              "        label.fontSize = math.max(math.floor(size * scale), 16)\n"
              "    end)\n"
              "    if own ~= nil then\n"
              "        pcall(function() label.text = own end)\n"
              "    end\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE lobby button fit: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n")
    return ((_LOBBY_BTN_SET_DATA, helper + _LOBBY_BTN_SET_DATA),
            (_LOBBY_BTN_SET_NAME, _LOBBY_BTN_SET_NAME
             + "    _lobbyBtnItems[self] = true\n"
               "    for item in pairs(_lobbyBtnItems) do\n"
               "        if item.cfg then\n"
               "            _fitLobbyBtnName(item)\n"
               "        end\n"
               "    end\n"))


# The lobby's top-bar entries (`UILobbyMenuItemClass`): the head of CMLTSetData, its layout lines, and
# the end of RedDotCallBack.
_LOBBY_MENU_SET_DATA = ("---@param argument LobbyMenuItemData\n"
                        "function UILobbyMenuItemClass:CMLTSetData(argument, index, selected)\n")
_LOBBY_MENU_LAYOUT = ("    ForceRebuildLayoutImmediate(self.stackRect)\n"
                      "    self.itemLayoutElement.preferredWidth = self.stackRect.sizeDelta.x\n")
_LOBBY_MENU_RED_END = ("    UIUtility:SetActive(self.effectLoader, show)\n"
                       "    UIUtility:SetActive(self.dynamicIcon, not show)\nend\n")


def _lobby_menu_icon_gap() -> tuple[tuple[str, str], ...]:
    """The edit that keeps a lobby top-bar entry's name clear of its icon while the entry's red-dot
    effect plays.

    An entry is an icon and a name in a horizontal layout group (`Stack`) with -4.5 spacing: the 78-unit
    icon sits in a 60-unit slot, and its plain art leaves about a 12-unit gap before the name. While the
    red dot shows, the game swaps the icon for a larger effect (Mall's yellow cart), which touches the
    name. That state now adds 16 units to the spacing, re-laid out at once, which leaves the cart about
    8 px clear of "Mall" on a 2400 x 1080 phone (8 units only moved it 3 px, 2026-11-11). The prefab's
    spacing is kept by each group's instance id, because list items are reused.
    """
    helper = ("local _lobbyMenuSpacing = {}\n\n"
              "local function _tidyLobbyMenuItem(item)\n"
              "    pcall(function()\n"
              "        local group = item.name.transform.parent:GetComponent("
              "typeof(CS.UnityEngine.UI.HorizontalLayoutGroup))\n"
              "        if not CommonUtility:NotNull(group) then\n"
              "            return\n"
              "        end\n"
              "        local spacing = _lobbyMenuSpacing[group:GetInstanceID()]\n"
              "        if spacing == nil then\n"
              "            spacing = group.spacing\n"
              "            _lobbyMenuSpacing[group:GetInstanceID()] = spacing\n"
              "        end\n"
              "        group.spacing = spacing + (item._isShowRed and 16 or 0)\n"
              "    end)\n"
              "end\n\n")
    relayout = ("    if self.cfg then\n"
                "        pcall(function()\n"
                "            _tidyLobbyMenuItem(self)\n"
                "            ForceRebuildLayoutImmediate(self.stackRect)\n"
                "            self.itemLayoutElement.preferredWidth = self.stackRect.sizeDelta.x\n"
                "        end)\n"
                "    end\n")
    return ((_LOBBY_MENU_SET_DATA, helper + _LOBBY_MENU_SET_DATA),
            (_LOBBY_MENU_LAYOUT, "    _tidyLobbyMenuItem(self)\n" + _LOBBY_MENU_LAYOUT),
            (_LOBBY_MENU_RED_END, _LOBBY_MENU_RED_END[:-len("end\n")] + relayout + "end\n"))


# The lobby (`UILobbyClass`): its vOnInitialize head, and the red-dot registration inside it.
_LOBBY_INITIALIZE = "function UILobbyClass:vOnInitialize(argument)\n"
_LOBBY_REGIST_RED = "    self:RegistRedPoint()\n    self:GetApplyList()"


def _lobby_menu_button_gap() -> tuple[tuple[str, str], ...]:
    """The edit that lays the lobby's Menu button (`Btn_Storage`), its divider and the entry row after
    it out with the Chinese lobby's gaps.

    The button places `Img_GoMenu` (35 units wide) and `Txt_Name` (a 72-unit box, centred) at fixed
    offsets, sized for 菜单: on a 2400 x 1080 phone (one unit, one pixel) the Chinese reads icon, 11 px,
    name, 36 px, divider (`Split`), 40 px, the Event icon (2026-11-11). "Menu" at 36 is about 35 px
    wider, so it ran into the icon and up to the divider. The icon stays where the prefab puts it (it
    carries an Animation that holds its position anyway), the name moves 18 units right, back to 11 px
    after the icon, and the divider and the entry row (`Left`: the top-bar list, First Top-up and
    Download) each move 36 units right, which restores 36 px before the divider and 40 px after it.
    Each offset is taken from the prefab's own position, kept by each transform's instance id, so a second initialize does
    not add up.
    """
    helper = ("local _lobbyMenuButtonX = {}\n\n"
              "local function _shiftLobbyMenuPart(tf, dx)\n"
              "    if tf == nil then\n"
              "        return\n"
              "    end\n"
              "    local base = _lobbyMenuButtonX[tf:GetInstanceID()]\n"
              "    if base == nil then\n"
              "        base = tf.anchoredPosition.x\n"
              "        _lobbyMenuButtonX[tf:GetInstanceID()] = base\n"
              "    end\n"
              "    tf.anchoredPosition = CSVector2(base + dx, tf.anchoredPosition.y)\n"
              "end\n\n"
              "local function _tidyLobbyMenuButton(lobby)\n"
              "    local ok, err = pcall(function()\n"
              "        local button = lobby.btn_Storage.transform\n"
              "        _shiftLobbyMenuPart(button:Find(\"Txt_Name\"), 18)\n"
              "        _shiftLobbyMenuPart(button.parent:Find(\"Split\"), 36)\n"
              "        _shiftLobbyMenuPart(button.parent:Find(\"Left\"), 36)\n"
              "    end)\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE lobby menu gap: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n")
    return ((_LOBBY_INITIALIZE, helper + _LOBBY_INITIALIZE),
            (_LOBBY_REGIST_RED, "    self:RegistRedPoint()\n    _tidyLobbyMenuButton(self)\n    self:GetApplyList()"))


def _crlf(edits: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """<edits> with every line ending CRLF, for a script stored with Windows line endings."""
    return tuple((old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) for old, new in edits)


# The room's bottom-left buttons (`UIPVPRoomLeftDown_NormalClass`): its class declaration, and the end
# of OnSetSelfPersonalTrainer, which runs at initialize and whenever the buttons are shown or hidden.
_ROOM_LEFT_DOWN_CLASS = ("---@class UIPVPRoomLeftDown_NormalClass : "
                         "UIPVPRoomLeftDown_NormalClass_AutoBind\n")
_ROOM_LEFT_DOWN_SHOWN = "    self:SetLineupSeparator(showSetting)\nend\n"


def _room_buttons_clear_of_icons() -> tuple[tuple[str, str], ...]:
    """The edit that keeps the room's Lineup and Settings names clear of their icons.

    Prefab `UIPVPRoomLeftDown_Normal` (package 19): each button is a 200-unit cell (a `LayoutElement`
    in `BtnGroup`'s horizontal layout, which a content size fitter sizes), with its icon centred at
    x -43.5 (`Img_EmbattleEnter`, 75 wide) or -45 (`Img_Setting`, 84 wide) and its name a 33-point label
    sized to its text and centred at x 18. Two Chinese characters span x -15 to 51, clear of the icon;
    "Lineup" and "Settings", centred on the same point, start inside the icon. Each name is now pinned
    by its left edge where the Chinese starts (its centre less one font size), and the cell grows by
    whatever the name needs to end 30 units before the cell's divider, with the icon and the name moved
    left by half that growth so they keep their place from the cell's left edge. The prefab's width and
    positions are kept by the button's instance id (not in a weak table keyed by its Lua wrapper, which
    can be collected and lose them), because a second pass must not add up. The fit runs when the
    buttons are shown and once more on the next tick, in case the name is filled after this script;
    a failure leaves the button as the game drew it, logged as a Unity warning.
    """
    helper = ("local _roomButtonBase = {}\n\n"
              "local function _fitRoomButton(button, iconName, labelName)\n"
              "    if not CommonUtility:NotNull(button) then\n"
              "        return\n"
              "    end\n"
              "    local root = button.transform\n"
              "    local icon = root:Find(iconName)\n"
              "    local labelTf = root:Find(labelName)\n"
              "    if icon == nil or labelTf == nil then\n"
              "        return\n"
              "    end\n"
              "    local label = labelTf:GetComponent(typeof(CS.Timi.TimiText))\n"
              "    local element = root:GetComponent(typeof(CS.UnityEngine.UI.LayoutElement))\n"
              "    if not CommonUtility:NotNull(label) then\n"
              "        return\n"
              "    end\n"
              "    local base = _roomButtonBase[root:GetInstanceID()]\n"
              "    if base == nil then\n"
              "        local width = root.rect.width\n"
              "        if CommonUtility:NotNull(element) and element.preferredWidth > 0 then\n"
              "            width = element.preferredWidth\n"
              "        end\n"
              "        base = { width = width, iconX = icon.anchoredPosition.x,\n"
              "                 left = labelTf.anchoredPosition.x - label.fontSize }\n"
              "        _roomButtonBase[root:GetInstanceID()] = base\n"
              "    end\n"
              "    local grow = math.max(math.ceil(base.left + label.preferredWidth + 30 - base.width / 2), 0)\n"
              "    if CommonUtility:NotNull(element) then\n"
              "        element.preferredWidth = base.width + grow\n"
              "    else\n"
              "        root:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Horizontal, "
              "base.width + grow)\n"
              "    end\n"
              "    icon.anchoredPosition = CSVector2(base.iconX - grow / 2, icon.anchoredPosition.y)\n"
              "    labelTf.pivot = CSVector2(0, labelTf.pivot.y)\n"
              "    labelTf.anchoredPosition = CSVector2(base.left - grow / 2, labelTf.anchoredPosition.y)\n"
              "    pcall(function() ForceRebuildLayoutImmediate(root.parent) end)\n"
              "end\n\n"
              "local function _fitRoomButtons(view)\n"
              "    local ok, err = pcall(function()\n"
              "        _fitRoomButton(view.btnEmbattle, \"Img_EmbattleEnter\", \"Txt_Embattle\")\n"
              "        _fitRoomButton(view.btn_Setting, \"Img_Setting\", \"Txt_Setting\")\n"
              "    end)\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE room buttons: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n")
    return _crlf(((_ROOM_LEFT_DOWN_CLASS, helper + _ROOM_LEFT_DOWN_CLASS),
                  (_ROOM_LEFT_DOWN_SHOWN,
                   "    self:SetLineupSeparator(showSetting)\n"
                   "    pcall(_fitRoomButtons, self)\n"
                   "    pcall(function()\n"
                   "        ScheduleService:SetTimeout(function()\n"
                   "            if self:Available() then\n"
                   "                pcall(_fitRoomButtons, self)\n"
                   "            end\n"
                   "        end, 0)\n"
                   "    end)\n"
                   "end\n")))


# The room's friend panel tabs (`UIPVPRoomNestedRecommendTabItemClass`): its class declaration, and the
# end of CMLTSetData, after the title is set.
_ROOM_TAB_CLASS = ("---@class UIPVPRoomNestedRecommendTabItemClass : "
                   "UIPVPRoomNestedRecommendTabItemClass_AutoBind\n")
_ROOM_TAB_SET_DATA_END = "    self:SetShowSplitLine(index == count)\nend\n"


def _room_tab_names_fit() -> tuple[tuple[str, str], ...]:
    """The edit that gives the room's friend panel tab names (Friend, Recent, Recommend, Team) one shared
    size.

    Prefab `UIPVPRoomNestedRecommendTabItem` (package 19): each name (`Txt_Title`) fills its tab with
    best fit (33 at most), and `List_Tab` gives every tab the same width, 129 units on a 2400 x 1080
    phone, so "Recommend" alone shrank to about 20. Each tab, once its title is set, turns best fit off,
    lets its name overflow (still centred), and measures on its own label, at the prefab's largest size,
    every name the panel can show (`UIPVPRoomRecommendBaseClass`'s TAB2NAME keys); it takes the size at
    which the widest fits its label less 8 units (never below 16). Every tab measures the same names, so
    all reach the same size without knowing each other: on the phone each tab sits in its own list cell,
    so tabs grouped by parent each fitted only themselves, and the list kept its even widths when a tab
    asked for more (2026-11-21, probe). A label not laid out yet (no width) keeps best fit. The prefab's
    size is kept by each label's instance id, because list items are reused; the tab's own name is put back; a failure
    leaves the tab as the game drew it, logged as a Unity warning.
    """
    helper = ("local _roomTabNameSize = {}\n"
              "local _ROOM_TAB_NAME_KEYS = { \"RoomRecommendTabFriend\", \"RoomRecommendTabRecent\",\n"
              "    \"RoomRecommendTabPlayer\", \"RoomRecommendTabRoom\" }\n\n"
              "local function _fitRoomTabName(item)\n"
              "    local label = item.txtTitle\n"
              "    local own = label and label.text\n"
              "    local ok, err = pcall(function()\n"
              "        local size = _roomTabNameSize[label:GetInstanceID()]\n"
              "        if size == nil then\n"
              "            size = label.resizeTextForBestFit and label.resizeTextMaxSize or label.fontSize\n"
              "            _roomTabNameSize[label:GetInstanceID()] = size\n"
              "        end\n"
              "        local room = label.rectTransform.rect.width - 8\n"
              "        if room <= 0 then\n"
              "            return\n"
              "        end\n"
              "        label.resizeTextForBestFit = false\n"
              "        label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow\n"
              "        label.fontSize = size\n"
              "        local scale = 1\n"
              "        for _, key in ipairs(_ROOM_TAB_NAME_KEYS) do\n"
              "            label.text = Localize.GetString(key)\n"
              "            local width = label.preferredWidth\n"
              "            if width > room then\n"
              "                scale = math.min(scale, room / width)\n"
              "            end\n"
              "        end\n"
              "        label.fontSize = math.max(math.floor(size * scale), 16)\n"
              "    end)\n"
              "    if own ~= nil then\n"
              "        pcall(function() label.text = own end)\n"
              "    end\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE room tab fit: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n")
    return _crlf(((_ROOM_TAB_CLASS, helper + _ROOM_TAB_CLASS),
                  (_ROOM_TAB_SET_DATA_END,
                   "    self:SetShowSplitLine(index == count)\n"
                   "    pcall(_fitRoomTabName, self)\n"
                   "end\n")))


# The lobby's Menu panel entries (`UILobbyMenuLittleItemClass`): its class declaration, the empty-entry
# return in CMLTSetData, and the line that sets the name.
_MAIN_MENU_ITEM_CLASS = ("---@class UILobbyMenuLittleItemClass : "
                         "UILobbyMenuLittleItemClass_AutoBind\n")
_MAIN_MENU_ITEM_EMPTY = "    if data.empty or not data.cfg then\n        return\n    end\n"
_MAIN_MENU_ITEM_NAME = "    self:SetContent(self.cfg.Name)\n"


def _main_menu_names_fit() -> tuple[tuple[str, str], ...]:
    """The edit that gives the lobby Menu panel's entry names (Custom, Achievement, Encyclopedia,
    Announcement and the rest) one shared size.

    Prefab `UILobbyMenuLittleItem` (package 19, `52615AAB6C452819`): each entry is a 195 x 240 cell, its
    name (`Txt_UnLockName`) a 150 x 44 box with best fit, so "Achievement", "Encyclopedia" and
    "Announcement" each shrank to their own size while the short names stayed at full size (1.11.0.2,
    2026-11-21). One list (`menuRootTimiList`) holds every entry, four to a row, plus blank fillers. Each
    entry records its name once set (a filler records none), then refits every recorded entry: best fit
    off, the name allowed to overflow its box (still centred), and every recorded name measured on that
    entry's label at the prefab's largest size; all take the size at which the widest fits one cell less
    12 units (never below 16). The prefab's size is kept by each label's instance id, because list items are reused, the
    entry's own name is put back, and a failure leaves the entry as the game drew it, logged as a Unity
    warning.
    """
    helper = ("local _mainMenuNameSize = {}\n"
              "local _mainMenuNames = setmetatable({}, { __mode = \"k\" })\n\n"
              "local function _fitMainMenuName(item)\n"
              "    local label = item.content\n"
              "    local own = label and label.text\n"
              "    local ok, err = pcall(function()\n"
              "        local size = _mainMenuNameSize[label:GetInstanceID()]\n"
              "        if size == nil then\n"
              "            size = label.resizeTextForBestFit and label.resizeTextMaxSize or label.fontSize\n"
              "            _mainMenuNameSize[label:GetInstanceID()] = size\n"
              "        end\n"
              "        local room = item._rootTf.rect.width - 12\n"
              "        if room <= 0 then\n"
              "            return\n"
              "        end\n"
              "        label.resizeTextForBestFit = false\n"
              "        label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow\n"
              "        label.fontSize = size\n"
              "        local scale = 1\n"
              "        for other, name in pairs(_mainMenuNames) do\n"
              "            if CommonUtility:NotNull(other.content) then\n"
              "                label.text = name\n"
              "                local width = label.preferredWidth\n"
              "                if width > room then\n"
              "                    scale = math.min(scale, room / width)\n"
              "                end\n"
              "            end\n"
              "        end\n"
              "        label.fontSize = math.max(math.floor(size * scale), 16)\n"
              "    end)\n"
              "    if own ~= nil then\n"
              "        pcall(function() label.text = own end)\n"
              "    end\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE main menu fit: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n"
              "local function _fitMainMenuNames()\n"
              "    for item in pairs(_mainMenuNames) do\n"
              "        if CommonUtility:NotNull(item.content) then\n"
              "            _fitMainMenuName(item)\n"
              "        end\n"
              "    end\n"
              "end\n\n")
    return ((_MAIN_MENU_ITEM_CLASS, helper + _MAIN_MENU_ITEM_CLASS),
            (_MAIN_MENU_ITEM_EMPTY, "    _mainMenuNames[self] = nil\n" + _MAIN_MENU_ITEM_EMPTY),
            (_MAIN_MENU_ITEM_NAME, _MAIN_MENU_ITEM_NAME
             + "    if not string.isNullOrEmpty(self.cfg.Name) then\n"
               "        _mainMenuNames[self] = self.cfg.Name\n"
               "        pcall(_fitMainMenuNames)\n"
               "    end\n"))


# The Chessplayer page (`UILordListClass`): its class declaration, the end of InitCombatPowerTab, and the
# switch to the Combat Power tab.
_LORD_LIST_CLASS = "---@class UILordListClass : UILordListClass_AutoBind\n"
_LORD_LIST_TABS_SET = ("    self:SetInterfaceType(defaultToPower and UILordListClassInterfaceType.TotalLegendPoint\n"
                       "        or UILordListClassInterfaceType.ChessPlayer)\nend\n")
_LORD_LIST_TO_POWER = "    self:SetInterfaceType(UILordListClassInterfaceType.TotalLegendPoint)\n"


def _lord_list_header_fit() -> tuple[tuple[str, str], ...]:
    """The edit that keeps the Chessplayer page's header readable: one size for its two tab names
    (Chessplayer, Combat Power), and the Combat Power page's sort toggle clear of the back title.

    Prefab `UILordList` (package 19): the tabs are a `TimiMenu` (`TabList`) of `UILordTotalPowerPaageItem`
    items (`40090008899DA31A`), 197 x 69 each, whose name boxes are 76 units (selected) and 152 (not), so
    "Chessplayer" and "Combat Power" ran into each other at full size (1.11.0.2, 2026-11-21). Both names
    keep their full size (best fit off, overflowing their boxes, still centred), and every tab widens to the
    widest name plus 40 units each side (never narrower than the prefab); the tabs stay centred where they
    were, moving right only as far as keeps them 40 units clear of the sort toggle, sit side by side, each
    tab's underline stretches with it, and the grey line under the bar (`WidgetCommonLine5`) is set to the
    tabs' own left and right edges, measured where they sit (moving it by the tabs' offset left it about
    100 units right of them on the phone). A first try shrank the names to fit 197 units instead; measured against the 76-unit box it put
    them at 16, and the user asked for wider tabs and larger names, with the sort label smaller to make
    room.

    Prefab `UILordCombatpowerList` (`835EF33C7D9684AE`): the sort toggle (`WidgetCommonCheckWithLeftTitle`,
    right-pivoted, its label left of the box) sits in a `Check` group whose left edge, a divider, is
    where the two-character Chinese back title ends; "‹ Chessplayer" covered it and "Sort by Combat
    Power" ran left under the title. Its label drops to 80% of the prefab's size (never below 16). The
    group moves right until its left edge sits 24 units past the
    back title's text (`UIFullScreenViewTemplate_Back`'s `title`, measured as left-aligned), and the
    toggle's right edge moves out until the toggle starts 24 units past the divider. The toggle's width is
    its widest label plus 64 units (the box and its gap, as the prefab's unselected state lays them out),
    not its laid-out width: the Combat Power page is inactive until first shown, so its layout is not
    built, and measured that way the tabs sat centred on the first visit and moved once the page had
    been seen. Measured from the labels, the tabs take the Combat Power position from the first visit. Both run when the
    tabs are set and when the Combat Power tab opens, and again on the next tick; the prefab positions
    are kept by each object's instance id, so a rerun never drifts, and a failure leaves the header as the
    game drew it, logged as a Unity warning. A rerun half a second later settles the header after the
    page's opening animation. Kept in a weak table keyed by the Lua wrapper, the values were lost when
    the wrapper was collected, and the next pass took the moved layout as the prefab's: on the phone the
    sort label shrank again and the toggle and tabs crept right into the total power.
    """
    helper = ("local _lordTabSize = {}\n"
              "local _lordTabBase = {}\n"
              "local _lordCheckBase = {}\n\n"
              "local function _fitLordTabs(page, toggleEnd)\n"
              "    local menuTf = page.tabList.transform\n"
              "    local texts = menuTf:GetComponentsInChildren(typeof(CS.UnityEngine.UI.Text), true)\n"
              "    local items, seen = {}, {}\n"
              "    local widest = 0\n"
              "    for i = 0, texts.Length - 1 do\n"
              "        local label = texts[i]\n"
              "        local item = label.rectTransform\n"
              "        while item ~= nil and item.parent ~= menuTf do\n"
              "            item = item.parent\n"
              "        end\n"
              "        if item ~= nil then\n"
              "            local size = _lordTabSize[label:GetInstanceID()]\n"
              "            if size == nil then\n"
              "                size = label.resizeTextForBestFit and label.resizeTextMaxSize or label.fontSize\n"
              "                _lordTabSize[label:GetInstanceID()] = size\n"
              "            end\n"
              "            label.resizeTextForBestFit = false\n"
              "            label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow\n"
              "            label.fontSize = size\n"
              "            widest = math.max(widest, label.preferredWidth)\n"
              "            if not seen[item] then\n"
              "                seen[item] = true\n"
              "                items[#items + 1] = item\n"
              "            end\n"
              "        end\n"
              "    end\n"
              "    if #items == 0 or widest <= 0 then\n"
              "        return\n"
              "    end\n"
              "    for _, item in ipairs(items) do\n"
              "        if _lordTabBase[item:GetInstanceID()] == nil then\n"
              "            _lordTabBase[item:GetInstanceID()] = { w = item.rect.width, x = item.anchoredPosition.x }\n"
              "        end\n"
              "    end\n"
              "    table.sort(items, function(a, b) return _lordTabBase[a:GetInstanceID()].x < _lordTabBase[b:GetInstanceID()].x end)\n"
              "    local first = _lordTabBase[items[1]:GetInstanceID()]\n"
              "    local width = math.max(widest + 80, first.w)\n"
              "    local baseLeft = first.x - first.w * items[1].pivot.x\n"
              "    local left = baseLeft + (first.w - width) * #items / 2\n"
              "    local function place()\n"
              "        for i, item in ipairs(items) do\n"
              "            item:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Horizontal, width)\n"
              "            item.anchoredPosition = CSVector2(left + width * (i - 1) + width * item.pivot.x, item.anchoredPosition.y)\n"
              "        end\n"
              "    end\n"
              "    place()\n"
              "    if toggleEnd ~= nil then\n"
              "        local tabStart = items[1]:TransformPoint(CS.UnityEngine.Vector3(items[1].rect.xMin, 0, 0))\n"
              "        local gap = menuTf:InverseTransformPoint(toggleEnd).x + 40 - menuTf:InverseTransformPoint(tabStart).x\n"
              "        if gap > 0 then\n"
              "            left = left + gap\n"
              "            place()\n"
              "        end\n"
              "    end\n"
              "    local line = page.topTab:Find(\"WidgetCommonLine5\")\n"
              "    if line ~= nil then\n"
              "        local lineParent = line.parent\n"
              "        local tabStart = items[1]:TransformPoint(CS.UnityEngine.Vector3(items[1].rect.xMin, 0, 0))\n"
              "        local tabEnd = items[#items]:TransformPoint(CS.UnityEngine.Vector3(items[#items].rect.xMax, 0, 0))\n"
              "        local startX = lineParent:InverseTransformPoint(tabStart).x\n"
              "        local endX = lineParent:InverseTransformPoint(tabEnd).x\n"
              "        line:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Horizontal, endX - startX)\n"
              "        local lineLeft = line.localPosition.x + line.rect.xMin\n"
              "        line.anchoredPosition = CSVector2(line.anchoredPosition.x + startX - lineLeft, line.anchoredPosition.y)\n"
              "    end\n"
              "end\n\n"
              "local function _placeLordSortToggle(page)\n"
              "    local list = page.uiLordCombatpowerListChild\n"
              "    local back = page.uiFullScreenViewTemplate_BackChild\n"
              "    if not list or not back or not list.widgetCommonCheckWithLeftTitle or not back.title then\n"
              "        return\n"
              "    end\n"
              "    local toggleTf = list.widgetCommonCheckWithLeftTitle.transform\n"
              "    local check = toggleTf.parent\n"
              "    local base = _lordCheckBase[check:GetInstanceID()]\n"
              "    if base == nil then\n"
              "        base = { checkX = check.anchoredPosition.x, toggleX = toggleTf.anchoredPosition.x }\n"
              "        _lordCheckBase[check:GetInstanceID()] = base\n"
              "    end\n"
              "    local labels = toggleTf:GetComponentsInChildren(typeof(CS.UnityEngine.UI.Text), true)\n"
              "    local labelWidth = 0\n"
              "    for i = 0, labels.Length - 1 do\n"
              "        local label = labels[i]\n"
              "        local size = _lordTabSize[label:GetInstanceID()]\n"
              "        if size == nil then\n"
              "            size = label.resizeTextForBestFit and label.resizeTextMaxSize or label.fontSize\n"
              "            _lordTabSize[label:GetInstanceID()] = size\n"
              "        end\n"
              "        label.resizeTextForBestFit = false\n"
              "        label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow\n"
              "        label.fontSize = math.max(math.floor(size * 0.8), 16)\n"
              "        labelWidth = math.max(labelWidth, label.preferredWidth)\n"
              "    end\n"
              "    pcall(function() ForceRebuildLayoutImmediate(toggleTf) end)\n"
              "    local toggleX = math.max(base.toggleX, labelWidth + 64 + 24)\n"
              "    toggleTf.anchoredPosition = CSVector2(toggleX, toggleTf.anchoredPosition.y)\n"
              "    local title = back.title\n"
              "    local titleTf = title.rectTransform\n"
              "    local titleEnd = titleTf:TransformPoint(CS.UnityEngine.Vector3(titleTf.rect.xMin + title.preferredWidth, 0, 0))\n"
              "    local titleRight = check.parent:InverseTransformPoint(titleEnd).x\n"
              "    local baseLeft = check.localPosition.x - (check.anchoredPosition.x - base.checkX) + check.rect.xMin\n"
              "    local shift = math.max(titleRight + 24 - baseLeft, 0)\n"
              "    check.anchoredPosition = CSVector2(base.checkX + shift, check.anchoredPosition.y)\n"
              "    return check:TransformPoint(CS.UnityEngine.Vector3(check.rect.xMin + toggleX, 0, 0))\n"
              "end\n\n"
              "local function _fitLordHeader(page)\n"
              "    local toggleEnd = nil\n"
              "    local ok2, err2 = pcall(function()\n"
              "        toggleEnd = _placeLordSortToggle(page)\n"
              "    end)\n"
              "    local ok, err = pcall(function()\n"
              "        _fitLordTabs(page, toggleEnd)\n"
              "    end)\n"
              "    if not ok or not ok2 then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE chessplayer header: \" .. tostring(err) .. \" \" .. tostring(err2)) end)\n"
              "    end\n"
              "end\n\n"
              "local function _fitLordHeaderNowAndNext(page)\n"
              "    pcall(_fitLordHeader, page)\n"
              "    pcall(function()\n"
              "        ScheduleService:SetTimeout(function()\n"
              "            if page:Available() then\n"
              "                pcall(_fitLordHeader, page)\n"
              "            end\n"
              "        end, 0)\n"
              "        ScheduleService:SetTimeout(function()\n"
              "            if page:Available() then\n"
              "                pcall(_fitLordHeader, page)\n"
              "            end\n"
              "        end, 0.5)\n"
              "    end)\n"
              "end\n\n")
    return ((_LORD_LIST_CLASS, helper + _LORD_LIST_CLASS),
            (_LORD_LIST_TABS_SET, _LORD_LIST_TABS_SET[:-len("end\n")]
             + "    _fitLordHeaderNowAndNext(self)\nend\n"),
            (_LORD_LIST_TO_POWER, _LORD_LIST_TO_POWER + "    _fitLordHeaderNowAndNext(self)\n"))


# The match-end ranking screen's tab bar (`UISettleBattle_OSGClass`): its class declaration, and the end
# of RefreshTimiMenuOptions, after the tabs are set.
_SETTLE_TABS_CLASS = "---@class UISettleBattle_OSGClass : UISettleBattleClass\n"
_SETTLE_TABS_SET = ("    self.list_Tab:SetOptions(optionList)\n"
                    "    self.list_Tab:SetSelect(CS.Timi.TimiMenuIndex(0), true)\nend\n")


def _settle_tab_names_fit() -> tuple[tuple[str, str], ...]:
    """The edit that keeps the match-end ranking screen's tab names (Lineup Combine, Post-game social,
    Championship collection, and Support details in an apex room) apart.

    Prefab `UISettleBattle` (package 19): `List_Tab` is a `TimiMenu` pinned to the top right (pivot on
    its right edge) with a horizontal layout (middle right, spacing 53) under a content size fitter.
    Each item (`UIPVPSettleBattleTabItem`) is a 144 x 60 cell whose names (`SelectTxt`, `UnSelectTxt`),
    the `Select` group and its underline are 144 wide and centred, so a longer English name overflows
    into its neighbours. Each cell (and those children of it that share its width) now widens to its own
    name plus 24 units a side, at one shared size; the bar grows left, which the layout does by itself.
    If the widened bar would reach the Feedback button (`btn_Problem`) less 40 units, every name shrinks
    by one factor to fit (never below 16). The prefab's sizes and widths are kept by instance id, so a
    rerun measures from them and never adds up. The fit runs when the tabs are set, on the next tick and
    half a second later, in case the menu builds its items late; a failure leaves the bar as the game
    drew it, logged as a Unity warning.
    """
    helper = ("local _settleTabSize = {}\n"
              "local _settleTabWidth = {}\n\n"
              "local function _fitSettleTabs(view)\n"
              "    local listTf = view.list_Tab.transform\n"
              "    local items = {}\n"
              "    for i = 0, listTf.childCount - 1 do\n"
              "        local item = listTf:GetChild(i)\n"
              "        if item.gameObject.activeSelf then\n"
              "            items[#items + 1] = item\n"
              "        end\n"
              "    end\n"
              "    if #items == 0 then\n"
              "        return\n"
              "    end\n"
              "    local cells = {}\n"
              "    local namesWidth, baseWidth = 0, 0\n"
              "    for _, item in ipairs(items) do\n"
              "        local base = _settleTabWidth[item:GetInstanceID()]\n"
              "        if base == nil then\n"
              "            base = item.rect.width\n"
              "            if base <= 0 then\n"
              "                return\n"
              "            end\n"
              "            _settleTabWidth[item:GetInstanceID()] = base\n"
              "        end\n"
              "        local labels = item:GetComponentsInChildren(typeof(CS.UnityEngine.UI.Text), true)\n"
              "        local cell = { item = item, base = base, labels = {}, name = 0 }\n"
              "        for i = 0, labels.Length - 1 do\n"
              "            local label = labels[i]\n"
              "            local size = _settleTabSize[label:GetInstanceID()]\n"
              "            if size == nil then\n"
              "                size = label.resizeTextForBestFit and label.resizeTextMaxSize or label.fontSize\n"
              "                _settleTabSize[label:GetInstanceID()] = size\n"
              "            end\n"
              "            label.resizeTextForBestFit = false\n"
              "            label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow\n"
              "            label.fontSize = size\n"
              "            cell.labels[#cell.labels + 1] = { label = label, size = size }\n"
              "            cell.name = math.max(cell.name, label.preferredWidth)\n"
              "        end\n"
              "        namesWidth = namesWidth + cell.name\n"
              "        baseWidth = baseWidth + base\n"
              "        cells[#cells + 1] = cell\n"
              "    end\n"
              "    local scale = 1\n"
              "    local layout = listTf:GetComponent(typeof(CS.UnityEngine.UI.HorizontalLayoutGroup))\n"
              "    local spacing = CommonUtility:NotNull(layout) and layout.spacing or 0\n"
              "    pcall(function()\n"
              "        local feedback = view.btn_Problem.transform\n"
              "        local limit = feedback:TransformPoint(CS.UnityEngine.Vector3(feedback.rect.xMax, 0, 0))\n"
              "        local barRight = listTf:TransformPoint(CS.UnityEngine.Vector3(listTf.rect.xMax, 0, 0))\n"
              "        local room = listTf:InverseTransformPoint(barRight).x - listTf:InverseTransformPoint(limit).x - 40\n"
              "        local fixed = 48 * #cells + spacing * (#cells - 1)\n"
              "        if room > fixed and namesWidth > 0 and namesWidth + fixed > room then\n"
              "            scale = (room - fixed) / namesWidth\n"
              "        end\n"
              "    end)\n"
              "    for _, cell in ipairs(cells) do\n"
              "        local name = cell.name\n"
              "        if scale < 1 then\n"
              "            name = 0\n"
              "            for _, entry in ipairs(cell.labels) do\n"
              "                entry.label.fontSize = math.max(math.floor(entry.size * scale), 16)\n"
              "                name = math.max(name, entry.label.preferredWidth)\n"
              "            end\n"
              "        end\n"
              "        local width = math.max(math.ceil(name + 48), cell.base)\n"
              "        local item = cell.item\n"
              "        local parts = item:GetComponentsInChildren(typeof(CS.UnityEngine.RectTransform), true)\n"
              "        for i = 0, parts.Length - 1 do\n"
              "            local part = parts[i]\n"
              "            if part ~= item and part.anchorMin.x == part.anchorMax.x then\n"
              "                local partBase = _settleTabWidth[part:GetInstanceID()]\n"
              "                if partBase == nil then\n"
              "                    partBase = part.rect.width\n"
              "                    _settleTabWidth[part:GetInstanceID()] = partBase\n"
              "                end\n"
              "                if math.abs(partBase - cell.base) < 1 then\n"
              "                    part:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Horizontal, width)\n"
              "                end\n"
              "            end\n"
              "        end\n"
              "        item:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Horizontal, width)\n"
              "        local element = item:GetComponent(typeof(CS.UnityEngine.UI.LayoutElement))\n"
              "        if CommonUtility:NotNull(element) then\n"
              "            element.preferredWidth = width\n"
              "        end\n"
              "    end\n"
              "    pcall(function() ForceRebuildLayoutImmediate(listTf) end)\n"
              "end\n\n"
              "local function _fitSettleTabsSafely(view)\n"
              "    local ok, err = pcall(_fitSettleTabs, view)\n"
              "    if not ok then\n"
              "        pcall(function() CS.UnityEngine.Debug.LogWarning(\"HOKACE settle tabs: \" .. tostring(err)) end)\n"
              "    end\n"
              "end\n\n")
    return ((_SETTLE_TABS_CLASS, helper + _SETTLE_TABS_CLASS),
            (_SETTLE_TABS_SET,
             _SETTLE_TABS_SET[:-len("end\n")]
             + "    _fitSettleTabsSafely(self)\n"
               "    pcall(function()\n"
               "        ScheduleService:SetTimeout(function()\n"
               "            if self:Available() then\n"
               "                _fitSettleTabsSafely(self)\n"
               "            end\n"
               "        end, 0)\n"
               "        ScheduleService:SetTimeout(function()\n"
               "            if self:Available() then\n"
               "                _fitSettleTabsSafely(self)\n"
               "            end\n"
               "        end, 0.5)\n"
               "    end)\n"
               "end\n"))


# The All Things Moment service (`ICreateSDKServiceClass`): where it builds the match-end tip from the
# server's notification.
_MOMENT_TIPS = ("            self.DemandTips = data.Response.BubbleText .. "
                "Localize.GetString(\"WanXiangReportShareTips\")\n"
                "        else\n"
                "            self.DemandTips = data.Response.BubbleTextDefault\n")


def _moment_tip_translated() -> tuple[tuple[str, str], ...]:
    """The edit that translates the match-end All Things Moment tip's highlight title.

    The tip is the server's highlight title (`BubbleText`, such as `五连绝世无人能挡`) joined to
    `WanXiangReportShareTips` (", tap to Generate All Things Moment report"), or the server's own default
    (`BubbleTextDefault`) when there is no title. Neither server text is in any table or asset, so a
    title is looked up in `_HOKACE_MOMENT_TITLES`, which `rewrite_script` fills from SCRIPT_TRANSLATIONS.
    A Chinese title or default the table lacks is dropped while the tip itself is translated: the tip
    shows alone, its leading comma removed and its first letter capitalised ("Tap to Generate All Things
    Moment report"). A failure keeps the game's own text.
    """
    helper = ("local function _hokaceHasCjk(text)\n"
              "    return type(text) == \"string\" and string.find(text, \"[\\228-\\233][\\128-\\191][\\128-\\191]\") ~= nil\n"
              "end\n\n"
              "local function _hokaceMomentTip(title, default)\n"
              "    local tip = tostring(Localize.GetString(\"WanXiangReportShareTips\"))\n"
              "    local ok, result = pcall(function()\n"
              "        local function tipAlone()\n"
              "            local text = string.gsub(tip, \"^\\239\\188\\140\", \"\")\n"
              "            text = string.gsub(text, \"^[%s,]+\", \"\")\n"
              "            return (string.gsub(text, \"^%l\", string.upper))\n"
              "        end\n"
              "        if title ~= nil then\n"
              "            local known = _HOKACE_MOMENT_TITLES[title]\n"
              "            if known ~= nil then\n"
              "                return known .. tip\n"
              "            end\n"
              "            if _hokaceHasCjk(title) and not _hokaceHasCjk(tip) then\n"
              "                return tipAlone()\n"
              "            end\n"
              "            return title .. tip\n"
              "        end\n"
              "        if _hokaceHasCjk(default) and not _hokaceHasCjk(tip) then\n"
              "            return tipAlone()\n"
              "        end\n"
              "        return default\n"
              "    end)\n"
              "    if ok then\n"
              "        return result\n"
              "    end\n"
              "    if title ~= nil then\n"
              "        return title .. tip\n"
              "    end\n"
              "    return default\n"
              "end\n\n")
    return _crlf((("---@class ICreateSDKServiceClass\n", helper + "---@class ICreateSDKServiceClass\n"),
                  (_MOMENT_TIPS,
                   "            self.DemandTips = _hokaceMomentTip(data.Response.BubbleText, nil)\n"
                   "        else\n"
                   "            self.DemandTips = _hokaceMomentTip(nil, data.Response.BubbleTextDefault)\n")))


_ENCYCLOPEDIA_TABS = "    self.mainMenu:SetOptions(optionList)\n    self.submenuListTimiList:SetSingleSelectMode()\n"
_ENCYCLOPEDIA_TAB_SPACING = """    self.mainMenu:SetOptions(optionList)
    local function fitMainMenu()
        if not self:Available() then return end
        local menu = self.mainMenu.transform
        local ui = CS.UnityEngine.UI
        local textType = typeof(ui.Text)
        local horizontal = CS.UnityEngine.RectTransform.Axis.Horizontal
        local items, width = {}, 344
        for i = 0, menu.childCount - 1 do
            local item = menu:GetChild(i)
            local selected = item:Find("Select/Txt_Select")
            local unselected = item:Find("UnSelect")
            if item.gameObject.activeSelf and CommonUtility:NotNull(selected) and CommonUtility:NotNull(unselected) then
                items[#items + 1] = item
                for _, tf in ipairs({ selected, unselected }) do
                    local label = tf:GetComponent(textType)
                    label.resizeTextForBestFit = false
                    label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
                    label.alignment = CS.UnityEngine.TextAnchor.MiddleCenter
                    label.fontSize = 38
                    width = math.max(width, math.ceil(label.preferredWidth + 48))
                end
            end
        end
        if #items == 0 then return end
        local total = width * #items
        local layout = menu:GetComponent(typeof(ui.HorizontalLayoutGroup))
        if CommonUtility:NotNull(layout) then layout.enabled = false end
        menu.parent:SetSizeWithCurrentAnchors(horizontal, total)
        menu:SetSizeWithCurrentAnchors(horizontal, total)
        menu.anchoredPosition = CSVector2(total / 2, menu.anchoredPosition.y)
        for i, item in ipairs(items) do
            item.anchorMin = CSVector2(0.5, item.anchorMin.y)
            item.anchorMax = CSVector2(0.5, item.anchorMax.y)
            item:SetSizeWithCurrentAnchors(horizontal, width)
            local x = width * (i - 1 - #items / 2 + item.pivot.x)
            item.anchoredPosition = CSVector2(x, item.anchoredPosition.y)
        end
    end
    pcall(fitMainMenu)
    pcall(function()
        ScheduleService:SetTimeout(function() pcall(fitMainMenu) end, 0)
    end)
    self.submenuListTimiList:SetSingleSelectMode()
"""


_ENCYCLOPEDIA_CARD_REFRESH = "    self:LowerUIRefresh()\nend\n"
_ENCYCLOPEDIA_CARD_SERIES = """    self:LowerUIRefresh()
    if self._curShowTabType == ResData.V8CardType.CardType_Talent then
        pcall(function() self:_FitTalentSeriesHeading() end)
    end
end

local talentSeriesGradient
local function getTalentSeriesGradient()
    if CommonUtility:NotNull(talentSeriesGradient) then return talentSeriesGradient end
    local unity = CS.UnityEngine
    local size = 16
    local texture = unity.Texture2D(size, size, unity.TextureFormat.RGBA32, false)
    texture.wrapMode = unity.TextureWrapMode.Clamp
    texture.filterMode = unity.FilterMode.Bilinear
    -- Match the card colors above and below the series row. Keep the center opaque over the glyphs.
    for y = 0, size - 1 do
        local v = y / (size - 1)
        for x = 0, size - 1 do
            local u = x / (size - 1)
            local edge = math.abs(2 * u - 1)
            local red = 20 - 2 * v + 3 * edge
            local green = 35 - 4 * v + (6 - 3 * v) * edge
            local blue = 31 - 5 * v + (5 - 2 * v) * edge
            local alpha = math.min(1, 8 * u, 8 * (1 - u), 6 * v, 6 * (1 - v))
            texture:SetPixel(x, y, unity.Color(red / 255, green / 255, blue / 255, alpha))
        end
    end
    texture:Apply(false, true)
    talentSeriesGradient = texture
    return texture
end

function UIGameAtlasCardInfoItemClass:_FitTalentSeriesHeading()
    local ui = CS.UnityEngine.UI
    local previews = self._rootTf:GetComponentsInChildren(typeof(ui.Text), false)
    for i = 0, previews.Length - 1 do
        local label = previews[i]
        local layout = label.transform.parent
        if label.name == "Txt_OSHType" and layout.name == "OSHTypeLayout" then
            local capture = layout.parent.parent:Find("Icon_Capture")
            if CommonUtility:NotNull(capture) and capture.gameObject.activeSelf then
                -- The captured card already contains the Chinese heading under this localized text.
                local plate = layout:Find("HokAceSeriesBackground")
                if not CommonUtility:NotNull(plate) then
                    local gradient = getTalentSeriesGradient()
                    local object = CS.UnityEngine.GameObject("HokAceSeriesBackground", typeof(CS.UnityEngine.RectTransform))
                    local image = object:AddComponent(typeof(ui.RawImage))
                    image.texture = gradient
                    image.raycastTarget = false
                    object:AddComponent(typeof(ui.LayoutElement)).ignoreLayout = true
                    plate = image.rectTransform
                    plate:SetParent(layout, false)
                    plate:SetAsFirstSibling()
                end
                plate.sizeDelta = CSVector2(math.min(layout.rect.width, math.max(245, label.preferredWidth + 16)), 44)
                label.color = CS.UnityEngine.Color(0.62, 0.86, 0.71, 1)
            end
        end
    end
end
"""


_PRIVILEGE_REFRESH_END = """        self:SetPlatformType(false)
    end
end

function UIPrivilegeInvitationItemClass:OnUIPrivilegeInvitationItemClickAction()
"""
_PRIVILEGE_ICON_GAP = """        self:SetPlatformType(false)
    end
    local function fitPrivilegeIcon()
        if not self:Available() then return end
        local group, iconPath, titlePath
        if self.channelType == OSProto.EAcntType.ACNT_TYPE_QQ then
            group, iconPath, titlePath = self.platformTypeRect1, "qqIcon", "textTitle"
        elseif self.channelType == OSProto.EAcntType.ACNT_TYPE_WX then
            group, iconPath, titlePath = self.platformTypeRect2, "weixinIcon", "textTitle1"
        else
            return
        end
        local icon = group:Find(iconPath)
        local title = group:Find(titlePath)
        local label = title:GetComponent(typeof(CS.UnityEngine.UI.Text))
        if label.preferredWidth <= 0 then return end
        local titleLeft = title:TransformPoint(CS.UnityEngine.Vector3(title.rect.center.x - label.preferredWidth / 2, 0, 0))
        local iconRight = icon:TransformPoint(CS.UnityEngine.Vector3(icon.rect.xMax, 0, 0))
        local delta = group:InverseTransformPoint(titleLeft).x - group:InverseTransformPoint(iconRight).x - 12
        icon.anchoredPosition = CSVector2(icon.anchoredPosition.x + delta, icon.anchoredPosition.y)
        local graphic = icon:GetComponent(typeof(CS.UnityEngine.UI.Graphic))
        if CommonUtility:NotNull(graphic) then graphic.raycastTarget = true end
    end
    pcall(fitPrivilegeIcon)
    pcall(function()
        ScheduleService:SetTimeout(function() pcall(fitPrivilegeIcon) end, 0)
    end)
end

function UIPrivilegeInvitationItemClass:OnUIPrivilegeInvitationItemClickAction()
"""


_CAREER_TAB_OPTIONS = "    self.tabList01:SetOptions(optionList)\n    self:UnRegisterCareerBusinessCardRedDot()\n"
_CAREER_TAB_SPACING = """    self.tabList01:SetOptions(optionList)
    local function fitCareerTabs()
        if not self:Available() then return end
        local ui = CS.UnityEngine.UI
        local textType = typeof(ui.Text)
        local horizontal = CS.UnityEngine.RectTransform.Axis.Horizontal
        local list = self.tabList01.transform
        local items, labels = {}, {}
        for i = 0, list.childCount - 1 do
            local item = list:GetChild(i)
            if item.gameObject.activeSelf then
                items[#items + 1] = item
            end
        end
        if #items == 0 then return end
        local width, targetSize = 252, 40
        local total = width * #items
        local size = targetSize
        local layout = list:GetComponent(typeof(ui.HorizontalLayoutGroup))
        if CommonUtility:NotNull(layout) then layout.enabled = false end
        list.parent:SetSizeWithCurrentAnchors(horizontal, total)
        list.anchorMin = CSVector2(0.5, list.anchorMin.y)
        list.anchorMax = CSVector2(0.5, list.anchorMax.y)
        list:SetSizeWithCurrentAnchors(horizontal, total)
        list.anchoredPosition = CSVector2(0, list.anchoredPosition.y)
        for i, item in ipairs(items) do
            item.anchorMin = CSVector2(0.5, item.anchorMin.y)
            item.anchorMax = CSVector2(0.5, item.anchorMax.y)
            item:SetSizeWithCurrentAnchors(horizontal, width)
            local x = width * (i - 1 - #items / 2 + item.pivot.x)
            item.anchoredPosition = CSVector2(x, item.anchoredPosition.y)
            local line = item:Find("Group/Select/Line_Select")
            if CommonUtility:NotNull(line) then
                line:SetSizeWithCurrentAnchors(horizontal, width)
            end
            for _, path in ipairs({ "Group/Select/Txt_Select", "Group/UnSelect/Txt_UnSelect" }) do
                local tf = item:Find(path)
                if CommonUtility:NotNull(tf) then
                    local label = tf:GetComponent(textType)
                    if CommonUtility:NotNull(label) then
                        label.resizeTextForBestFit = false
                        label.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
                        label.fontSize = targetSize
                        if label.preferredWidth > width - 36 then
                            size = math.min(size, math.floor(targetSize * (width - 36) / label.preferredWidth))
                        end
                        labels[#labels + 1] = label
                    end
                end
            end
        end
        for _, label in ipairs(labels) do
            label.fontSize = math.max(1, size)
        end
    end
    pcall(fitCareerTabs)
    pcall(function()
        local options = self._optionList
        ScheduleService:SetTimeout(function()
            if self._optionList == options then pcall(fitCareerTabs) end
        end, 0)
    end)
    self:UnRegisterCareerBusinessCardRedDot()
"""

_CAREER_STAT_TYPE = "    self:SetLine(true)\n    self:SetType(index - 1)\nend\n"
_CAREER_STAT_SPACING = """    self:SetLine(true)
    self:SetType(index - 1)
    if not (data and data.ShowName) then return end
    local function fitCareerStat()
        if not self:Available() or self.data ~= data then return end
        local button = self._rootTf:Find("Btn_CarrerDetail")
        local valueTf = button:Find("Txt_Num")
        if not CommonUtility:NotNull(valueTf) then
            valueTf = button:Find("Group/Txt_Num")
            valueTf:SetParent(button, false)
        end
        local textType = typeof(CS.UnityEngine.UI.Text)
        local value = valueTf:GetComponent(textType)
        local unit = button:Find("Group/Txt_Title"):GetComponent(textType)
        -- Keep the title binding for localization and draw the pair with a fixed space.
        if not unit.text or unit.text == "" then return end
        local center = CSVector2(0.5, 0.5)
        valueTf.anchorMin = center
        valueTf.anchorMax = center
        valueTf.pivot = center
        valueTf:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Horizontal, 172)
        valueTf.anchoredPosition = CSVector2(0, 0)
        value.alignment = CS.UnityEngine.TextAnchor.MiddleCenter
        value.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
        value.verticalOverflow = CS.UnityEngine.VerticalWrapMode.Overflow
        value.resizeTextForBestFit = false
        value.supportRichText = true
        -- The prefab draws the text about 20 units left of the cell center.
        -- The renderer centers the padding with the text, shifting the visible text right.
        local inset = "<color=#FFFFFF00>00 </color>"
        value.text = inset .. tostring(data.value or 0) .. " " .. unit.text
        unit.enabled = false
        -- Measure all three pairs together so a long count or label cannot shrink one on its own.
        local texts = self._rootTf.parent:GetComponentsInChildren(textType, false)
        local stats, size = {}, 27
        for i = 0, texts.Length - 1 do
            local stat = texts[i]
            if stat.name == "Txt_Num" and stat.rectTransform.parent.name == "Btn_CarrerDetail" then
                stat.fontSize = 27
                if stat.preferredWidth > 212 then
                    size = math.min(size, math.floor(27 * 212 / stat.preferredWidth))
                end
                stats[#stats + 1] = stat
            end
        end
        for _, stat in ipairs(stats) do
            stat.fontSize = math.max(1, size)
        end
    end
    pcall(fitCareerStat)
    pcall(function()
        local function refreshStat() pcall(fitCareerStat) end
        ScheduleService:SetTimeout(refreshStat, 0)
        ScheduleService:SetTimeout(refreshStat, 0.5)
    end)
end
"""

_LORD_DETAIL_LAYOUT = "    self:_RefreshLayout()\nend\n\nfunction UILordOverviewInfoItemClass:_RefreshLayout()"
_LORD_DETAIL_SPACING = """    self:_RefreshLayout()
    local function fitLordDetails()
        if not self:Available() then return end
        local root = self._rootTf
        local ui = CS.UnityEngine.UI
        local textType = typeof(ui.Text)
        local horizontal = CS.UnityEngine.RectTransform.Axis.Horizontal
        local overflow = CS.UnityEngine.HorizontalWrapMode.Overflow
        local function fit(label, size, width)
            label.resizeTextForBestFit = false
            label.horizontalOverflow = overflow
            label.fontSize = size
            if label.preferredWidth > width then
                label.fontSize = math.max(1, math.floor(size * width / label.preferredWidth))
            end
        end
        local operation = root:Find("Operation")
        local tabs = { { "Btn_Overview", "OverviewTxt" }, { "Btn_Strategy", "StrategyTxt" },
            { "Btn_GrowUp", "GrowUpTxt" } }
        local names, buttons, available = {}, {}, operation.rect.width
        local total, size = 0, 30
        for i, tab in ipairs(tabs) do
            buttons[i] = operation:Find(tab[1])
            names[i] = buttons[i]:Find(tab[2]):GetComponent(textType)
            fit(names[i], size, available)
            total = total + names[i].preferredWidth
        end
        local textRoom = available - 22 * #tabs
        if textRoom <= 0 then return end
        if total > textRoom then
            size = math.max(1, math.floor(size * textRoom / total))
        end
        total = 0
        for _, label in ipairs(names) do
            label.fontSize = size
            total = total + label.preferredWidth
        end
        local padding = (available - total) / #tabs
        local x = -available / 2
        for i, label in ipairs(names) do
            local button, tf = buttons[i], label.rectTransform
            local width = label.preferredWidth + padding
            button:SetSizeWithCurrentAnchors(horizontal, width)
            button.anchoredPosition = CSVector2(x + width / 2, -1)
            tf:SetSizeWithCurrentAnchors(horizontal, width - 12)
            tf:SetSizeWithCurrentAnchors(CS.UnityEngine.RectTransform.Axis.Vertical, 46)
            tf.anchoredPosition = CSVector2(0, 0)
            label.alignment = CS.UnityEngine.TextAnchor.MiddleCenter
            x = x + width
            if i < #tabs then
                local line = operation:Find("Line_Operation0" .. i)
                line.anchoredPosition = CSVector2(x, line.anchoredPosition.y)
            end
        end

        local title = root:Find("Name/NameGroup")
        local name = title:Find("Txt_Name"):GetComponent(textType)
        local skin = title:Find("Txt_SKinName"):GetComponent(textType)
        if skin.gameObject.activeInHierarchy then
            local layout = title:GetComponent(typeof(ui.HorizontalLayoutGroup))
            if CommonUtility:NotNull(layout) then layout.spacing = 10 end
            fit(name, 34, available * 0.42)
            fit(skin, 30, available * 0.49)
            UIUtility:ForceRebuildLayoutImmediate(title)
        else
            fit(name, 34, available)
        end

        if self._currentOpType == UILordOverviewInfoItemClassOperationType.GrowUp then
            local detail = root:Find("GrowUp/CombatPower/Btn_Detail")
            local icon = detail:Find("DetailIcon")
            local power = detail:Find("Info/Txt_CombatPower"):GetComponent(textType)
            local iconLeft = icon:TransformPoint(CS.UnityEngine.Vector3(icon.rect.xMin, 0, 0))
            local room = power.rectTransform:InverseTransformPoint(iconLeft).x - power.rectTransform.rect.xMin - 12
            if room > 0 then fit(power, 32, room) end
        end
        if self._currentOpType ~= UILordOverviewInfoItemClassOperationType.Strategy then return end
        local strategy = root:Find("Strategy/Strategy_Info")
        local strategyLabels = strategy:GetComponentsInChildren(textType, false)
        local difficulty, tags = nil, {}
        for i = 0, strategyLabels.Length - 1 do
            local label = strategyLabels[i]
            if label.name == "Txt_Diff" then
                difficulty = label
            else
                tags[#tags + 1] = label
            end
        end
        local tagRoom = math.max(20, (available - 230) / math.max(1, #tags) - 24)
        for _, tag in ipairs(tags) do fit(tag, 20, tagRoom) end
        if difficulty then pcall(function()
            fit(difficulty, 20, 92)
            local group = difficulty.rectTransform.parent
            local left = 8
            local tf = difficulty.rectTransform
            local width = difficulty.preferredWidth
            tf.anchoredPosition = CSVector2(left + width / 2, tf.anchoredPosition.y)
            for _, path in ipairs({ "Di_Diff", "Stage_Diff" }) do
                local markers = group:Find(path)
                local scale = 0.8
                markers.localScale = CS.UnityEngine.Vector3(scale, scale, 1)
                local x = left + width + 10 + markers.rect.width * scale / 2
                markers.anchoredPosition = CSVector2(x, markers.anchoredPosition.y)
            end
        end) end
        local list = root:Find("Strategy/LordSkillList")
        local captions = list:GetComponentsInChildren(textType, true)
        for i = 0, captions.Length - 1 do
            local caption = captions[i]
            if caption.name == "Txt_Type" or caption.name == "Txt_Type_Select" then
                fit(caption, 22, 102)
            end
        end
    end
    local function fitSafely()
        local ok, err = pcall(fitLordDetails)
        if not ok then CS.UnityEngine.Debug.LogWarning("HOKACE Chessplayer detail spacing: " .. tostring(err)) end
    end
    fitSafely()
    pcall(function()
        ScheduleService:SetTimeout(fitSafely, 0)
        ScheduleService:SetTimeout(fitSafely, 0.5)
    end)
end

function UILordOverviewInfoItemClass:_RefreshLayout()"""


# Lua UI scripts whose own formatting or behaviour is wrong for a translation: each entry is an exact
# source literal and its replacement, applied under the same once-only rule as SCRIPT_LABELS.
SCRIPT_EDITS: dict[int, tuple[tuple[str, str], ...]] = {
    # The Card screen's faction tabs (`UICollectionCampTabItemClass`, package 10, prime-only, so it is
    # appended): "Three Kingdoms" ran over the Zhulu Plateau icon on 1.9.2.4, and the other long names
    # crowded their neighbours. Every name now takes one shared size that fits its cell and the space
    # beside it, which the bar (`UICollectionTopCampTabClass`) records.
    0xA7D00B2D657BB71F: _camp_tab_names_fit()[0],
    0x678810D31DBD5621: _camp_tab_names_fit()[1],
    # The lobby (package 10; EFB6 is prime-only, so appended; the other two sit in the 1.9.2.4
    # override), 1.9.2.4: "Chessplayer" shrank to fit its button
    # while Card and Lineup did not (`UILobbyBtnItemClass`), and the Menu and Mall icons ran into their
    # names (`UILobbyClass`'s Menu button, `UILobbyMenuItemClass` while the red dot plays).
    0xEFB633FD63FC35CF: _lobby_btn_names_fit(),
    0x2C5B589676763044: _lobby_menu_icon_gap(),
    0xFC07FFAAB85F0418: _lobby_menu_button_gap(),
    # The lobby's Menu panel (`UILobbyMenuLittleItemClass`, package 10, in the 1.11 override), 1.11.0.2:
    # "Achievement", "Encyclopedia" and "Announcement" each shrank to fit their cells.
    0xD752489AB26CEFC8: _main_menu_names_fit(),
    # The Chessplayer page (`UILordListClass`, package 10, in the 1.11 override), 1.11.0.2: the
    # Chessplayer and Combat Power tab names ran into each other, and the Combat Power page's sort toggle
    # sat under the back title.
    0x428AF2481FE35A3A: _lord_list_header_fit(),
    # Career tab cells and stat units, and the Chessplayer character detail panel (package 10).
    0x314286AA90A60098: ((_CAREER_TAB_OPTIONS, _CAREER_TAB_SPACING),),
    0xC08C09E32934B2D1: _crlf(((_CAREER_STAT_TYPE, _CAREER_STAT_SPACING),)),
    0x3EF1BE086B77011A: _crlf(((_LORD_DETAIL_LAYOUT, _LORD_DETAIL_SPACING),)),
    # Career's Activate Privilege button (`UIPrivilegeInvitationItemClass`, package 10).
    0x89729889DF8FCE3B: _crlf(((_PRIVILEGE_REFRESH_END, _PRIVILEGE_ICON_GAP),)),
    # Encyclopedia's two game mode tabs (`UIGameAtlasClass`, package 10).
    0xFE5A2BCACD864638: ((_ENCYCLOPEDIA_TABS, _ENCYCLOPEDIA_TAB_SPACING),),
    # Encyclopedia Talent Card previews (`UIGameAtlasCardInfoItemClass`, package 10).
    0x5471D39F4D9063ED: _crlf(((_ENCYCLOPEDIA_CARD_REFRESH, _ENCYCLOPEDIA_CARD_SERIES),)),
    # The room (package 10, both in the 1.11 override, stored with CRLF line endings): "Lineup" and
    # "Settings" ran into their icons (`UIPVPRoomLeftDown_NormalClass`), and "Recommend" alone shrank
    # among the friend panel tabs (`UIPVPRoomNestedRecommendTabItemClass`).
    0x29FE6D03415A0971: _room_buttons_clear_of_icons(),
    0x7C2AE97D11BD7B4F: _room_tab_names_fit(),
    # The room's Super Weekend perk line (`UIPVPRoomClass:RefreshSettleAddBenefitTip`, package 10, LF):
    # it joins the perks of the bin `9E924AAB5066EE19` with a Chinese full-width comma, which read
    # "Double Diamonds from card flips 2/3，Shared Score with no Intimacy limit" on 1.11.0.2.
    0x31A01EDC4D72FCCE: (
        ('table.append(sourceDescList, table.concat(descList, "，"))',
         'table.append(sourceDescList, table.concat(descList, ", "))'),
        ('self.uiRoomTipInfoItemChild:SetTxtContent(table.concat(sourceDescList, "，"))',
         'self.uiRoomTipInfoItemChild:SetTxtContent(table.concat(sourceDescList, ", "))'),
    ),
    # The match-end ranking screen (`UISettleBattle_OSGClass`, package 10, in the 1.11 override),
    # 1.11.0.2: "Lineup Combine", "Post-game social" and "Championship collection" overflowed their
    # 144-unit tab cells and ran into each other.
    0x915E19AB90FFA1D9: _settle_tab_names_fit(),
    # The match-end All Things Moment tip (`ICreateSDKServiceClass`, package 10, in the 1.11 override,
    # CRLF), 1.11.0.2: "五连绝世无人能挡, tap to Generate All Things Moment report", the title being
    # the server's own text. Its titles are in SCRIPT_TRANSLATIONS.
    0xCC55DC213C5C6913: _moment_tip_translated(),
    # The match-end ranking toasts (package 10, prime-only, so they are appended): 1st to 3rd place
    # (`UIPvpSettlementRankingToastTopShowClass`, the button shows at 3rd) and 4th and lower
    # (`UIPvpSettlementRankingToastOtherShowClass`). Their "Exit now" button read 现在退出 on 1.8.0.1.
    0x08C73100FB914BF2: (_exit_button_label("UIPvpSettlementRankingToastTopShowClass"),),
    0x2D8E478FEE87C03D: (_exit_button_label("UIPvpSettlementRankingToastOtherShowClass"),),
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
    # UIPrefabClass (package 10, prime-only, so it is appended): the engine's `TextRendering` flag makes
    # every character a line-break point, the Chinese way, so a wrapped English line splits inside a word
    # ("Ancient Coi n"). Something outside Lua turns it on at startup and, mid-frame, as some screens and
    # list items open, so every UI prefab's Create turns it off before the prefab fills its text, and a
    # LateUpdate handler (registered from Create on the current Lua runner, again when the runner is
    # replaced) turns it off every frame, before Unity rebuilds the canvases. Device-verified 2026-10-23
    # on 1.7.0.2 (the Create reset) and 2026-11-02 on 1.8.0.1 (both; about 140 000 frames, the flag
    # caught on in 100): Card, Encyclopedia, lists and a match wrap between words.
    # `docs/features/latin-line-breaks.md`.
    0x3482BF89614B5ABB: (
        ("apply_decoration()\n---@param parentPrefabClass UIPrefabClass | "
         "Assets.Scripts.Framework.UI.UIPrefabBaseClass\n---@param parentTf UnityEngine.Transform\n"
         "function UIPrefabClass:Create(mediator, parentPrefabClass, parentTf, argument, customID, addCanvas, "
         "localScale, lifeType)\n    local resourcePath = self:vGetPath()\n",
         "local _setLineBreakFlag = nil\nlocal _lineBreakRunner = nil\n\n"
         "local function _resetLineBreakFlag()\n"
         "    if _setLineBreakFlag then\n        pcall(_setLineBreakFlag, false)\n    end\nend\n\n"
         "apply_decoration()\n---@param parentPrefabClass UIPrefabClass | "
         "Assets.Scripts.Framework.UI.UIPrefabBaseClass\n---@param parentTf UnityEngine.Transform\n"
         "function UIPrefabClass:Create(mediator, parentPrefabClass, parentTf, argument, customID, addCanvas, "
         "localScale, lifeType)\n"
         "    if _setLineBreakFlag == nil then\n"
         "        _setLineBreakFlag = false\n"
         "        pcall(function() _setLineBreakFlag = CS.UnityEngine.TextRendering.SetFlag end)\n"
         "    end\n"
         "    _resetLineBreakFlag()\n"
         "    pcall(function()\n"
         "        local runner = CoroutineService:GetRunner()\n"
         "        if runner ~= nil and runner ~= _lineBreakRunner then\n"
         "            _lineBreakRunner = runner\n"
         "            CoroutineService:AddLateUpdate(_resetLineBreakFlag)\n"
         "        end\n"
         "    end)\n"
         "    local resourcePath = self:vGetPath()\n"),
    ),
}
# Lua scripts that show text the server sends, which no table or asset holds: each entry names a Lua
# table an edit in SCRIPT_EDITS reads, and the Chinese texts to fill it with. `rewrite_script` declares
# the table at the top of the script with the catalog's translation of each (in the run's language, so
# the pairs live in `resources/catalog_supplement/texts.json`), leaving out any the catalog lacks.
SCRIPT_TRANSLATIONS: dict[int, tuple[str, tuple[str, ...]]] = {
    # The match-end All Things Moment tip's highlight titles, each seen on a phone.
    0xCC55DC213C5C6913: ("_HOKACE_MOMENT_TITLES", ("五连绝世无人能挡",)),
}
# Every Lua script the pass may write.
SCRIPT_ASSETS = frozenset(SCRIPT_LABELS) | frozenset(SCRIPT_EDITS) | frozenset(SCRIPT_TRANSLATIONS)
# The PC edition's package holding every SCRIPT_ASSETS script, the same Lua as the mobile edition's
# (azydev fork, 2026-11-18, PC 1.10.1.2). `pc_catalog` opens only this package for them; a script it
# lacks is looked for by a scan of every package's index, which the build logs.
SCRIPT_PC_PACKAGE = "10"
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
    if file_hash in SCRIPT_TRANSLATIONS:
        name, sources = SCRIPT_TRANSLATIONS[file_hash]
        # Declared only where an edit uses the table, and only once.
        if name.encode() in new and f"local {name} = ".encode() not in new:
            rows = []
            for source in sources:
                target = translate(source)
                if target and not any(char in target + source for char in '"\\\r\n'):
                    rows.append(f'["{source}"] = "{target}", ')
            line_end = "\r\n" if b"\r\n" in raw else "\n"
            new = f"local {name} = {{ {''.join(rows)}}}{line_end}".encode() + new
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
    the finished bin would leave the checksum stale. Every other asset goes through `pb_text.rewrite`,
    and one that was a sealed config bin is resealed after it (`_resealed`), or refused.
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
    if not changed:
        return None
    # The replacement comes from the catalog verbatim, so it carries the same {Energy}-style tokens the
    # staged path has to expand; the client would otherwise render them in Chinese.
    new = expand_tokens(new, log, terms)
    return _resealed(file_hash, raw, new, log)


def _resealed(file_hash: int, raw: bytes, new: bytes, log=None) -> bytes | None:
    """<new> resealed when <raw> is a sealed config bin, <new> itself when <raw> is not; None to refuse.

    The client checks field 4 of a sealed bin and frees a bin whose checksum is stale, so the game drops
    what it feeds (ADR 0005; the withdrawals above). A rewritten sealed bin therefore gets fields 1 and 4
    recomputed over its final bytes, after the token expansion, and is refused when it does not read back
    sealed.
    """
    try:
        sealed = config_bin.is_sealed(raw)
    except config_bin.NotConfigBin:
        sealed = False
    if not sealed:
        return new
    try:
        resealed = config_bin.encode(config_bin.reseal(config_bin.fields(new)))
        if config_bin.is_sealed(resealed):
            return resealed
        problem = "the resealed bin does not pass its own checksum"
    except config_bin.NotConfigBin as error:
        problem = f"the rewrite does not parse as a config bin ({error})"
    if log is not None:
        log(f"  {file_hash:016X}: sealed config bin not translated ({problem})")
    return None


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
