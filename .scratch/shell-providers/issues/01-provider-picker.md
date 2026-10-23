# 01: Shell provider picker and the provider seam

**What to build:** the groundwork both new providers stand on. A home-screen picker for the shell provider, remembered and changeable when no run is in progress; a seam in `WorkerDeviceConnection` so the worker can be started by something other than Shizuku; and the refusal of Shizuku running as uid 0. See the [spec](../spec.md), *Choosing a provider* and *Shared by all providers*.

- Picker with Shizuku, Wireless debugging (Beta) and Root (Beta); Shizuku is the default, and stays selected on a phone that already has a patch.
- Provider written in the diagnostic log header.
- One numbered guide per provider; the two new guides are placeholders until 02 and 03 fill them.
- Shizuku-specific strings become provider-specific; `GAME_MISSING` stays free of any provider name.
- `PrivilegedDeviceService` reads its uid at start: 2000 is today's path; 0 is refused until 03 lands; Shizuku at uid 0 gets *Shizuku is running with root. Choose the Root provider instead.*

**Blocked by:** none

**Status:** ready-for-agent

**Device test:** requested

- [x] Picker, persistence and log header, with unit tests
- [x] Starter seam: Shizuku is one implementation, behaviour unchanged
- [x] Rooted-Shizuku refusal
- [x] `tools/research/check_ui_strings.py` passes

## Comments

**Implementation (2026-10-24).** `ShellProvider` holds the choice (shared preferences `shell-provider`, Shizuku when nothing is saved) and `WorkerAccess` the worker's uid dispatch. `WorkerDeviceConnection` now takes a `WorkerStarter`; `ShizukuWorkerStarter` is today's two-path Shizuku start, moved unchanged, plus the refusal of a Shizuku server whose uid is 0. Wireless debugging and Root are `available = false` until 02 and 03: their guide says so, and Start and the worker refuse them. The home screen gains ② Shell provider; Start becomes ③ (`03  /  …` eyebrows, `NEEDS SHIZUKU` is now `NEEDS ACCESS`). The diagnostic export's second line is `Shell provider: <key>`. Unit tests: `ShellProviderTest`. The instrumented build was broken at HEAD (`DiagnosticLogExportProbeTest` calls a Kotlin default-argument constructor from Java); `@JvmOverloads` fixes it.

What to check on the phone: the picker persists across an app restart and locks while a run is in progress; Shizuku patch end to end unchanged (`WorkerBindingProbeTest`, `InterfaceProbeTest`); choosing Wireless debugging or Root shows the placeholder guide and Start refuses; Shizuku started with root shows the refusal; an exported log names the provider.
