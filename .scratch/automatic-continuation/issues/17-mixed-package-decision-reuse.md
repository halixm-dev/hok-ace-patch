# 17: Reuse mixed-package decisions within a verified session

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 09, 12

## Scope and files

Own bridge `_restore_pristine/_restore_package/_mixed_packages/plan_redownload` and affected asset/update offline probes. Read asset-restore/update-stuck-redownload features, ADR 0008 and architecture section 4. Windows mixed-package support is outside scope.

## Steps

1. Measure copies, trial restores, decoded/hashed bytes and duration for build refusal→Re-download classification using one snapshot.
2. Introduce a scoped verified decision object keyed by complete snapshot/delta/engine identity and recorded restore-refused inputs. Keep it in the same trusted session invocation; a restart requires fresh validation before reuse.
3. Reuse proven accepted restored copies when useful, and reuse refused package/deletion decisions when the exact inputs match. Preserve source immutability and storage reservations.
4. Any restore error/layout/token mismatch or changed input invalidates that decision and falls back to existing refusal/Re-download consent behavior.
5. Keep approved deletion scope equal to the freshly computed control. Never extend consent merely because a cached classification names more files.

## Acceptance

- [ ] Control/change give identical restored/refused package sets, output hashes and exact Re-download plans.
- [ ] Same verified path does fewer duplicate trial copies/restores where measured.
- [ ] Changed snapshot/delta/engine/refusal record and corrupt kept body cannot reuse a decision.
- [ ] Existing appended-survivor, record-token/chunk-shape and allowlist gates remain intact.

## Checks and handoff

Run affected `check_asset_restore.py`, `check_update_repatch.py` and `check_update_redownload.py` with the actual external fixture arguments those scripts require, plus bridge-continuation/pristine checks. Read `--help` before executing fixture-dependent commands. Run staging-contract check if pipeline behavior/docs changed. Record measured gain or a no-change verdict.

## Stop condition

If passing a decision safely would reuse it outside its proof lifetime, keep the repeated check. Do not persist a verdict as trusted solely because its JSON survived.

## Comments

### Pass 1 (2026-11-12): implemented, compiled, not run

Every acceptance box stays unchecked. No probe, offline bridge or pipeline run, device, adb or real-game operation ran. Nothing was committed.

**Changed files**

- `android/app/src/main/python/android_bridge.py`:
  - Process-memory decision store `_MIXED_DECISIONS`: keyed by the resolved session snapshot folder, holds at most `MIXED_DECISION_LIMIT` = 4 entries, lock-guarded and never written to disk, so a restart always decides afresh. Counters `MIXED_DECISION_STATS`: computed, reused, recorded, invalidated, unproven, restores, copied_bytes, proof_bytes, decide_seconds. `_forget_mixed_decisions()` simulates a restart for probes.
  - Proof:
    - `_mixed_evidence` measures the resolved snapshot path, the complete caller-verified manifest, and the bytes of the kept delta (bodies included), staged hashes, `restore-refused.json` and `redownload.json`. It also measures every engine file except `__pycache__`. Any link, junction or unreadable input gives None, which means nothing is recorded or reused.
    - `_mixed_proof` adds the complete rebuild report.
    - Helpers: `_hash_unlinked`, `_engine_files`, `_kept_decision` (drops a stale entry for the same snapshot and counts it `invalidated`), `_record_decision`, and `_mixed_refusal` (the unchanged `UPDATE_MIXED` text, factored out).
  - `_decide_mixed` also returns the packages whose restore failed. `_record_decision` keeps a decision only when the evidence measured the same before and after deciding and no restore failed. A failed restore may be transient (space, I/O), and reusing it could widen the plan.
  - `_restore_package`: only adds the restore and copied-byte counters.
  - `_mixed_packages(..., engine=None)`: reuses a kept refusal with zero trial copies; otherwise it decides and records.
  - `_restore_pristine(..., engine=None)`:
    - Reuses only a kept non-empty refusal: it raises the identical refusal without restoring.
    - A decision that took every package is always recomputed, because the build needs the restored copies.
    - Restored copies are never reused or moved, so snapshot immutability and the `_copy_bytes` reservations are unchanged.
  - Callers that verify the snapshot just before pass `engine=root`: `build_snapshot`, `build_removal` and `_plan_redownload` (which covers `plan_redownload` and `redownload_plan`). Research callers without `engine` and `manifest` behave exactly as before.
- `tools/research/check_asset_restore.py`: new `check_decision_reuse`, which runs after `check_android` on a real engine copy. It covers:
  - Fresh controls: the junction engine is unproven, so nothing is recorded.
  - A build refusal records its decision. The plan after it reuses it with 0 restores and 0 bytes copied; its plan and staged hashes equal the control.
  - A second plan and a second build reuse it, with identical refusal text.
  - A restart recomputes.
  - A changed `restore-refused.json`, delta or engine each invalidates the entry and recomputes, matching a fresh control. Undoing the change recomputes again.
  - A corrupt kept body refuses with no reuse and no record.
  - Another session, and a changed snapshot manifest in the same session, recompute.
  - A faked out-of-space restore is not kept, and the retry plans no more than the control.
  - A changed check token refuses package 20 and is not kept.
  - The appended-survivor reasons stand.
- `tools/research/check_update_redownload.py`: per captured layer, two more plans of the same session through a real engine copy. Both must equal the control plan and staged hashes. When a mixed decision was made, the second plan must reuse it with zero restores.
- `docs/features/asset-restore.md`: new section "Mixed-package decision reuse".

**Checks run**

- `.venv\Scripts\python.exe -m py_compile android/app/src/main/python/android_bridge.py tools/research/check_asset_restore.py tools/research/check_update_redownload.py` (Python 3.12.10): exit 0.
- `git diff --check`: exit 0, with LF/CRLF notices only.
- No Kotlin touched, so no Gradle compile. No staging-contract change (`build_patch` is untouched).

**Concerns**

- Proof cost: the proof hashes the whole engine tree (about 60 MB) and the kept records (the delta is up to about 69 MB). It does this twice per recorded decision and once per reuse, which may cost more than the copy it saves on small packages. Pass 2 decides from measurements.
- `__pycache__` is excluded from the engine proof because it is Python's derived cache; `runtime/` bytecode outside it stays covered. If the device engine root contains any link, reuse is silently declined: safe, but no gain.
- Producer and app identity are not measured in Python. The decision lives only as long as the worker process, and an APK update ends that process. Kotlin is untouched; no seam was needed.
- The proof binds the session snapshot folder, not the run id. Two calls on the same snapshot folder in one process share a decision only while every input matches.
- `check_update_repatch.py` calls `_restore_pristine(session, keep)` without manifest or engine, so it exercises only the unchanged fresh path.
- `check_update_redownload.py` already calls `clear_build` without a build-owner record (ticket 09 behaviour). It may refuse before reaching the plans.
- The Out of Scope section of `docs/features/update-stuck-redownload.md` still lists this reuse as ticket 17. It was not edited because it is outside this ticket's ownership.

**Pass 2 gates**

- Read each script's `--help` first. Run:
  - `check_asset_restore.py --work <dir>` (fixture defaults: the 1.7.0.1 pristine layer and `D:\scratch\hok-1.7.0.1\out5-catalog`).
  - `check_update_redownload.py --work <dir on D:> --cycle <capture>`, if the 2026-10-23 captures exist.
  - `check_update_repatch.py` with its fixtures, `check_bridge_continuation.py` and `check_pristine_delta.py`.
- Record control against reuse: restores, copied bytes, proof bytes and seconds. Give a gain or no-change verdict, and drop or narrow the shortcut if the proof costs more than the copies it saves.
- Confirm control and reuse give identical restored/refused sets, refusal text, plan files and staged hashes. Confirm every invalidation case.

Pass 2 (2026-11-12, real-dump worker; no code change). `check_asset_restore.py --pristine <fixture 1.8.0.1 builtin> --staged <current EN build of that fixture, parity PASS vs baseline> --work D:/scratch/hok-ac-pass2/parity/t17/work2 --apk <fixture normal.apk>`, run from the external current snapshot: **all checks passed, rc 0, 830 s** (log `D:/scratch/hok-ac-pass2/parity/t17b.log`). Code identity: `check_asset_restore.py` `a0a92b5a…`, `android_bridge.py` `9c667e31…` (copied from the checkout mid-session). The live `android_bridge.py` has changed since (`ebc0b18e…`: `sys.dont_write_bytecode`, `_staged_payload_manifest`); this result does not cover that revision. A first attempt failed only because the snapshot lacked `android/app/src/main/python` (harness gap, not product).

| Step | Restores | Copied | Proof hashed | Seconds |
|---|---|---|---|---|
| Control plan / refusal (no reuse) | 3 | 944,013,312 B | 69,692,480 B / 0 B | 21.4 / ~19 |
| Build records its decision | 3 | 944,013,312 B | 158,459,770 B | 20.0 |
| Plan reusing it; second plan; second build | 0 | 0 B | 79,229,885 B each | 2.1, 1.9, 1.2 |
| Restart, other session, changed snapshot/delta/engine/refusal-record (and undone), failed restore, changed token | decide afresh (2 or 3 restores) | 603–944 MB | ~158 MB | 16–41 |

Restored/refused sets, refusal text (`package 10, 21`), Re-download plan (`10/*`, `21/*`) and "no trial copy left" matched control in every case; a corrupt kept body reuses nothing; the whole build over restored packages passes the text signal (120 s). Verdict (recommendation): keep. Each reuse saves ~944 MB copied and ~18 s for ~79 MB hashed; recording costs ~89 MB of extra hashing once. Not run: `check_update_redownload.py` (no real-update captures, per user), `check_update_repatch.py`.
