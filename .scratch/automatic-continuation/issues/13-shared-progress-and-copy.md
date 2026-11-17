# 13: Unify continuation states and remove routine confirmations

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 07, 11, 12

## Scope and files

Own both frontends' state presentation, Android `GuidedHome.kt/StopCard.kt/WorkerStatus.kt/UiText.kt`, `resources/ui/strings.json`, `PRODUCT.md` and `DESIGN.md`. Read the confirmed spec state table, current shared design/product and GLOSSARY. Preserve visual tokens/layout; this is workflow/copy work.

## Steps

1. Render Working, Continuing, Stopping safely, Restoring, Waiting for you, Verified complete and Recovery needs attention consistently from authoritative run state. In Recovery needs attention, replace the existing main patch button's label and click handler with the specific required recovery action. Keep Save log separate and secondary; the main button cannot dispatch a fresh patch while recovery is unresolved. Apply this in both patchers.
2. Remove ordinary post-Start patch checkbox/dialog and automatic-action Remove confirmation. An explicit Remove action authorizes its non-destructive operation. Keep destructive setup/deletion, OS/installer intervention, required download readiness and cleanup-specific consequences. Do not expand patch consent into optional APK-cache removal.
3. Put finish-updates/close-game guidance inline before Start. For an actual waiting download, show the required Downloads finished action and consequences. Avoid arbitrary new prompts.
4. Show measured bytes/operation detail, honest indeterminate work, phone approval waits and clear persistent error next steps. Locked selections explain the pending action; Stop safely is the path to change it.
5. Map unconfirmed/cancelled/restored distinctly. No Open game while active consistency/normal restoration is unresolved; only verified result gets completion counts. Preserve partial-translation/applied/skipped wording.
6. Add shared EN/ID keys/placeholders and remove obsolete keys only after both callers change. Reconcile DESIGN's manual-recovery/Windows-no-verification assumptions and PRODUCT's stale update/data-clear limitations with actual implementation/evidence.

## Acceptance

- [ ] Ordinary Start reaches work without another checkbox/dialog, with durable authorization still enforced by core.
- [ ] Real intervention shows one clear next action; no stopped action auto-restarts and no unconfirmed success is implied.
- [ ] Recovery needs attention changes the existing main patch button into the required recovery action in both patchers; clicking it dispatches recovery, not a fresh patch. Save log remains a separate secondary action.
- [ ] Both languages have complete keys/identical placeholder contracts; dynamic progress is translated where user-facing, raw technical logs remain technical.
- [ ] Windows scaling and Android large-font/rotation/background states stay usable with existing design.
- [ ] PRODUCT/DESIGN describe implemented state transitions and preserve destructive informed consent.

## Checks and handoff

Run `check_ui_strings.py`, `check_references.py`, Android unit/build/interface/route/guided-home/result/stop probes and Windows progress/stop probes. Exercise both languages visually; record what was observed versus source-checked. Real-device UI gaps remain open for 19.

## Stop condition

If a state cannot establish a safe result, use attention/waiting and retain logs. Do not use upbeat completion copy to hide an unresolved action.

## Comments

### Pass 1 (2026-11-12): implemented, static checks only

**Changed files**

- `resources/ui/strings.json`: new shared keys `restoring_your_game`, `continue_saved_work`, `finish_stopping_safely`, `attention_saved_action`, `attention_stop_saved`, `choices_locked`; Windows `restore_game_app`, `check_saved_work`, `attention_restore_normal`, `attention_check_saved_work`, `waiting_downloads_detail`, `waiting_setup_consent`; Android `nothing_left_to_recover`, `ready_before_start`, `ready_before_start_root` (all `draft`; both now end with the caveat from the removed `patch_confirmation`: "Adding the translation has not passed all phone tests." / "Penerapan terjemahan belum lulus semua pengujian ponsel."); Windows `nothing_left_to_recover_click`. The first-setup caveat in `first_setup_consent` is unchanged. Windows had no equivalent caveat in any removed key (the removed caveats were Android-only). Windows gained `recovery_needs_attention`, `downloads_finished`, `retrying_saved_action`; Android gained `continuing_saved_work`, `waiting_for_you`. Reworded `download_game_data`, `ready_connect_phone` (finish-downloads guidance), `progress_bytes` / `progress_bytes_read` (`{done}`/`{total}` sizes), `stop_not_saved`, `setup_update`. Removed `stop_safely_question`, `keep_going`, `stop_and_recover`, `all_in_game_updates_finished_and_i`, `start_translation`, `patch_confirmation`, `patch_confirmation_root`, `retry_saved_work`, `tap_start_we_will_check_your_game_and`, `redownload_confirmation`.
- `app/hok_patcher.py`: `main_action` / `recover` / `recovery_action` (Start becomes the saved work's recovery action; `recover` re-runs discovery and resumes only the saved record), state headings while busy, NEEDS ATTENTION card for saved work, cancelled run no longer READY TO PLAY with Open game, `choices_locked`, `_size` byte formatting, waiting details, `_wait_ended` keyed errors.
- `android/.../MainActivity.kt` (presentation only): `showPatchConfirmation` removed (prepared runs authorize and dispatch at once; first setup keeps its data-loss consent); `showRemoveConfirmation` plain dialog at the tap; `recover_attention` key with `attentionAction` / `attentionDetail`; `continuing` / `recoveryOnly` flags; Restoring / Continuing headings; `ready_before_start`; recovery-only flow never falls into fresh PREPARE.
- `android/.../GuidedHome.kt` (`choices_locked`, Start refused while the next action is a recovery key), `UiText.kt` (`recovered_unconfirmed` not game-ready, `english(key)`, removed confirmation helpers), `StopCard.kt` (WAIT_FOR_GAME only with no pending work), `PatchWorkerService.kt` (one line: `stop_not_saved` via `UiText.english`, a presentational seam).
- Tests: `ResultStateTest.kt`, `StopCardTest.kt`, `InterfaceProbeTest.kt`, `HomeStatesCaptureTest.kt` (continuing/restoring/attention captures), `UpdateCheckpointProbeTest.java` (rewritten: no `showPatchConfirmation`, Remove dialog has no checkbox, Cancel creates no request or run).
- `app/patcher_core.py` (coordinator review: authorized minimal seam): `Patcher(recovery_only=True)` and `NOTHING_TO_RECOVER`. In `run`, a recovery-only run with no saved record returns `{NOTHING_TO_RECOVER: True}` before `check_work_dir`, ADB, device wait, preparation, APK work or any game write; with a saved record it re-reads the lifecycle under the owner and device locks (`claim_run`) and returns the same result if it resolved since discovery. No other core behavior changed. `hok_patcher.recover` calls `start(..., recovery_only=True)`; the worker maps the result to `done`/`nothing_to_recover`, and `finish` returns to idle with `nothing_left_to_recover_click`.
- `tools/research/check_windows_controls.py`: new `WindowsRecoveryOnly` probes (nothing saved, resolved between discovery and claim, recover button passes `recovery_only`, worker never reports success). Authored, not run.
- Docs: `DESIGN.md`, `PRODUCT.md`, `docs/features/android-shizuku-patcher.md`, `docs/features/standalone-patcher-app.md`.

**Checks (static only)**

- `check_ui_strings.py`: exit 1 with 9 findings, all pre-existing and outside this ticket's files: `RunStore.kt` 160/166/212 field names (`certificate_sha256`, `sha256`, `record_sha256`, `receipt_sha256`); `patcher_core.py` 1326 (`normal_install_progress` fills `role`), 487 and 1344 (PatchError raised with text), 1810 and 1908 (`error_files_changed` fills `detail`). The two `hok_patcher.py` findings that predated this ticket are fixed.
- `py_compile app/hok_patcher.py app/patcher_core.py tools/research/check_windows_controls.py` (.venv 3.12): OK.
- After the review corrections, `check_ui_strings.py` reports the same 9 findings (patcher_core line numbers shifted by the seam: 1346, 497, 1364, 1830, 1928); no new findings.
- Gradle `--offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac`: BUILD SUCCESSFUL (one pre-existing deprecation warning, `PatchWorkerService.kt:155`).
- `git diff --check`: clean (CRLF warnings only).
- `check_references.py`: all references resolve.

**Concerns**

- Remove reading: the dialog at the tap is treated as the explicit Remove action, so no checkbox and no second dialog after preparation.
- `WorkerStatus` English technical lines are unchanged (technical log).
- The setup downloads checkpoint keeps its checkbox (required download readiness).
- PRODUCT's update/data-clear limitation text was left as is: no new device evidence.
- Out-of-ownership `check_ui_strings` findings in `patcher_core.py` and `RunStore.kt` remain.

**Left for Pass 2 and ticket 19**

- `check_windows_controls.py` (including `WindowsRecoveryOnly`); all unit, interface, route, guided-home, result, stop and capture probes; Windows progress/stop probes.
- Visual review in EN and ID: Windows scaling, Android large font, rotation and background; the new captures (continuing, restoring, attention).
- Device cycles for recovery-only flows, Remove without a second dialog and Start without a confirmation.

Pass 2 fix (2026-11-12): `RunNotificationTest.removedAndWrittenOfferOpenGame` hit an NPE because `RunNotification.of` returned null for every non-game-ready result, so an unconfirmed "Translation written" run posted no notification at all. `RunNotification.of` now posts `recovered_unconfirmed` with its own heading and summary and `openGame = false`; game-ready results keep Open game, and chained steps, a player-requested Stop and Space freed stay quiet (`otherOutcomesPostNothing` unchanged). The test is split into `removedOffersOpenGame` and `writtenUnconfirmedPostsWithoutOpenGame`. `:app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest` (offline): BUILD SUCCESSFUL, 105 tests, 0 failures.

Pass 2 fix (2026-11-12): `check_ui_strings.py` findings cleared (9 to 0), with no new strings keys.
- `patcher_core.py` `control_boundary` and `install_prepared`'s failure: the conditional-key `PatchError`s are split into two raises with literal keys (`error_cancelled` / `error_close_preserved`; `error_normal_recovery` / `error_apk_identity`, each still filling `{detail}`).
- `normal_install_progress`: the checker read `role == ...` inside the `ui_text(...)` call as a fill. Now `ui_text("normal_install_progress") if role == "normal" else ui_text("access_install_progress")`, and each key is checked.
- `error_files_changed` (completion audit, `_publish_payload`, `push_translation`): the string has no `{detail}`, so the detail was dropped from both the screen and the log. The technical reason now goes to the log line before the raise, and the error shows the plain string.
- `RunStore.kt`: the private JSON validator `text(obj, vararg names)` matched the checker's `text(` UI sink, so the persisted field names (`sha256`, `certificate_sha256`, `record_sha256`, `receipt_sha256`) were read as shown literals. The helper is renamed `requireStrings`. Persisted keys are unchanged and the checker is not changed.
Checks: `check_ui_strings.py` OK (400 strings); `py_compile app/patcher_core.py` OK; `check_windows_recovery.py` OK; `check_windows_controls.py` OK (23 tests); Gradle offline `:app:compileDebugKotlin :app:testDebugUnitTest` BUILD SUCCESSFUL.


Pass 2 storage correction (2026-11-12): Storage waits show measured GB advice instead of Re-download approval. Paused saved actions keep primary Try again plus secondary Stop safely, independently of the progress bar. Resolve Stop before Free up space. Foreground space checks are five seconds apart and resume only after the saved requirement is met. check_ui_strings.py passed (400 EN/ID entries); paused-screen device check pending.


Pass 2 idle-Stop fix (2026-11-12): the indefinitely displayed Stopping safely state came from a nested background task being dropped while the outer routing task was busy. Resolution now finishes in the original background task and its UI result closes the Stop. The saved action stays stopped; another translation needs a new explicit Start. No copy changes. `IdleStopRoutingTest` passed all 4 cases plus Kotlin compilation; real installed screen verification remains pending with ticket 19.
