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

- [ ] Both reference checks pass
- [ ] Every rule in the spec's *Implementation Decisions* that a future change could break is in `AGENTS.md` or an ADR

## Comments
