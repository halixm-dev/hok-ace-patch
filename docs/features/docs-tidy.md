---
feature: docs-tidy
status: delivered
updated: 2026-10-16
branch: docs-tidy
commits: 4195409..the docs-tidy tip
---

# Docs Tidy

## Report

Every kind of doc now has one home, and `AGENTS.md` carries rules and pointers instead of evidence:

- `AGENTS.md` went from 41,990 bytes to about 12 KB: each constraint is one to three lines with a pointer
  to its ADR, feature record or runbook, and the Docs section is a placement table (kind → home → when to
  read it), one runbook per row.
- The project memory file is `docs/lab-notebook.md`, the single source for numbers and verdicts; the
  artifact-retention notes merged into its housekeeping section.
- The feature records moved to `docs/features/`, with their task lists dropped (open items became a
  *Still owed* list) and the terminology record renamed `terminology-table.md`. The pipeline, app and
  language records' journey logs are one line per entry, citing the notebook by date.
- `docs/adr/` holds the six load-bearing decisions (install path, update timing, append not rebuild, the
  allowlist gate, uncatalogued config bins, atlas placement), each pointing at its evidence.
- `docs/runbooks/` holds the device cycle, diagnosing an untranslated string and reading a crash.
- The staging summary contract is the `build_patch` docstring in `tools/build_device_patch.py`;
  `AGENTS.md` keeps a two-line pointer.
- The old task folder is retired: the Career-atlas material is `tools/research/career_atlas/`, T14's
  prototype sprite-table script was deleted as superseded by `atlas_sprites.py table --out`, and the open
  badge work is `.scratch/career-atlas-badges/`. The finished Indonesian review folded into its record.
- The README's coverage section is a summary linking the ledger, and its layout table is current.
- Prose follows `GLOSSARY.md`: override layer / prime layer, terminology table, catalog edit, config bin.
- The issue-tracker config carries the promotion step this record was written by.

No shipping behaviour changed: apart from the `build_patch` docstring, nothing under `app/`, the
pipeline, `resources/` or `android/` was edited.

**Verification**

| command | result |
|---|---|
| `.venv\Scripts\python.exe tools\research\check_references.py` | `all references resolve`, run again after the spec folder was deleted |
| `.venv\Scripts\python.exe tools\research\check_staging_contract.py` | `staging contract is in the docstring; AGENTS.md points to it` |
| `.venv\Scripts\python.exe tools\research\check_graphics.py` | `all checks passed` |
| `build.bat` | the exe built (ticket 12) |
| `AGENTS.md` size | 12,285 bytes |

The reference check proves its own retired-name matcher before each scan (`RETIRED_CASES`): a retired
path matches only at the repo root, so a nested folder of the same name is not a failure.

**Journey log**

- One reference check as the only seam, run by hand like the other offline checks: it caught each pointer a move broke, and its retired-name list grew one entry per move. 2026-10-16.
- Moving the staging contract verbatim into the docstring: kept in place by `check_staging_contract.py`, which reads the docstring with `ast`; a new `mode` lands in the code, the docstring and the checker together. 2026-10-16.
- Dropping the records' task lists outright: would have lost the dated evidence `prime-only-append.md` kept under its task list, so that evidence moved to its Report and open items became *Still owed*. 2026-10-16.
- Compacting journey logs: each removed number was spot-checked in the notebook first; evidence the notebook lacked became dated entries there. 2026-10-16.
- Matching a retired path anywhere on a line: too broad, it also matched a nested folder of the same name; it now matches only at the repo root. Review, 2026-10-16.
- The ticket-12 vocabulary sweep: missed *texture payload*, *data set* and *config asset* in places; the review's sweep fixed the prose and left code identifiers and quoted output alone. Review, 2026-10-16.
- Splitting the notebook's topic sections into their records: deferred to its own spec (`notebook-split`).

## [S1] Problem

The repo's documentation grew one feature at a time, and each kind of material now lives in several places at once. The always-loaded agent instructions (about 42 KB) mix the rules an agent needs on every turn with the device verdicts, hashes and byte counts behind them, so every turn pays for evidence that only matters to one pass. The same measurement is often written three times: in a feature record's journey log, in the project memory file and inside a rule, so correcting a number means finding all three. The project memory file's name collides with Claude's own memory system. Shipped-feature records sit under a folder name left over from an earlier workflow, while the newly configured issue tracker introduces a second home for specs with no rule for how one becomes the other. A task folder at the repo root held handoffs, progress notes, art sources and a validation script that a shipping rule depends on. Two finished one-off docs sit beside the living ones. The README repeats the coverage ledger. The project has a rich domain vocabulary (prime layer, override layer, append, device cycle, allowlist) but no glossary, and the word "glossary" already means the game-keyword table. Load-bearing decisions that were measured and must not be re-litigated are buried in journey logs rather than recorded as decisions.

## [S2] Design

- **No shipping behaviour changes.** The work moves and rewrites docs, one docstring and the paths in research-tool comments. Nothing under the app, the pipeline, the resources or the Android build changes, apart from the staging entry point's docstring.
- **Instructions budget.** The always-loaded instructions target about 12 KB. Each constraint becomes a rule of one to three lines plus a pointer to its ADR, feature record or runbook. Hashes, dates, byte counts and device verdicts leave the instructions. A number stays inline only when the rule can't be stated without it (the Python version, for example).
- **Placement table.** The instructions' Docs section is replaced by one placement table: kind → home → when to read it, one row per kind of doc. Each row's "read it when" wording is the trigger, written to `/writing-for-agents` pointer discipline: lead with the key word, one trigger per branch.
- **ADRs.** Six start the folder, numbered in this order, each a short paragraph that points to its feature record's journey log:
  1. The install path is re-sign, then the access APK, then write the override layer, then reinstall the normal APK. Code injection and prebaked APKs fail.
  2. The translation is written only after the in-game update.
  3. No package is rebuilt (the rebuild list stays empty, and package `21` in particular): prime-only content reaches the phone by append.
  4. The allowlist is the only gate for translating a config bin. The row-checksum heuristic was measured and dropped.
  5. A config bin the catalog doesn't cover is never rewritten.
  6. A regioned atlas is placed by the device's sprite table, never by the catalog's PC offsets.
- **Lab notebook.** The project memory file moves to `docs/lab-notebook.md` with its content intact: the topic sections first, then the dated entries. Two of its sections move out to runbooks (reading a crash, operating discipline), and the artifact-retention notes merge into its housekeeping section. From now on it is the single source for raw measurements, and other docs cite its entries by date.
- **Journey logs.** In each feature record, a journey-log entry that restates a measurement already in the notebook becomes one line: attempt, verdict, notebook date. Where a record holds evidence that is in no notebook entry, that evidence moves into the notebook first, as a dated entry, so nothing is lost.
- **Feature records.** The old record folder moves to `docs/features/` with the same file names, except that the terminology record is renamed to drop "glossary". The task checklist sections are removed. The record shape (Report, [S1], [S2], [S3]) is unchanged.
- **Promotion step.** It goes into the issue-tracker config: it maps the `/to-spec` template onto the record shape and deletes the `.scratch` folder once the record is written.
- **Runbooks.** Three: device cycle and diagnose untranslated (both taken from the prime-rebuild record), and read a crash (from the notebook). Each source keeps a one-line pointer to its runbook.
- **Staging contract.** The contract moves verbatim into the staging entry point's docstring, apart from terminology fixes. The instructions keep two lines naming where it is.
- **Vocabulary.** All moved prose follows `GLOSSARY.md`: override layer / prime layer, terminology table, device cycle, access APK / normal APK. Code identifiers are left as they are.
- **Task-folder retirement.** The Career-atlas material moves under the research tools as one folder (art sources, evidence, reference pack, validation script). Every reference in the instructions, the texture record and the atlas research tool is updated. T15's open badge work becomes a `.scratch` ticket. T14's script is diffed against the shipped sprite-table module and deleted if it's superseded, otherwise kept beside the moved material.
- **README.** The coverage section shrinks to a summary that links to the ledger. The layout section and every link to a moved doc are updated.
- **Commits.** Each step lands as a `docs:` commit (or `chore:` for pure moves), so each one can be reviewed and reverted on its own.

## [S3] Out of Scope

- Splitting the notebook's topic sections into their feature records. That is a separate later spec (`notebook-split`).
- Any change to the coverage ledger's numbers, the catalog, the runtime, or shipping code beyond the one docstring.
- The Android app's own README and third-party notice, which stay where they are.
- The architecture review of the pipeline (`/improve-codebase-architecture`), which follows this tidy.
- Finishing the optional badge art. It only moves into a ticket here.
