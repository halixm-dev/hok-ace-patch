---
feature: language-switch
status: built; device-tested in both patchers (switch, Remove) and the Android patcher (game update)
updated: 2026-11-13
branch: master
commits: f428002..3bcae14
---

# Repatch without clearing the game's data

## Report

### Device cycles on the Android patcher (2026-11-12 to 2026-11-13, Wireless debugging, `f15a72e`)

Real interruption cycles of automatic continuation; details in the [lab notebook](../lab-notebook.md)'s entries of
those dates.

| Case | Verdict |
|---|---|
| Switches | ID (`a123804e`), ID again with no file written (`48fcabc6`), EN after ID (`923ad9ad`), each complete 398/318 with 1 table skipped. **Pass** |
| Stop mid-apply (`468d719c`, `f7a510aa`) | Each rolled back to the previous layer. For `468d719c` the delta and staged-hash record stayed unchanged and the next Start (`923ad9ad`) took the rolled-back layer as its own. **Pass** |
| Worker loss mid-apply (`28932a16`), force-stop in the final install (`6a664446`) | Recovered, reused the verified build, complete; the delta stayed per-language deterministic (EN body `6318dd32…` both times). **Pass** |
| Remove (`93d5aad3`, then `665f5998` on 1.10.1.2 data) | Removed 11 files each, delta cleared, only `staged-hashes.json` kept. **Pass** |
| Remove byte proof | The EN delta built from the files exactly as `93d5aad3` left them equals the EN deltas built from the delta-rebuilt pristine layer (body `6318dd32…`, asset bodies `257e90a5…`): Remove restored the pristine bytes exactly. **Pass** |

Limits: one phone, Wireless debugging only. The Windows patcher's cycles were skipped by the user on
2026-11-17; Shizuku and Root had none. No coverage count moved.

### Completion receipt and final pristine knowledge (2026-11-12, pass 1, unverified)

| Rule | Current source behavior |
|---|---|
| Publication | Complete payload read-back, exact normal/root APK audit and durable delta finalization precede the completion receipt. Full result/counts/skips and original build identity are retained. A saved receipt never attests the current phone by itself. |
| Android finalization | STAGED seals explicit old delta/record/classification identities and intended final staged-hash bytes. Promotion pins old bytes and a hashed intent, accepts only old → record-promoted → final pairs, then reads back active delta or required absence AND staged-hash record. A finalized flag still requires those actual bytes, backups and intent; its audit is read-only. New unrelated active knowledge is refused. |
| Stop/unconfirmed | Required metadata promotion must succeed before consistent closure, including Stop or unconfirmed recovery. Failure leaves the run actionable and material pinned. Success versus Stop uses a short durable terminal section after expensive hashing; cancelled/stopped/unconfirmed results cannot authorize reuse. |
| Fresh Start | Matching success output may be copied into new owned staging after independent current APK/full-layer/producer/options/source-prime/delta audits. New authorization owns every later write/install. Remove, changed game/engine/options/metadata, damaged-file deletion and optional cache release prevent stale reuse. Windows declines prior deletion declarations; repeat Remove does ordinary processing. |
| Evidence | Authored artifact/Windows recovery and private Android metadata/full-coordinator controls; compile-only checks. No behavior, output parity, timing or phone verdict is claimed. |

### Android durable Start seam (2026-11-12, unverified)

| Rule | Current source behavior |
|---|---|
| Translate / Remove | A durable `RunStore` record fixes the action, language, exact provider and target before preparation; prepared source/normal/access identities and receipt digest are checked again at claim. Saved status is never permission. |
| Interrupted dispatch | Claim does not consume away unfinished work. One stable UUID links Start to the child session, including a restart before journal publication; existing children cannot create another fresh run. |
| Destructive work | Ordinary translation Start cannot become Re-download approval. Damaged-file fallback now pauses for separate scoped consent, which ticket 12 supplies. Official-signature conversion retains separate First setup consent. |
| Retention / verification | Free up space refuses while an authorization is unresolved. Automatic reuse/routing and resolved-cache retention remain tickets 09–11. New metadata/probe source has only compile checks; all behavior/device gates remain open. |


A translated phone can now be patched again without clearing the game's data, in all three cases that
used to need a clear: a language switch, a newer translation of the same data, and an in-game update.
After each verified install, each patcher keeps a **pristine delta** (`tools/pristine_delta.py`): the
pristine bytes of every range it overwrote, about 5 MB. A later run rebuilds the pristine layer from it
in its own copy and builds the new language from that, so the phone gets one write per staged file, as
on a first install. Both patchers also gained **Remove translation**, which writes the pristine bytes
back with no new patch.

After an in-game update, the Android patcher recovers without a clear: a package the update left stuck
or mixed is deleted in the Start run and downloaded again by the game (**Re-download damaged files**,
[update-stuck-redownload](update-stuck-redownload.md)), one it left partly translated is written back
from the delta's kept asset bodies ([asset-restore](asset-restore.md)), and the next Start patches.

| what landed | where |
|---|---|
| the delta: `make`, `write`/`read`, `rebuild`, the staged-hash record, `text_not_pristine`, `accept_replaced` | `tools/pristine_delta.py` |
| the pristine layer verdict (first install, stale delta, mixed, refusals, rebuilt), in one order for both patchers | `pristine_delta.layer_verdict` |
| Windows repatch from the delta, the pending delta, Remove | `pristine_layer.PristineLayer`, mixed into `patcher_core.Patcher` (`restore_pristine`, `check_first_delta`, `write_back_pristine`), and `Patcher.push_translation` |
| Windows first delta from a kept session | `PristineLayer.bootstrap_delta` |
| Android repatch, delta promotion, Remove | `android_bridge` (`build_snapshot`, `keep_delta`, `build_removal`), `PristineDelta.kt`, `PatchCoordinator` |
| Android build-input copy budget | `build_storage.estimate(pristine_copy_bytes=)` |
| an updated package accepted as the new pristine, per package | `pristine_delta.accept_replaced` |
| Re-download of stuck and mixed packages in one run | `android_bridge.plan_redownload` |
| the Language card / LANGUAGE picker text, Remove buttons | both front ends |
| offline checks | `tools/research/check_pristine_delta.py`, `check_windows_repatch.py`, `check_update_repatch.py`, `check_update_redownload.py` |
| device cycle tooling | `tools/research/update_cycle.py`, `watchdog_history.py` |

### Android checkpoint continuation (2026-11-12, pass 1; verification pending)

| Rule | Current source behavior |
|---|---|
| Re-entry | `PatchCoordinator.dispatch` continues a claimed run's own session. A clean session restarts whole stages from PREPARED (`SessionJournal.resumeConsistent`); an unfinished file change rolls back from the verified originals first; a lost install reply is audited against the installed identity (`reconcileInstall`). |
| Reuse | A published snapshot is reused once its owner record, its rename intent and the live layer match it. A STAGED build is reused only when `inspect_build_checkpoint` proves the same measured input identity. An unfinished snapshot or build restarts in a new owned attempt; a layer the game changed retires the snapshot (kept) and takes one fresh snapshot. |
| Pristine delta | The build's delta effect is sealed at STAGED (`android_bridge.finalization_plan`, `PristineDelta.seal`). After the payload and normal APK are verified, `PristineDelta.finalize` promotes it byte-only and idempotently, with no engine: the plan's hashes join the kept record, and Remove deletes the delta. The prior kept files are pinned beside the attempt first. COMPLETE needs `finalized`. |
| Unconfirmed results | A `recovered_unconfirmed` closure keeps its pristine knowledge but never counts as success: a continuation moves it to `unconfirmed_history` and must write and verify a fresh payload. |
| Stop and retention | An interruption keeps the action continuable; an explicit Stop resolves it once it is consistent (`stopped_consistent`). Unresolved actions pin their session. Among resolved linked sessions only the newest stays as the reusable cache; release removes receipts before bytes. Legacy sessions keep their old promotion and release. |
| Open | Every behavior above has compile checks only. Probes in `CoordinatorRecoveryProbeTest`, `FullCoordinatorProbeTest`, `RemovalRollbackProbeTest`, `SessionPublicationProbeTest`, `RunStoreProbeTest` and `AutomaticRouteProbeTest` are written and not run. |

### Windows durable ownership (in progress)

The Windows explicit Start now saves a run intent before APK preparation. A registry beside
`settings.json` finds unfinished working folders after the folder picker changes. Recovery discovery
runs before fresh-run free-space and installed-game checks; pending setup can therefore be found
even when the game is absent. Unknown or competing records block fresh work.

`app/patch_session.py` owns strict JSON, atomic read-back publication, root/device ownership and
persistent retry/Stop state. ADB commands bind the saved serial and verify Android owner user 0.
Incremental pulls reuse only sessions with matching serial/user/package evidence. Legacy pending
deltas remain safety-only candidates; they do not authorize a new translation.

This is a Pass 1 foundation, not a verified continuation feature. Tickets 04–07 still own installed
APK recovery, mutation journals, dispatch and safe terminal outcomes. Until then an explicit run
retains its unresolved intent and pins recovery sessions; a later Start/settings change is blocked.
No FINALIZED outcome is guessed from the legacy workflow. Behavioral/process/ADB probes and keyed
string checks remain pending Pass 2; no device verification is claimed.

### Windows file transaction (Pass 1; verification pending)

The Windows data session now retains `recovery/packages/` and touched Watchdog bytes separately
from the pristine build input. Both full and changed-only pulls compare that complete retained
file manifest with the live override layer before publication. Reconstructing pristine input
does not change these pre-action recovery bytes, which may contain the previous translation.

`app/device_transaction.py` records the exact expected final file set, including unchanged files,
identical-output skips, restored files and explicit removal of delta-created files. Its transport
uses Android's fixed game-private `.hok-ace-patcher.lock`; uploads stay outside the live layer.
Each changed file has a durable intent, a destination-directory temporary file, temporary
length/hash and sync checks, rename, parent sync, live read-back and durable acknowledgment.
Watchdog changes follow package writes and have the same retained originals and per-file intents.

Recovery classifies live bytes against the saved before/after identities. Unexpected files or
bytes block mutation rather than replacing a possible game update. Rollback uses the actual
pre-action snapshot, and does not require the translation engine or valid staged outputs.
The whole apply has an initial attempt and one automatic retry across reopen; retry counters
are never reset by rollback. The existing bounded run journal also requires a preflight refusal
when it cannot retain every proposed write and rollback budget.

The transaction pins exact old/pending delta and staged-hash records before writes. Only a full
payload audit and independent installed normal APK audit permit delta promotion/removal. Removal
retires the old delta by durable rename, retaining it in the session. Delta and staged-hash
read-backs precede the transaction's final record. This is the file-protocol seam for tickets
06–07; it does not publish a product completion receipt or authorize general startup continuation.

Synthetic interruption probes were authored for transfer/temp/rename cuts, lost replies, repeated
rollback, Watchdog restoration, changed-only snapshots, external changes, Stop, retry persistence,
and torn delta finalization. Only Python 3.12 syntax/import checks have run for this work.
Behavioral, real-output, Windows filesystem/device and release gates remain open. The older
verification results below describe the earlier workflow and do not verify this transaction.

### Earlier verification

- `check_pristine_delta.py --game` on pristine 1.6.0.1: English 11 rebuilt + 3 unchanged of 14 files,
  delta 5.12 MB; Indonesian 11 + 3 of 14, 3.87 MB. EN → ID, ID → EN and EN → EN each stage bytes identical
  to a build from pristine. One byte changed, truncated and missing files are reported, never rebuilt.
- `check_windows_repatch.py`: bootstrap from a pristine kept session, refusal over a translated one,
  Remove then patch again, Remove with no record refused (11 OK).
- `PristineDeltaProbeTest` and `RemovalRollbackProbeTest` pass on the Xiaomi M2007J3SG (2 tests, 6.8 s).
- `check_update_repatch.py`: replaced-file acceptance and the mixed-file refusal on the real 1.6.0.1
  packages with faked updates, both patchers.
- Device, Xiaomi M2007J3SG (lab notebook):
  - 2026-10-17, "Language switch without a clear": Windows EN → ID → EN, no repair, login kept, each
    switch byte-identical to a build from pristine; catalog fixes landed mid-cycle, so a newer translation
    was covered too.
  - 2026-10-17/18, "Language switch without a clear (Android patcher)": Remove through Windows left a
    Chinese lobby with no repair; Android EN → ID → EN, no repair, login kept.
  - 2026-10-23, "An update over a patched layer, captured end to end": update 1.6.0.1 → 1.7.0.1 over an
    English install; two Re-downloads and one asset restore, then a patch, no clear.
  - 2026-10-23, "One Re-download takes a stuck package and the mixed ones together": update 1.6.0.1 →
    1.7.0.2; one Re-download (`1`, `10`, `21`), asset restore (`15`, `19`, `20`), patch, no clear, English
    in game, login kept. Shipped in Android patcher 1.7.2.1.

### Journey

- The delta's measurement came first (lab notebook, 2026-10-17, "Reverse delta from a staged layer back
  to the pristine one"): 5.12 MB against 898.3 MB for compressed full copies. The two languages overwrite
  different ranges of `1/1_0.db`, which is why a delta always points at pristine and never chains.
- The Windows patcher has no rollback, so its new delta is written as `delta.pending.bin` before the first
  push and promoted after the last; the next run accepts either delta's staged bytes per file.
- Remove first left an empty delta; the spec owner changed it the same day to delete it, so "no delta"
  means one thing everywhere and the next run is a first install under both pristine signals.
- The per-file "replaced file becomes its new pristine" rule became per package and stricter
  (2026-10-18): textures have no text signal, so the delta records each changed asset's uncompressed
  SHA-256 on both sides.
- **Withdrawn after the first real update (ticket 01, 2026-10-23):** the update-flow signals before the
  update ((i) a delta file changed, (ii) `History.db` merges after the install, (iii) asking the user), the
  pristine write-back before the update, and the two-access-cycle run. The game updates the moment it
  opens, with no prompt, and nothing on the phone changes before then (`NewVersionInfo.json` stays the
  same), so the patcher has no moment to write first. The update merges diffs into the translated
  packages rather than failing on them; the spec owner chose the after-update path instead. ADR 0002 still
  allows that one write, unused. Signal (ii) holds after the fact (`watchdog_history.py`).
- Re-download first took only the stuck packages, so the 1.7.0.1 update needed two runs; since `48f10fa`
  one run also takes the mixed packages asset restore cannot.

Still owed: the Windows patcher does not detect a stuck update (Re-download is Android-only); a phone the
Android patcher translated before the delta shipped still needs one clear, since `releaseSession` had
deleted its snapshot bulk.

### Windows checkpoint continuation (Pass 1; verification pending)

`Patcher.run` discovers and claims the saved action before fresh capacity or installed-game checks.
It restores the saved work folder, language, action and exact phone/user target. Settings cannot
retarget unfinished work. Legacy pending deltas remain safety-only attention cases.

| Boundary | Current implementation |
|---|---|
| Preparation | Pinned APK identities and `preparation-source.json` permit an incomplete pre-mutation attempt to restart in a new owned child. Unknown source, mutation intent or a changed signer refuses a guessed restart. Signed normal output before official-game setup does not imply conversion or consent. |
| Snapshot | `windows_checkpoints.Checkpoints` publishes a commit-last source receipt using `run_artifacts`. Reopen rehashes actual recovery bytes and compares the full live source, APK identities and readiness. Saved producer evidence validates the snapshot independently of current translation-engine changes. Incomplete pulls restart in a new UUID child. |
| Staging | A new owned build attempt wraps the unchanged `build_patch`. Only finished payload, restored-but-unstaged files, deletion plan, full expected layer, unchanged summary and session delta enter `committed/`. A separate `build-receipt.json` is published last. A summary alone never permits reuse. |
| Invalidation | Current complete producer and semantic inputs gate staged reuse. Engine changes keep an independently matching snapshot. After interrupted apply, rollback precedes reuse or fresh staging; a copied, separately owned snapshot can seed the new generation without another device transfer. Missing producer evidence permits verified fresh processing but disables receipt reuse. |
| File recovery | Overall `files_apply` remains initial attempt plus one retry. A new transaction generation starts beyond the previous rolled-back per-file cycle, preventing key collisions without resetting that overall budget. Corrupt staged work cannot replace recovery originals. |
| Final install only | No snapshot/build/payload rewrite is needed. A full live-layer audit runs while access is installed, then the finalization callback restores and independently verifies normal, then delta metadata is promoted/read back. Reopen after normal restoration may require a bounded access/audit/normal cycle; no post-normal `run-as` success is assumed. |
| Result | Transaction metadata pins summary/receipt hashes before writes. Recovery validates those saved hashes and the saved producer receipt without loading the current translation engine. Full payload, normal and finalized delta proof gate `completion-receipt.json` and FINALIZED. |
| Stop | Stop before finalization requires rollback. Stop during normal restoration is rechecked before first finalization intent. Once finalization has started it finishes forward safely; a stopped result is `stopped_consistent`/cancelled, never Verified complete/Open game or a no-op cache hit. UI wiring remains ticket 07. |
| Retry scopes | Persisted `access-plan.json` binds access and matching normal cleanup to stable operation/cycle keys. Work, finalization and mandatory Stop repair have separate bounded scopes. Reopen does not generate fresh failure budgets. Explicit safe recovery Retry may re-arm one scope while Stop stays irrevocable; UI policy remains ticket 07. |
| Retention | Unresolved intent references pin APKs, snapshot/originals, staging and metadata. Under the owner locks, only proven resolved optional groups are removable; keep the newest per exact device target, including stopped reusable work. Publish cache invalidation before removal. Unknown/legacy/corrupt records stay pinned. Actual free space and conservative copy/staging/normal/rollback reserves gate new work. |

`tools/research/check_windows_checkpoints.py` authors synthetic call/byte-count, preparation-gap,
identity mutation, rollback/reapply, final-install-only, Stop, Remove and retention probes. The
recovery entry point includes them. Only Python 3.12 syntax/import checks have run for this change;
no behavioral, parity, timing or device result is claimed. Same-input EN/ID/switch/Remove controls,
real filesystem/installer interruption cycles and frozen packaging remain release gates.


### Windows Stop, Close and progress (Pass 1; verification pending)

| Control | Implemented boundary |
|---|---|
| Stop safely | Queue an irreversible control request without disk IO on the UI thread. The control/worker thread persists Stop before acknowledgement or cancellation cleanup. Whole owner read-modify-write methods share one reentrant lock; retry updates cannot overwrite Stop. Saved Stop never grants automatic translation continuation. |
| Close | Preserve continuation, cancel pending UI waits without answering them, finish feasible rollback/normal restoration, then close after the non-daemon worker and control threads finish. No shared ADB-server shutdown. Disconnected or failed recovery remains durable for reopen. |
| Reopen/reconnect | Startup dispatch requires one existing durable authorized run and claims existing work/device locks. No saved authorization leaves the UI idle. While owning saved work, bounded-backoff polling waits for that exact phone; waiting does not consume mutation attempts. |
| Retry | Persist a reconciliation guard before dispatch, scoped by actual durable operation progress. Repeated identity-read failures cannot borrow a pending build's retry permission. Each logical send retains its existing initial-plus-one journal budget. Exhaustion allows audit and bounded safety repair while blocking new patch sends. Explicit Retry can re-arm known safe operations/guards, never uninstall or Stop. |
| Progress/result | Queue core state, operation detail, measured transferred bytes and measured APK-entry counts. Unknown totals remain indeterminate; installer instructions explain phone approval. The GUI accepts added/removed results only from the core's verified_complete outcome; cancelled/unresolved restoration never shows a success result. |

The source uses cooperative command/build-log/APK-entry boundaries. Each owned ADB
child has a 180-second timeout; the UI stays responsive while an indivisible operation
finishes. Safety cleanup bypasses user cancellation while retaining journal budgets.
After metadata finalization, the core flushes queued UI controls before choosing the
terminal receipt, so a delayed Stop saver cannot turn completed safety finalization
into translation success. A failed Stop save also remains queued across explicit
Retry in the same open GUI; replacement workers retry its persistence/recovery
before patch dispatch. A stopped finalized transaction finishes forward and
publishes stopped_consistent/cancelled; it is never rolled back at that point.
Actual USB loss, slow phone installs, frozen packaging, both languages/scaling and
interactive dialogs remain Pass 2/device gates. Import-only checking emitted a
CustomTkinter font fallback warning; no window, screenshot or visual verdict exists.
`tools/research/check_windows_controls.py` authors isolated race, UI-wait, retry,
startup, result-gating and synthetic build/install/file-write interruption probes;
`check_windows_recovery.py` includes them. None has been executed in Pass 1.

## [S1] Problem

A phone that is already translated could not be patched again without clearing the game's data, at the
cost of a ~2.7 GB re-download and a login. Three cases hit this, the first most often:

1. **After an in-game update.** The update brings back Chinese text, or the repatch fails or the game
   force-closes.
2. **A newer translation** of the data already on the phone.
3. **A language switch**, English to Indonesian or back.

The cause is the text pass: it translates only records that are still Chinese. Over an English install
the Indonesian catalog changed 0 of 387 tables while the textures still switched, leaving MULAI GAME over
English text. The patcher kept no copy of the pristine bytes it overwrote, so clearing was the only way
back to the Chinese source.

## [S2] Design

| Area | Decision |
|---|---|
| Module | One shared `tools/pristine_delta.py`; Windows calls it from `patcher_core`, Android through `android_bridge`. No Kotlin reimplementation |
| Format | One file per install: schema-versioned JSON header plus a zlib body. Per package file: path under `packages/`, pristine and staged length and SHA-256, overwritten ranges with their pristine bytes, and each changed asset's uncompressed SHA-256 on both sides. A created file records pristine length 0 |
| Ranges | 4 KiB blocks, then 64-byte sub-blocks, runs closer than 256 bytes coalesced; both files read whole from disk, never from staging state |
| Points at pristine | A run from a rebuilt layer makes its new delta against the rebuilt pristine files. One delta per patcher, no chain; the two patchers never share one |
| Valid per file | An entry holds while its file is at the staged SHA-256; the data version is only logged, because an update can change content under an unchanged `1.info` |
| Self-verifying | `rebuild` takes a file only at its staged length and SHA-256 and checks each result against the pristine SHA-256 |
| When made | Only after a verified install (Windows after `push_translation`, Android once the run is `COMPLETE`), written atomically. An interrupted install keeps the old delta |
| First delta | Only from a pristine layer: no pulled file at a staged hash this patcher ever recorded, and the text pass planned every catalog table it read (`text_not_pristine`). A stale delta with no file at a recorded staged hash (data cleared) builds as a first install |
| Windows bootstrap | With no delta, try once to make one from a kept session whose backup passes the pristine signals and whose staged files equal the phone's |
| Where kept | Windows `<working folder>/pristine/delta.bin`; Android `filesDir/pristine/delta.bin`, outside `sessions/` |
| Android build input | `snapshot/` keeps the phone's bytes for rollback; the rebuilt files go into a separate copy of only the files the delta names (~0.9 GB), which `build_storage.estimate` reserves |
| Refusals | After the pull and before any game file is written, with the clear-data message (or "patch with the patcher that patched it last"). Which one is `pristine_delta.layer_verdict`'s, shared; each patcher keeps its own message |
| Dropped files | A file the last install translated and the new build no longer stages goes back at its rebuilt pristine bytes |
| Remove translation | Writes the rebuilt pristine files through the install path (Android through `GameFileTransaction`), then deletes the delta. The re-signed normal APK stays; the screen says to keep using Scan to login |
| After an update | A package the update replaced becomes its new pristine when none of its files and none of the recorded assets is at staged bytes, and the text signal holds (`accept_replaced`); asset restore takes a partly translated one; the rest refuse with `UPDATE_MIXED`, and a stuck one with `UPDATE_STUCK`, both offering Re-download on Android |

## [S3] Out of Scope

- Layers the Android patcher translated before the delta shipped: their snapshot bulk is gone, so the
  first repatch still needs a clear.
- Detecting or preparing for an update before it runs, and the pristine write-back before it (withdrawn:
  no signal precedes an update).
- A stuck update in the Windows patcher.

### Automatic-continuation bridge checkpoints (2026-11-12, pass 1)

The new explicit Android bridge checkpoint APIs keep `snapshot/` as the actual phone bytes,
including Watchdog, and reconstruct the pristine layer only inside an owned build attempt.
`build_checkpoint` runs the existing translation or Remove path and verifies the complete final
output, including restored files, before publishing a separate `build-receipt.json` last. The
pipeline summary and delta binary formats are unchanged. Remove retains its empty session delta
for finalization while its receipt explicitly names `delta: null`; the empty binary is still hashed
as an artifact. Building never promotes or removes the kept delta. Only the existing verified
finalization caller invokes `keep_delta`, passing the returned result directory for a new checkpoint.

Final payload checks distinguish numeric package files from the runtime stager's verification
reports. Only `package<id>_stage_manifest.json` (`unity19_stage_manifest.json` for package 19)
with a verified, validated report for a present package, and empty
`package<id>_metadata_<8-character tempfile suffix>/` directories for a present package, are
accepted beside the pipeline summary. Reports remain byte-for-byte in `out/` and in the complete
result receipt; they never enter staged hashes or the pristine delta. Their hashes describe the
text-stage pass before later passes, so final package bytes still use independent staged-hash and
delta read-back. Unknown entries, nonempty/orphaned metadata directories, missing/extra/changed
package files and malformed reports refuse publication or reuse.

A missing complete producer identity permits ordinary fresh processing and all final read-back
checks, but produces no reusable receipt. Restart reuse rehashes exact output/source/APK/delta
identities and returns the saved summary without staging. A reset targets only an owned incomplete
attempt and refuses any receipt-bearing attempt, even one whose receipt is damaged. Kotlin journal,
transaction-path and finalization integration followed in the same release. Verified later: output
parity, the changed-input controls and the Wireless debugging and Root phone cycles, recorded in
[automatic-continuation](automatic-continuation.md).

### Android rollback and identical outputs (2026-11-12, Pass 1; unverified)

Rollback first classifies the whole live layer against independently verified pre-action bytes and the journal's attempted/committed/in-flight staged paths. Only those package paths may be restored or deleted (a journalled creation); untouched originals remain audit-only. Missing original files, extra files or external bytes outside the permitted before/after/explicit-deletion states refuse recovery before writes. Watchdog clearing and each restore/delete recheck actual bytes under the provider's game lock. Refusal keeps original/Watchdog material and tries normal restoration only over the pinned known access APK; an unrelated installed update is never overwritten.

A recovery invocation may consume its own opaque originals descriptor once. Restart/standalone rollback independently rehashes retained originals. Identical staged outputs stay in the complete applied manifest and delta although their writes are skipped; Remove uses the same rule. Saved payload/normal flags no longer bypass a fresh complete live-layer audit on reopen. Finalization finishes forward after a queued Stop but publishes `stopped_consistent`, never success. Private controls are authored; behavioral, parity and device verification remain pending.

### Android cache under storage pressure (2026-11-12)

The coordinator retains the newest resolved run for reuse while space is sufficient. When a measured budget fails, it automatically invalidates optional resolved-cache receipts before removing their bulk, then remeasures the same budget once. Enough space continues the same operation; insufficient space remains a storage wait without consuming retry attempts. Current work, unfinished references, the completed-output source being adopted, saved recovery APKs and the active pristine delta stay pinned. Corrupt run records prevent cleanup. This cleanup changes only optional patcher session files; it does not clear game data or the app's general cache. Host budget regressions pass; private retention probes are compiled, with execution recorded separately.

The same measured-shortage reclaim (and a dispatched storage wait) also frees two things a pinned run cannot reach otherwise (2026-11-12, phone `f15a72e`, 3.1 GB stranded). First, the running action's own retired snapshots (`snapshot-attempts/<id>/retired`): only ids the journal lists in `retired_snapshots`, only while it shows no dirty packages, no mutation intent and no verified payload, only a real directory under no link that no live link points into, never the canonical `snapshot` or the current attempt. The receipt goes first, then the bytes; `retired_released` records the id and `retired_snapshots` keeps the history. A Re-download plan binds only the manifest digest and holds only against the canonical snapshot, so a plan bound to a retired manifest measures again and needs a new approval. Second, the `files/engine/<digest>` folders of earlier app builds (about 56 MB each, one per update): every digest a pending run's saved identity or preparation, an unresolved or pinned session, or a pending first setup names stays, as does any folder a live link points into; an unreadable record or tree deletes nothing. Deletion is serialized with `EngineAssets.prepare`. The budget is remeasured unchanged. Host selection tests pass (`ShortageReclaimTest`); the private probes are compiled, with execution recorded separately.

Three more parts of the same reclaim came from the 2026-11-19 Wireless cycle (phone `ebad528e`, 45 GB). First, byte-identical saved APKs are shared (`ApkPreparation.shareDuplicates`): a fresh preparation on a phone whose game already carries the stable key kept `recovery/<sha>/normal.apk` and `preparations/<id>/original.apk` as two 2 GB copies. Preparation now shares them as soon as it ends, by a hard link or, where the phone refuses one, a symlink. Second, the running action's finished build work: an attempt's `scratch/` once `result/build-receipt.json` exists (the build has moved its output, delta and hashes into `result/`; 1.6 GB of pristine copies and work files on that run). The rule for links is the same: a linked scratch, or one a live link points into, stays. Third, every APK install budgets what Android holds at once (`StorageBudget.installAllocations`): `pm` stages the whole APK, then refuses unless the installed size (the APK plus the compressed native libraries it extracts, 0.40 GB for the game) still fits above its 500 MiB low-storage reserve. Budgeted as one APK, the normal APK restore failed with 4.1 GB free; it now refuses before the install, and the reclaim gets one chance to free the room first. The access APK copy in `preparations/` stays: recovery reinstalls it to roll back packages.
