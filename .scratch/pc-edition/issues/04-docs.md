# 04: Rules, records and the PC cycle runbook

**What to build:** the docs that make the PC edition a first-class part of the repo. See the [spec](../spec.md).

- **`AGENTS.md`:**
  - the opening line and the *Architecture* table name the PC edition and the three new modules;
  - *Flow* names the two cores;
  - *Constraints* gain:
    - receipts in the working folder, never the engine's default;
    - the per-edition allowlist;
    - ADR 0011 (keep every launcher-listed file at its listed size);
    - refuse while `wxq*.exe` or `王者万象棋.exe` runs;
    - empty `replacements\` before each job.
- **`README.md`:** the PC target, `--pc-job`, `--pc-selftest` and `check_pc_install.py`.
- **`docs/translation-progress.md`:** a PC column, with textures stated as *applied*.
- **`docs/features/language-switch.md`:** a PC section (receipts, restore-then-install); the pristine-delta wording stays mobile-only.
- **`docs/runbooks/pc-cycle.md`:** one change, one watched run in the PC edition, one verdict. It records the launcher's version and the game's data version.
- **`GLOSSARY.md`:** check the new terms still read right against the code as built.
- **Reference checks:** run `tools/research/check_references.py` and `tools/research/check_staging_contract.py`.

**Blocked by:** 03

**Status:** needs-triage

- [x] Both reference checks pass
- [x] Every rule in the spec's *Implementation Decisions* that a future change could break is in `AGENTS.md` or an ADR

## Comments

2026-11-20, Claude (branch `feat/pc-edition-04-docs`, on top of ticket 03's branch):

- **Checks:** `check_references.py` ("all references resolve"), `check_staging_contract.py` and
  `check_ui_strings.py` (456 strings) pass with Python 3.12.10.
- **`AGENTS.md`:** the opening line names both editions; *Architecture* names `pc_edition`,
  `engine_hooks`, `pc_catalog` and `bc7_mode6` (the code imports it from `mobile_graphics.port_atlas`
  and the smoketest); *Flow* names the two cores; *Commands* gains `--pc-selftest` and
  `check_pc_install.py`; the *Docs* table gains the PC cycle. A new *PC edition* group in
  *Constraints* holds receipts, the per-edition allowlist, ADR 0011, the process guard, emptying
  `replacements\`, the hooks, the per-install catalog and PC jobs. No existing rule was reworded.
- **The spec's decisions, checked one by one:** each one a future change could break is now in
  `AGENTS.md` or an ADR (ADR 0006 for the atlas refusal, ADR 0011 for the launcher list). The stage
  cache key and the hard-linked stage are speed, not correctness, so they stay in `pc_catalog`'s
  docstring.
- **Numbers:** the PC section of `translation-progress.md` comes from
  `C:\scratch\pc-edition-02\pc-selftest\out\pc_selftest.json` (the frozen exe, 2026-11-20) and the
  English install's log on the same copy. The data version 1.11.0.2 is the copy's `Version.txt`.
  Textures are stated as applied (359). The engine gives no per-table text count, and the ledger says so.
- **`GLOSSARY.md`:** *Allowlist* is now per edition. *Receipt* says the engine keeps receipts in this
  patcher's working folder. *PC edition*, *PC cycle* and *Windows patcher* already match the code.
- **`pc-cycle.md`:** records the launcher's version (the folder in `launcherConfig.json`'s
  `launcherExePath`, `26102.0.2.30004` on the copy) and the data version (`Version.txt`). Not yet run;
  ticket 05 runs it.

