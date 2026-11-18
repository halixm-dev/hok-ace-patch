# 18: Measure staging retries and bypass only proven failures

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 02, 09

## Scope and files

Own `tools/build_device_patch.py:failing_asset/full/fit-only staging loops`, relevant relocation integration, focused offline metrics/probes and patch-speed feature record. Read the full build_patch docstring and existing extra-chunk-to-relocation route before changing anything. Runtime bytecode is immutable.

## Steps

1. Instrument attempt counts, attributed failing asset, replacement-tree copies, available real package-copy bytes and duration on fixed EN/ID input. Copy cost inside compiled stage_unity_package must be measured/observed, not guessed from the Python loop.
2. Prove that failing_asset identifies the actual deterministic failure for exact package layout/source/translation/engine/options. Unknown or ambiguous attribution keeps the existing retry path.
3. Only if measurements show useful avoidable work, pre-route a proven failing table to the existing relocation path for the same complete inputs. Do not duplicate the already shipped extra-chunk exclusion.
4. Preserve scan/pass order, append/catalog/allowlist gates, text_not_pristine, read-back, counts and skip semantics. A pre-routed table must still be applied or honestly skipped, not silently dropped.
5. Scope any failure knowledge to the exact verified inputs and invalidate on changes. Add fault cases for different failing asset, changed chunk layout, unknown error and fit-only mode.
6. If evidence does not support a safe improvement, ship useful bounded metrics if appropriate and record the investigation's no-optimization verdict. This resolves the ticket without inventing savings.

## Acceptance

- [ ] Fixed control/change staged hashes, normalized summary, applied/skipped counts and delta mappings match.
- [ ] Fewer real expensive attempts/copies are measured for any retained shortcut.
- [ ] Unknown/misattributed/new-layout failures retain safe baseline behavior and coverage.
- [ ] Contract/docstring changes accompany any real pipeline change; no new config-bin or texture alias guessing.

## Checks and handoff

Run real-dump staging/parity checks for EN/ID with matching APK, pristine round trips, graphics check if affected, and staging-contract/references checks. Put new measured numbers/verdict in lab notebook. Missing real fixtures leaves optimization acceptance open; do not claim performance from a synthetic count alone.

## Stop condition

Without proven attribution and output parity, keep baseline retries. Never edit runtime bytecode or silently lose tables to reduce attempts.

## Comments

Pass 1 (implementation only; nothing below was run except the static checks listed).

| Files | Change |
|---|---|
| `tools/build_device_patch.py` | The in-place loop body moved, unchanged in behavior, into `_stage_package` (full → fit-only) and `_retry_loop` (one drop loop). `attribute_failure` returns `failing_asset`'s same hash plus its method; `failing_asset` wraps it. New keyword-only `build_patch(..., staging_metrics=None, retry_proofs=None)`: both default None, and neither the GUI, `patcher_core`, `android_bridge` nor `main` passes them, so shipped runs take the baseline path. `staging_metrics` records per package: safe/full/fit replacement-tree copies (files, bytes, seconds; fit includes `capacity_report`), every attempt (replacement files/bytes, seconds, outcome, error type/text, attributed hash, method, output package files/bytes after the call), relocation (offered/written/refused/seconds), `not_applied`, and run `totals`. `retry_proofs` (`{"producer_key", "proofs"}`) hashes each loop's exact-input key (producer, package id, loop, stager options, full SHA-256 + size of index and shards plus the scan fingerprint, every starting replacement) and records a baseline `proof` only when every failure was attributed and the loop staged. `confirm_retry_proofs` merges observations; a proof needs `RETRY_PROOF_CONFIRMATIONS` (2) identical observations. A confirmed proof pre-drops its tables in recorded order before the first attempt (they still reach `relocate_text` / `text_skipped` exactly as in the baseline); a missing table or an existing output copy skips it, and any failure of the pre-routed attempt copies the tables back, removes that output copy and runs the baseline loop from the full plan. Unattributed failures and the full → fit-only fallback are never skipped. Staging-contract docstring updated in the same edit. No CLI change, no summary field, no new config bin or texture alias. |
| `tools/research/measure_staging_retries.py` (new) | `faults`: 13 synthetic unittest cases on a fake package/stager (baseline parity with metrics+keys on, confirmed proof, one observation, conflicting observations, different failing asset → fallback, changed chunk layout, changed translation, unknown error keeps the fit-only fallback, unknown fit-only error raised, fit-only mode scoped both ways, existing output copy, absent table, malformed/pre-routed proofs). `measure`: one real `build_patch` with metrics, producer key (`run_artifacts.windows_producer_identity` + runtime tree), optional confirmed proofs, and an audit hook scoped to each real `stage_unity_package` call (copyfile calls/bytes, copytree/rmtree, writable/read opens, renames, removes, output copy size). Refuses existing paths and work/output/metrics inside the game or APK directory. `confirm`: merges two or more baseline runs under one producer key. |
| `docs/features/patch-speed.md` | "Staging retry measurement" section: boundary, metrics, shortcut rules, unverified status, no speed claim. |

| Check (Pass 1) | Result |
|---|---|
| `.venv\Scripts\python.exe -m py_compile tools\build_device_patch.py tools\research\measure_staging_retries.py` | Passed (syntax only). |
| `.venv\Scripts\python.exe tools\research\check_staging_contract.py` | Passed: "staging contract is in the docstring; AGENTS.md points to it", exit 0. |
| `git diff --check` | Passed, exit 0 (existing LF/CRLF notices only); the new untracked probe has no trailing whitespace. |
| Faults, measure, confirm, pipeline, `--selftest`, references check, parity | Not run (Pass 1 rule). |

Concerns for Pass 2:

- Baseline parity of the refactor is argued from code, not measured. Log lines and their order are unchanged; check staged hashes/summary anyway.
- The shortcut assumes `stage_unity_package` is a pure function of (source package, replacement set, options) that rewrites its whole output copy each call. The existing retries already rely on that, and the fallback removes the output copy before restarting; parity with proofs on is the evidence.
- Keys re-read the whole package (index + shards) and every replacement; `key_seconds` is recorded separately and may exceed the retries saved. Unknown whether the scan `fingerprints` are already SHA-256 (kept beside our own hash, not relied on).
- The audit hook sees only Python-level calls; native writes inside the runtime show only as output copy size. Writable opens are the cross-check if `shutil.copyfile` events are missed.
- The producer key hashes the repo's `app/tools/resources` and the interpreter: keep work/out/metrics outside the repo or two confirmation runs disagree.
- If measurements show few failed attempts or small failed-attempt cost, record the no-optimization verdict in `docs/lab-notebook.md`, keep the metrics and leave `retry_proofs` unwired (or remove it).

Pass 2 commands and gates (fresh directories under a new scratch root `<S>`, never inside the fixture or baseline folders; `<FX>` = `D:\scratch\hok-automatic-continuation-fixtures-1.8.0.1`, game/APK paths per its descriptor):

```bat
.venv\Scripts\python.exe tools\research\measure_staging_retries.py faults
.venv\Scripts\python.exe tools\research\check_staging_contract.py
.venv\Scripts\python.exe tools\research\check_references.py
:: two baseline EN observations, one ID, one metrics-only timing control
.venv\Scripts\python.exe tools\research\measure_staging_retries.py measure --runtime resources\runtime --game <FX>\<game> --catalog resources\catalog --apk <FX>\<apk> --work <S>\en1\work --output <S>\en1\out --metrics <S>\en1.json
.venv\Scripts\python.exe tools\research\measure_staging_retries.py measure --runtime resources\runtime --game <FX>\<game> --catalog resources\catalog --apk <FX>\<apk> --work <S>\en2\work --output <S>\en2\out --metrics <S>\en2.json
.venv\Scripts\python.exe tools\research\measure_staging_retries.py measure --runtime resources\runtime --game <FX>\<game> --catalog resources\catalog_id --apk <FX>\<apk> --work <S>\id1\work --output <S>\id1\out --metrics <S>\id1.json
.venv\Scripts\python.exe tools\research\measure_staging_retries.py measure --no-keys --runtime resources\runtime --game <FX>\<game> --catalog resources\catalog --apk <FX>\<apk> --work <S>\en0\work --output <S>\en0\out --metrics <S>\en0.json
.venv\Scripts\python.exe tools\research\measure_staging_retries.py confirm <S>\en1.json <S>\en2.json --out <S>\en-proofs.json
.venv\Scripts\python.exe tools\research\measure_staging_retries.py measure --proofs <S>\en-proofs.json --runtime resources\runtime --game <FX>\<game> --catalog resources\catalog --apk <FX>\<apk> --work <S>\en3\work --output <S>\en3\out --metrics <S>\en3.json
:: parity of each out against the preserved baseline build of the same inputs
.venv\Scripts\python.exe tools\research\compare_continuation_controls.py capture --staged <S>\en1\out --pristine <FX>\<game>\WXQ_Data\Package\builtin --apk <FX>\<apk> --report <S>\en1-capture.json
.venv\Scripts\python.exe tools\research\compare_continuation_controls.py compare <baseline-capture.json> <S>\en1-capture.json
```

Gates: all fault cases pass; en0/en1/en3 (EN) and id1 (ID) staged hashes, normalized summary, applied/skipped counts and delta mappings equal the baseline (`D:/scratch/hok-automatic-continuation-baseline-f369e14c/source`) for the same inputs; `totals.failed_attempts`, `failed_stage_seconds`, `failed_attempt_output_bytes`, `observed_totals.failed_calls` and `key_seconds` decide whether any proof saves real work; a kept shortcut needs en3 to show fewer real stage calls with identical output plus a repeated total-time control, and the same for ID. Record numbers and the verdict in `docs/lab-notebook.md`; acceptance boxes stay open until then.

Pass 2 (2026-11-12, fault-case fix only; no device, no real-dump runs in this note).

`faults` failed 1 of 13: `test_unknown_error_keeps_the_fit_only_fallback`, `AssertionError: None != 'staged'` on the fit-only loop's `preroute_outcome`. Root cause: the test's expectation, not production. Compared with the baseline (`D:/scratch/hok-automatic-continuation-baseline-f369e14c/source/tools/build_device_patch.py`, lines 422-462): `_stage_package`/`_retry_loop` catch only `RuntimeError` as the baseline does, an unattributed full failure returns to the fit-only fallback, and an unattributed fit-only failure re-raises; the test's own baseline-vs-routed `outcome()` assertion passed. The fake stager rewrites its output copy before failing (like the real one), so the failed full attempt leaves `<output>/<package>`, and the documented guard ("skipped when ... the output copy already exists") declines the fit-only proof. The guard stays: removing that leftover on a pre-route fallback would start the fit-only loop from a state the baseline never has.

| File | Change |
|---|---|
| `tools/research/measure_staging_retries.py` | The case now asserts the output copy exists after the full fallback, the fit-only proof is not used (`prerouted`/`preroute_outcome` None) and the fit-only loop stages in its 2 baseline attempts. |
| `tools/build_device_patch.py` | Docstring only: notes that a failed full loop leaves an output copy, so a fit-only proof is not used after that fallback. No code change. |
| `docs/features/patch-speed.md` | Same clause in the Shortcut row. |

| Check (Pass 2) | Result |
|---|---|
| `.venv\Scripts\python.exe tools\research\measure_staging_retries.py faults` | 13 of 13 OK. |
| `.venv\Scripts\python.exe tools\research\check_staging_contract.py` | Passed, exit 0. |

Consequence for the measurements: a fit-only proof can save work only in `fit_only_mode` runs or where the full loop staged; after a full → fit-only fallback it is always declined.

Pass 2 (2026-11-12, real-dump measurement worker; no device, no code change). Inputs: fixture 1.8.0.1 game (618 files) + `normal.apk` (SHA-256 `29b3ee7e…defdc`), verified against `inputs.json` before and after all runs (0 bad/missing/extra). Interpreter: checkout `.venv` Python 3.12.10 with `PYTHONDONTWRITEBYTECODE=1`, for baseline and current. Current code = external snapshot `D:/scratch/hok-ac-pass2/parity/current-src` (app/tools/resources copied from the checkout, HEAD f369e14 + working tree; `build_device_patch.py` sha256 `9ac014f1…`, `run_artifacts.py` `84056f4c…`, `mobile_snapshot.py` `89a26756…`, `measure_staging_retries.py` `d9b41056…`; all equal to the live checkout at the end of the runs). Baseline = `D:/scratch/hok-automatic-continuation-baseline-f369e14c/source` (`build_device_patch.py` `6c5c5232…`). Raw metrics/captures/logs: `D:/scratch/hok-ac-pass2/parity/t18/`.

| Check | Result |
|---|---|
| `measure_staging_retries.py faults` | 13/13 OK |
| `check_staging_contract.py`, `check_references.py` | Pass, exit 0 |
| Keyed `measure` (en1/en2/id1/en3) from the checkout or an exact copy | **Refused: "producer identity unavailable".** `run_artifacts.relative_path` rejects non-ASCII names, and 8 tracked files under `tools/research/career_atlas/originals/` have Chinese names (`zh_Image_*_胜利.png` etc.), so `windows_producer_identity` returns None for every Windows source run. Workaround for the measurement only: those 8 research PNGs were moved out of the external snapshot (nothing imports them). Producer key then `159f64039ea8…`, identical for en1/en2/id1/en3. |

| Run | Catalog / options | Wall s | build_patch s | Stage calls | Failed attempts | failed_stage_seconds | failed_attempt_output_bytes | key_seconds | Pre-routed | Parity vs baseline |
|---|---|---|---|---|---|---|---|---|---|---|
| en0 | EN `--no-keys` | 62 | 61.2 | 1 | 0 | 0 | 0 | 0 | 0 | PASS |
| en1 | EN keys | 96 | 56.1 | 1 | 0 | 0 | 0 | 1.07 | 0 | PASS |
| en2 | EN keys | 108 | 69.3 | 1 | 0 | 0 | 0 | 1.32 | 0 | PASS |
| id1 | ID keys | 131 | 65.9 | 1 | 0 | 0 | 0 | 1.24 | 0 | PASS (vs baseline ID) |
| confirm en1+en2 | | | | | | | | | | 0 confirmed proofs, 0 conflicts (no loop failed, so nothing is observed) |
| en3 | EN `--proofs` (empty) | 128 | 65.6 | 1 | 0 | 0 | 0 | 1.21 | 0 | PASS |
| en4, en5 | EN `--no-keys` repeats | 55, 71 | 53.8, 69.8 | 1 | 0 | 0 | 0 | 0 | 0 | PASS |

Every run: 1 package staged (`stage_seconds` 2.9–5.4), 178 replacement files / 18.3 MB copied once, 11 tables relocated (0.72 s), `observed_totals.failed_calls` 0. Parity = `compare_continuation_controls.py compare` of each capture against the baseline f369e14 build of the same inputs: staged file set + SHA-256, normalized summary, delta mappings/ranges/kept bodies all identical. Wall-time spread across identical no-key runs (54–70 s) is larger than `key_seconds`.

Verdict (recommendation; the coordinator decides): **drop the proof shortcut or leave it unwired.** On these real EN/ID inputs the full loop stages on its first attempt; there are no failed attempts, failed-stage seconds or failed-attempt output bytes to save, so no proof can form and `key_seconds` (~1.1–1.3 s) is pure cost. The metrics can stay. The refactor itself is parity-clean (en0–en5, id1). Not measured: `--fit-only` runs, other game versions where staging may fail.

Tool finding (not fixed): `compare_continuation_controls.py capture` refuses every real APK build, because summary `packages[*].source_package` for prime packages is `<work>/prime/<id>`, not under `WXQ_Data/Package/builtin/`. Captures here used an external wrapper (`D:/scratch/hok-ac-pass2/parity/capture_wrap.py`) that additionally normalizes exactly `.../prime/<id>` to `<work>/prime/<id>`; every other field stays gated. Sanity check: base-EN vs base-ID compare FAILS (delta, output, summary).

2026-11-18: the tool finding above is fixed in `compare_continuation_controls.py` itself (ticket 19 comment of that date); the external wrapper is no longer needed.
