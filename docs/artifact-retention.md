# Local artifact retention

Cleanup on 2026-10-03 removed **18.1 GiB** of obsolete outputs. `artifacts/` remains gitignored;
game dumps, APKs and generated patch packages are local inputs and evidence, not release source.

Retained:

| Material | Location | Purpose |
|---|---|---|
| Fresh 1.4.0.2 snapshot and its verified hashes | `dist/HOK ACE Patcher Data/pristine/20261003-173730/` | Known working Chinese control; future checksum research |
| Current normal/access APKs and updated patcher executable | `dist/` and `dist/HOK ACE Patcher Data/` | Supported installation and restore path |
| Full fixed patch, repair/rerun checks and native chunk-key donor | `dist/HOK ACE Patcher Data/grid-regression/` | Reproduce and verify the Talent Card fix |
| Screenshots, device push hashes, logs and small measurement reports | `artifacts/shots/`, `artifacts/device-cycle-t10/`, other cycle evidence directories | Preserve successful and failed device verdicts |
| Device push/capture tools and research probes | `artifacts/device-cycle-t9/`, `artifacts/device-cycle-t10/`, `artifacts/device-run/` | Reusable diagnostics; no imports from shipping code |
| Older source dumps and original APK | `artifacts/game-dump*`, `artifacts/tencent-pristine-1.1.1.apk` | Historical comparisons; never treat a patched dump as pristine |
| Small package-1 comparison specimens and key-probe inputs | `artifacts/cycles/base2/out/1`, `artifacts/cycles/3914DBBFECD1E54D/`, `artifacts/device-run/empty-rebuild/out/1`, `artifacts/device-cycle-t9/shipped-stage/` | Preserve the inputs needed by retained measurements |

Removed repeated prime extractions, replacement scans, superseded full rebuilds, obsolete 1.4.0.1
candidate patch outputs, duplicate selftest outputs, failed build logs, an unused PC installer, the
old full-cycle diagnostic backup archive, and scratch commit/diff text. Small reports and screenshots
were retained. The verified deletion inventory is `artifacts/cleanup-plan.json`.

Older spec commands remain historical verification records. Their removed outputs must be rebuilt
before reuse. In particular, an extra-text candidate needs a fresh build staged from the phone's own
game-data version; the old candidate packages are neither retained as complete patches nor ready to
push. This cleanup does not change candidate verdicts or the four-asset allowlist.

Before deleting more, retain a reproducible source, the current restore APK, and the evidence behind
device-gated decisions. Resolve every deletion target inside the intended artifact root and use native
PowerShell file operations. Never delete the generated runtime/catalog resources or signing key.
