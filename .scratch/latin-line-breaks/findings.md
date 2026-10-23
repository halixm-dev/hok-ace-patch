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
- No caller of `SetFlag` was found (no icall string in `libil2cpp.so`, no native call, no Lua), so the binary
  says the flag stays off. That contradicts the Card screen and TalkHelper's own comments, which both need the
  flag on. Open question: is there a setter this pass missed, or is card text wrapped by something else?
- Lever 3 (Lua builds a TextAsset and reloads only the number set) is out: `TextAsset` has no constructor in
  this build.

## Next steps

1. **Ask the friend for evidence** (unchanged): which symbol and value they saw in HOK Global, and where it is
   called.
2. **Settle the flag on a phone, one Lua line at startup**, as a throwaway build (not a shipped
   `SCRIPT_EDITS` entry): log `CS.UnityEngine.TextRendering` reachability, then call `SetFlag(false)` and look
   at the Card screen. If words wrap whole, the flag was on and lever 1 works. If the call errors (no compiled
   body), lever 1 is out. If nothing changes, the Card screen does not use this generator.
3. **If the flag is on**, prefer lever 2: append `A–Z a–z` to `Font/NumberCharacters`. This keeps the
   kinsoku rules for the Chinese that remains, where lever 1 drops them. It is a new asset kind for the
   pipeline (a TextAsset in an LZ4 SerializedFile in package `1`; `unity_text.SerializedFile` reads the object
   table). Build it as a device-cycle candidate, off by default, then prove it on the Card screen with a control
   build one variable apart (`docs/runbooks/device-cycle.md`).
