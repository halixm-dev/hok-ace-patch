---
feature: latin-line-breaks
status: lever 1 device-tested on 1.7.0.2; lever 2 withdrawn (fails on 1.8.0.1); lever 3 (per-frame reset) device-tested as probe v4 on 1.8.0.1, shipped build not yet run on a phone
updated: 2026-11-02
branch: master
commits: ed72898..HEAD
---

# Wrap translated text between words

## Report

Wrapped English used to split inside words ("Ancient Coi n", "level s up", "pe rmanently") on every card
description and in the Encyclopedia. It now wraps between words. The cause is one engine flag, and the fix
is one Lua edit that keeps it off. The first version reset the flag only when a UI prefab was created, and
words still split now and then (user report, 2026-11-02, data 1.8.0.1): the flag comes back on mid-frame,
and text laid out before the next `Create` split. The edit now also resets it every frame.

| what landed | where |
|---|---|
| the reset: `TextRendering.SetFlag(false)` at the top of every `UIPrefabClass:Create`, and in a LateUpdate handler every frame | `extra_text.SCRIPT_EDITS[0x3482BF89614B5ABB]` |
| the probes that found the flag, its setter and the per-frame reset, with their device evidence | `tools/research/latin_line_break_probe/` |

`UIPrefabClass` is prime-only, so the edit reaches the phone through the append pass. Both patchers carry it
(the Android patcher bundles `tools/`), for every language.

### Verification

- **Offline:**
  - The edit applies once to the APK's script (41 029 → 41 658 bytes) and compiles under Lua 5.3. A second
    pass changes nothing.
  - Against a mocked engine: the flag is off after `Create`; five creates register one handler; the handler
    turns the flag off; a new runner gets a new handler; `Create` still runs with no `CoroutineService` or
    no `TextRendering`.
- **On a phone, lever 1** (M2007J3SG, data 1.7.0.2, 2026-10-23), the shipped build (package `10` only):
  Card, Encyclopedia and a match wrap English between words. Shipped in Android patcher 1.7.2.2.
- **On a phone, lever 3 as probe v4** (M2007J3SG, data 1.8.0.1, 2026-11-02): the `Create` reset plus the
  per-frame reset with logging. About 140 000 frames over the lobby, Card, Encyclopedia, lists and a match;
  the flag was found on at the LateUpdate check in 100 of them, in bursts, and was reset each time. The user
  saw no word split. The shipped edit makes the same calls without the logging; it has not itself run on a
  phone yet.
- **Not checked yet:**
  - The shipped lever-3 build on a phone.
  - Re-login (the handler re-registers on a new runner; mocked only).
  - Chat. `TalkHelper` clamps punctuation runs for the flag-on generator.
  - Chinese that the catalog leaves untranslated, which now loses its line-start rules for punctuation.
  - Indonesian on a phone (built and read back only).

### Journey

Evidence and numbers are in `docs/lab-notebook.md`, in the 2026-10-23 entries starting with
"Latin line breaks: what `TextRendering.SetFlag` does, read statically", and the 2026-11-02 entries.

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
   items are instantiated, from outside Lua. Resetting on every create kept those screens whole.
4. **Lever 1 shipped**: probe v2's reset with no logging. It passed on the phone, the match included.
5. **Lever 2, withdrawn**: add the Latin letters to `Font/NumberCharacters`, so the flag-on generator never
   breaks inside a Latin word. Appended to package `1`, it built and read back, but words still split on the
   phone. Probe v3 showed why: `AssetService` serves the APK's copy (96 characters, no letters), most likely
   loaded before the override layer is read; feeding it to `LoadLinebreakingRules` from Lua changes nothing.
6. **Probe v4** (lever 3): reset every frame through `CoroutineService:AddLateUpdate`, and log each frame the
   flag is on at the check. `Canvas.preWillRenderCanvases` is not exposed to xLua, so LateUpdate is the
   latest per-frame hook Lua has. The flag was caught on in 100 of about 140 000 frames, and no word split.

Withdrawn along the way:
- **A Lua-built rules file** (`LoadLinebreakingRules(nil, nil, TextAsset(…))`): `TextAsset` has no
  constructor in this build.
- **A single `SetFlag(false)` at startup:** it does not hold for the session.
- **Lever 2** (above).

## [S1] Problem

English and Indonesian text broke inside words wherever a label wrapped. The game's Unity fork has a
`TextRendering` flag that makes every letter a line-break point, the way the engine treats Hanzi. It is on in
the shipped game, and something outside Lua turns it on again during a session, mid-frame.

## [S2] Design

- **Keep the flag off.** A `SCRIPT_EDITS` entry adds module-level locals and `_resetLineBreakFlag` to
  `UIPrefabClass` above `apply_decoration()`. The first `Create` resolves
  `CS.UnityEngine.TextRendering.SetFlag`. Every `Create` then:
  - calls it with `false` before `vGetPath()`, so the reset runs before a prefab fills its text;
  - registers `_resetLineBreakFlag` with `CoroutineService:AddLateUpdate` when the current runner
    (`CoroutineService:GetRunner()`) is not the one it last registered on. One handler per runner; a
    re-login that replaces the runner gets a new one.
- **Why LateUpdate.** Unity rebuilds canvases, laying out their text, after LateUpdate, so a flag turned on
  earlier in the frame is off again before that frame's text is laid out. A turn-on later in the same
  LateUpdate than this handler would still slip through for one frame; on the phone none was seen.
- **Failure.** The lookup, the calls and the registration are inside `pcall`, so a game build without the
  API only loses the fix.

## [S3] Out of Scope

- Patching `libunity.so`: the normal APK changes only `AndroidManifest.xml`.
- Finding the native or C# setter: not needed while the reset holds.
- HOK Global's flag (a friend's report): its libraries are packed, and HOK ACE did not need it.
