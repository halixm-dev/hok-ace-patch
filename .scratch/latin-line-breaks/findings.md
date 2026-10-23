# Latin line breaks: findings and next steps

Handoff, 2026-10-21. Nothing here has been on a phone.

## The problem

English and Indonesian text breaks inside words wherever a label wraps: card texts read "level s up", "Ancient Coi n", "refres h", "pe rmanently" (Card screen, every card description). The engine treats each Latin letter as a break point, the way it treats Hanzi.

## What a friend reported

Scanning HOK Global (`Honor+of+Kings_12.1.1.6_.apk`, in `artifacts/`) over USB debugging, Claude or Codex found a Tencent-made flag that switches text wrapping from Hanzi-style breaks to Latin-style breaks. We do not have their evidence yet: which method, which value, or how they read it.

## What we measured

| Where | Finding |
|---|---|
| HOK ACE `libunity.so` (Tencent's Unity fork) | Exports two native calls stock Unity lacks: `UnityEngine.TextRendering::LoadLinebreakingRules` and `UnityEngine.TextRendering::SetFlag`. The second is most likely the friend's flag. |
| HOK ACE `global-metadata.dat` | `TextRenderingBindings::SetFlag` and `LoadLinebreakingRules(TextAsset, TextAsset, TextAsset)` with parameters `isFollowingCharacters` and `numberCharacters`. Three resources feed it: `Font/LineBreakingLeadingCharacters`, `Font/LineBreakingFollowingCharacters`, `Font/NumberCharacters`. |
| HOK ACE Lua, package `10` | No Lua calls `SetFlag` or `LoadLinebreakingRules`. Chat's `TalkHelper` (`B8F9CB837E428E71`) says C# `GameFramework.cs` loads the rules, and its comments name the engine's `NativeTextGenerator` / `TextGenerator.cpp` (`InsertCharacter`, `RecoverWordWrap`). |
| HOK Global | `libunity_cp.so` and `libil2cpp_cp.so` are packed, so neither the flag nor its caller can be read statically. Its TextMeshPro kinsoku lists are the same CJK punctuation lists HOK ACE ships. |

## Two candidate levers

1. **Turn the flag on.** Call `CS.UnityEngine.TextRendering.SetFlag(<value>)` once at startup from a Lua edit, the same mechanism as `extra_text.SCRIPT_EDITS`. This needs the flag's meaning and value, and the call has to be reachable from xLua (no generated wrapper for `TextRendering` was found, so check whether xLua's reflection reaches it in this il2cpp build).
2. **Add Latin letters to `Font/NumberCharacters`.** If the generator keeps a run of "number characters" together, adding `A–Z a–z` (perhaps `'` and `-`) would keep words whole. This is a data-only change but it is an uncatalogued asset, so it needs the allowlist route and a device cycle.

Patching `libunity.so` is out: the normal APK changes only `AndroidManifest.xml` (`AGENTS.md`).

## Read statically, 2026-10-23

Steps 2 and 3 below are done; the evidence is in the lab notebook ("Latin line breaks: what
`TextRendering.SetFlag` does, read statically"). In short:

- `SetFlag(bool)` sets one byte on the native rules object. Flag **on**: every character except a digit, `/`
  or a `NumberCharacters` member is a break point, which is the "Coi n" break. Flag **off**: ordinary word wrap
  at spaces, with no rule set consulted.
- `Font/NumberCharacters` (package `1`) holds only block glyphs; no Latin letters.
- No caller of `SetFlag` was found statically. The device cycle below shows the flag **is** on in the shipped
  game, so a setter exists somewhere this pass did not read.
- Lever 3 (Lua builds a TextAsset and reloads only the number set) is out: `TextAsset` has no constructor in
  this build.

## Device cycle, 2026-10-23: partial

The probe (`probe/`) ran on the M2007J3SG with data 1.7.0.2; the evidence is in `probe/evidence/` and the lab
notebook ("Device cycle: the Latin line-break probe").

- The layout as the game started equals the `SetFlag(true)` layout, with mid-word breaks. So the flag is on.
- `CS.UnityEngine.TextRendering.SetFlag(false)` is reachable from xLua and returns without error. After it, the
  same sentence wraps at spaces, and every card description on Card > All wraps between words.

- **The flag comes back on within the session.** The Encyclopedia, and then the Card screen reopened, break
  words again. One call at the first rank title does not hold. The setter is not in Lua and not in the
  text-rendering icalls.

## Next steps

Probe v2 (2026-10-23) found that the flag comes back on as some Encyclopedia list items are instantiated.
Turning it off at the top of every `UIPrefabClass:Create` keeps the Card and Encyclopedia text wrapping
between words. Lever 1 is now an `extra_text.SCRIPT_EDITS` entry on `UIPrefabClass` (`3482BF89614B5ABB`)
that does exactly that, with no logging.

1. **Verify the shipped edit on a phone:** a normal build with the edit (`D:\scratch\latin-line-breaks\out-fix-catalog`),
   then walk Card, Encyclopedia (Effect, Hero, Talent and Equipment tabs), **a match**, a scene change and
   a re-login. None of these has been tested: if in-match text still splits words, its HUD needs a second
   hook. The reset answers a prefab that turns the flag on only at the next `Create`, so text that prefab
   lays out itself may still split. Probe v2's screens passed regardless.
2. **Check what flag-off costs** in the same cycle: Chinese the catalog leaves untranslated (no line-start
   rules for punctuation), chat (`TalkHelper` clamps punctuation runs for the flag-on generator), and
   Indonesian (`out-fix-catalog_id`).
3. **When it passes**, record the device verdict beside the entry in `tools/extra_text.py` and in
   `docs/translation-progress.md`. Then promote this folder to `docs/features/latin-line-breaks.md` and
   delete it (`docs/agents/issue-tracker.md`).
4. **Lever 2 is deferred, not dropped.** `NumberCharacters` with Latin letters would keep the flag on and keep
   the line-start rules for the Chinese that remains. Build it only if step 2 shows flag-off costs too much.
5. **Optional:** find the setter (a C# or native component on the Encyclopedia list items). It is not
   needed while the reset holds.
