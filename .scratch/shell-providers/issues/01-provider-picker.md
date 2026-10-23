# 01: Shell provider picker and the provider seam

**What to build:** the groundwork both new providers stand on. A home-screen picker for the shell provider, remembered and changeable when no run is in progress; a seam in `WorkerDeviceConnection` so the worker can be started by something other than Shizuku; and the refusal of Shizuku running as uid 0. See the [spec](../spec.md), *Choosing a provider* and *Shared by all providers*.

- Picker with Shizuku, Wireless debugging (Beta) and Root (Beta); Shizuku is the default, and stays selected on a phone that already has a patch.
- Provider written in the diagnostic log header.
- One numbered guide per provider; the two new guides are placeholders until 02 and 03 fill them.
- Shizuku-specific strings become provider-specific; `GAME_MISSING` stays free of any provider name.
- `PrivilegedDeviceService` reads its uid at start: 2000 is today's path; 0 is refused until 03 lands; Shizuku at uid 0 gets *Shizuku is running with root. Choose the Root provider instead.*

**Blocked by:** none

**Status:** ready-for-agent

**Device test:** pass c69c251

- [x] Picker, persistence and log header, with unit tests
- [x] Starter seam: Shizuku is one implementation, behaviour unchanged
- [x] Rooted-Shizuku refusal
- [x] `tools/research/check_ui_strings.py` passes

## Comments

**Implementation (2026-10-24).** `ShellProvider` holds the choice (shared preferences `shell-provider`, Shizuku when nothing is saved) and `WorkerAccess` the worker's uid dispatch. `WorkerDeviceConnection` now takes a `WorkerStarter`; `ShizukuWorkerStarter` is today's two-path Shizuku start, moved unchanged, plus the refusal of a Shizuku server whose uid is 0. Wireless debugging and Root are `available = false` until 02 and 03: their guide says so, and Start and the worker refuse them. The home screen gains ② Shell provider; Start becomes ③ (`03  /  …` eyebrows, `NEEDS SHIZUKU` is now `NEEDS ACCESS`). The diagnostic export's second line is `Shell provider: <key>`. Unit tests: `ShellProviderTest`. The instrumented build was broken at HEAD (`DiagnosticLogExportProbeTest` calls a Kotlin default-argument constructor from Java); `@JvmOverloads` fixes it.

What to check on the phone: the picker persists across an app restart and locks while a run is in progress; Shizuku patch end to end unchanged (`WorkerBindingProbeTest`, `InterfaceProbeTest`); choosing Wireless debugging or Root shows the placeholder guide and Start refuses; Shizuku started with root shows the refusal; an exported log names the provider.

## Device findings

**2026-10-24, `c69c251`, Redmi Note 9 Pro (`ebad528e`, Android 15, KernelSU): pass.** Evidence in `docs/lab-notebook.md` (2026-10-24, ticket 01).

- Unit tests: 69 pass, 0 fail (`ShellProviderTest` 6). `check_ui_strings.py`: OK.
- Probes: `WorkerBindingProbeTest`, `FirstSetupWorkerGuardProbeTest`, `InterfaceProbeTest` (incl. `pickerChangesInterfaceAndPersistsAcrossRecreation`), `DiagnosticLogExportProbeTest`, `GuidedHomeProbeTest` pass (15 of 17).
- Picker: Shizuku selected by default; Root and Wireless debugging show their placeholder guide, ③ reads *Choose a shell provider*, Start starts nothing; the choice survives a force-stop; every option is disabled while a run is in progress, and a tap then changes nothing.
- Shizuku started as root (`su -c libshizuku.so`, server uid 0): ③ shows *Shizuku is running with root. Choose the Root provider instead.*; Start starts no worker process.
- Exported log: line 2 is `Shell provider: shizuku`.
- Shizuku end to end (worker `dev.halixm.hokacepatcher:device` as `shell`): Re-download, game update, full English patch `complete`, normal APK restored and verified, pristine delta of 14 files kept. The game started without `errorCode:361` and reached the lobby in English.

Not failures of this ticket, for whoever touches them next:

- `WorkerProbeTest` (2 tests) fails here on this commit and on the pre-01 app alike: it hardcodes another phone's normal-APK hash (`WorkerProbeTest.java:27`, `b0b08f…`), and this phone's recovery material is `63bec2…`.
- A user's explicit choice (Root) is kept across restarts on a phone that has a patch. Read as intended: *stays selected* applies to the default, not to an explicit pick.
- On Android 15 the footer row sits partly under the gesture bar at the bottom of the scroll; the page insets are unchanged by this commit.
- Running the probes leaves `worker-state.json` in an error state (`FirstSetupWorkerGuardProbeTest`, `WorkerProbeTest`), so ③ shows *Work stopped* until the next real run.

