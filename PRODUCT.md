# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

One product on two platforms: the **Windows patcher** (a desktop app that patches a phone connected
over USB) and the **Android patcher** (an app that patches the phone it runs on, through Shizuku).
Both follow one shared design (`DESIGN.md`) rather than each platform's native design language.

## Users

Players of 王者万象棋 (Honor of Kings: Ace, Chinese server) who don't read Chinese, mainly English
and Indonesian speakers, patching their own phone. They are comfortable enough to enable USB
debugging or install Shizuku when told how, but they are not developers: they follow the steps the
patcher gives them and rarely read logs.

## Product Purpose

Install an English or Indonesian translation into the game on an Android phone, without root, by
rewriting the game's own data packages. Success is a phone that opens the game with the translation
in place and the game still working, plus an honest report of what was applied and what stayed
Chinese.

## Positioning

A free community tool that translates the game's own data on the player's phone, with no root and no
modified game client beyond a re-signed copy of the game's own APK. It is unofficial and not
affiliated with Tencent.

## Operating Context

- **Windows patcher**: the player connects the phone by USB with USB debugging allowed, picks a
  language and a working folder (about 8 GB), and clicks Start. It runs seven device steps: connect
  phone, prepare game APK, unlock data access, read language data, build translation, install
  translation, restore game.
- **Android patcher**: the player installs Shizuku, picks a language and taps Start. The patcher
  checks and recovers unfinished work before patching, asks for explicit consent before anything
  destructive, and keeps recovery tools for a game that won't open.
- The translation is written only after the in-game update finishes. During a run the game must stay
  closed. Afterwards the player logs in with *Scan to login*, because re-signing breaks direct
  WeChat/QQ login.
- Releases are published on GitHub (`halixm-dev/hok-ace-patch`). The Android patcher checks for
  updates only when the player asks.

## Capabilities and Constraints

- Coverage is partial: catalog text tables, catalog edits, two Career-atlas labels and one Lua label.
  Some game text always stays Chinese. Never call it a complete translation.
- Switching language, or applying a newer translation, currently requires clearing the game's data
  first. Repatching without a clear is specced (`.scratch/language-switch/`) but not shipped.
- First setup on an officially signed game deletes local game data and needs a fresh download
  (about 1.7–2.7 GB) and a new login. Consent checkboxes start unchecked.
- The interface is in English or Indonesian, following the chosen translation. Technical logs stay
  untranslated.
- Vocabulary follows `GLOSSARY.md` (Windows patcher, Android patcher, normal APK, access APK,
  override layer, and so on).

## Brand Commitments

- Name: **HOK ACE Language Patcher**. Self-description: a community patcher.
- Unofficial and not affiliated with Tencent. It must never look or read like a Tencent product: no
  Tencent artwork, logos, images or fonts.
- Honest about coverage: always says some game text stays Chinese, and reports counts as *applied*.
- Voice: plain, calm instructions that put the game's safety first ("Keep the game closed"). Warnings
  state the consequence and the next step; they never alarm or blame.

## Evidence on Hand

- `docs/translation-progress.md`: the measured coverage ledger.
- `docs/lab-notebook.md`: device and pipeline evidence, the single source for numbers and verdicts.
- No testimonials, user counts or press exist. Don't invent them.

## Product Principles

1. **The game's safety comes first.** Every flow protects the player's game and data; anything
   destructive needs explicit, informed consent.
2. **Honest about what it did.** Report what was applied and what was skipped; never promise a
   complete translation.
3. **One product on two platforms.** Same steps, same words, same look, wherever the platforms allow.
4. **Clear, guided steps.** Players follow instructions, so each screen says what to do next in
   plain language, in their language.

## Accessibility & Inclusion

Interface text in English and Indonesian. Text scales with the Android system font size and with
Windows display scaling.
