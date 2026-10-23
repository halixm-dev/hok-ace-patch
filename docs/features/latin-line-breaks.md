---
feature: latin-line-breaks
status: built; device-tested on 1.7.0.2 (Card, Encyclopedia, a match)
updated: 2026-10-23
branch: master
commits: ed72898..HEAD
---

# Wrap translated text between words

## Report

Wrapped English used to split inside words ("Ancient Coi n", "level s up", "pe rmanently") on every card
description and in the Encyclopedia. It now wraps between words. The cause was one engine flag, and the fix
is one Lua edit that keeps it off.

| what landed | where |
|---|---|
| the reset: `TextRendering.SetFlag(false)` at the top of every `UIPrefabClass:Create` | `extra_text.SCRIPT_EDITS[0x3482BF89614B5ABB]` |
| the probes that found the flag and its setter, with their device evidence | `tools/research/latin_line_break_probe/` |

`UIPrefabClass` is prime-only, so the edit reaches the phone through the append pass. Both patchers carry it
(the Android patcher bundles `tools/`), for every language.

### Verification

- **Offline:**
  - The edit applies once to the APK's script and compiles under Lua 5.3. A second pass changes nothing.
  - Against a mocked engine, it turns the flag off, and `Create` still runs when `TextRendering` is missing.
  - English and Indonesian builds from the 1.7.0.2 snapshot both succeed, and read back with the call once.
    Only package `10` differs from the control.
- **On a phone** (M2007J3SG, data 1.7.0.2, 2026-10-23), the shipped build (`out-fix-catalog`, package `10`
  only): Card, Encyclopedia and a match wrap English between words.
- **Not checked yet:**
  - Re-login and other scene changes.
  - Chat. `TalkHelper` clamps punctuation runs for the flag-on generator.
  - Chinese that the catalog leaves untranslated, which now loses its line-start rules for punctuation.
  - Indonesian on a phone (built and read back only).

### Journey

Evidence and numbers are in `docs/lab-notebook.md`, in the 2026-10-23 entries starting with
"Latin line breaks: what `TextRendering.SetFlag` does, read statically".

1. **Static reading** of the APK's `libunity.so`, `libil2cpp.so` and `global-metadata.dat`:
   - `SetFlag(bool)` sets one byte on the native line-breaking rules object.
   - **Flag on:** every character that is not a digit, `/` or a `Font/NumberCharacters` member is a break
     point.
   - **Flag off:** ordinary word wrap at spaces.
   - `NumberCharacters` holds only block glyphs. No caller of `SetFlag` was found, which wrongly suggested the
     flag stays off.
2. **Probe v1** (once, at the first rank title): the flag **was on** at startup, and Lua can call `SetFlag`.
   Turning it off fixed the Card screen. But the Encyclopedia, and then the Card screen reopened, split words
   again: the flag comes back on.
3. **Probe v2** (read and reset on every `UIPrefabClass:Create`): the flag comes back on as Encyclopedia list
   items are instantiated (effect, hero, talent, equipment and lord items, and the hero card-level badge),
   from outside Lua. Resetting on every create kept the screens whole.
4. **The shipped edit** is probe v2's reset with no logging. It passed on the phone, the match included.

Withdrawn along the way:
- **A Lua-built rules file** (`LoadLinebreakingRules(nil, nil, TextAsset(…))`): `TextAsset` has no
  constructor in this build.
- **A single `SetFlag(false)` at startup:** it does not hold for the session.

## [S1] Problem

English and Indonesian text broke inside words wherever a label wrapped. The game's Unity fork has a
`TextRendering` flag that makes every letter a line-break point, the way the engine treats Hanzi. It is on in
the shipped game, and something outside Lua turns it on again during a session.

## [S2] Design

- **Lever 1 shipped: keep the flag off.** A `SCRIPT_EDITS` entry adds a module-level local to `UIPrefabClass`
  above `apply_decoration()`. It resolves `CS.UnityEngine.TextRendering.SetFlag` on the first `Create`.
  Every `Create` then calls it with `false` before `vGetPath()`, so the reset runs before a prefab fills its
  text. Both the lookup and the call are inside `pcall`, so a game build without the API only loses the fix.
- **A known gap.** A prefab that turns the flag on is answered at the next `Create`, not before its own text
  is laid out. No screen showed this.
- **Lever 2 deferred: `Font/NumberCharacters` with Latin letters.** This would keep the flag on and the
  line-start rules for Chinese. It needs a new asset kind (a TextAsset in package `1`) and its own device
  cycle. Build it only if flag-off turns out to cost too much for chat or untranslated Chinese.

## [S3] Out of Scope

- Patching `libunity.so`: the normal APK changes only `AndroidManifest.xml`.
- Finding the native or C# setter: not needed while the reset holds.
- HOK Global's flag (a friend's report): its libraries are packed, and HOK ACE did not need it.
