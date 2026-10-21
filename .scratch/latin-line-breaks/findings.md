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

## Next steps

1. **Ask the friend for evidence:** the method or symbol they found in HOK Global, the value it is set to, where it is called (C#, Lua, or native), and how they read a packed library (a memory dump while the game runs?).
2. **Read `SetFlag` in HOK ACE:** disassemble the native `TextRendering::SetFlag` in `libunity.so` and the word-wrap path in `TextGenerator` to learn what each flag bit changes. Dump `libil2cpp.so` with `global-metadata.dat` (it reads unencrypted) to find `GameFramework`'s call site and the value HOK ACE passes today.
3. **Find `Font/NumberCharacters`** in the game data (the QTS packages through `QtsPackage`, in both data layers), and read its current contents.
4. **Choose a lever** from what steps 1–3 show, then prove it on a phone, Card screen first, with a control build one variable apart (`docs/runbooks/device-cycle.md`). Record the result in the lab notebook.
