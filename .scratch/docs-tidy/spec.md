# Docs tidy: one home for each kind of doc

Status: ready-for-agent

## Problem Statement

The repo's documentation grew one feature at a time, and each kind of material now lives in several places at once. The always-loaded agent instructions (about 42 KB) mix the rules an agent needs on every turn with the device verdicts, hashes and byte counts behind them, so every turn pays for evidence that only matters to one pass. The same measurement is often written three times: in a feature record's journey log, in the project memory file and inside a rule, so correcting a number means finding all three. The project memory file's name collides with Claude's own memory system. Shipped-feature records sit under a folder name left over from an earlier workflow, while the newly configured issue tracker introduces a second home for specs with no rule for how one becomes the other. A `tasks/` folder holds handoffs, progress notes, art sources and a validation script that a shipping rule depends on. Two finished one-off docs sit beside the living ones. The README repeats the coverage ledger. The project has a rich domain vocabulary (prime layer, override layer, append, device cycle, allowlist) but no glossary, and the word "glossary" already means the game-keyword table. Load-bearing decisions that were measured and must not be re-litigated are buried in journey logs rather than recorded as decisions.

## Solution

Every kind of doc gets exactly one home, and the always-loaded instructions carry rules plus pointers rather than evidence:

| Kind | Home | Read it when |
|---|---|---|
| Rules that apply every turn | `AGENTS.md`, about 12 KB or less | always loaded |
| Project vocabulary | `GLOSSARY.md` (already seeded) | naming anything |
| Load-bearing decisions | `docs/adr/` | before changing that area |
| Shipped-feature records | `docs/features/` | before changing that pass |
| Procedures | `docs/runbooks/` | before running that procedure |
| Raw evidence | `docs/lab-notebook.md`, the single source for numbers and verdicts | when a number or verdict is in question |
| Coverage counts | the coverage ledger (README keeps a short summary) | when coverage moves |
| Staging summary contract | the staging entry point's own docstring | editing the pipeline |
| Work in flight | `.scratch/<feature>/`, committed | working a ticket |
| Skill configuration | `docs/agents/` | read by the skills |

`tasks/`, `docs/compose/`, the finished Indonesian review doc and the artifact-retention doc are retired into the homes above. A shipped `.scratch` spec becomes a feature record by a fixed promotion step, and its `.scratch` folder is deleted.

## User Stories

1. As an agent starting any turn, I want the always-loaded instructions to hold only rules and pointers, so that my context isn't spent on evidence for passes I'm not touching.
2. As an agent about to change a pass, I want the instructions to point me to that pass's feature record by its trigger, so that I read the reasoning and the failed attempts before editing.
3. As an agent about to change a load-bearing behaviour (the install path, the rebuild list, the allowlist gate, atlas placement, uncatalogued config bins, update timing), I want a short ADR naming the decision and why, so that I don't re-propose an approach a device cycle already ruled out.
4. As an architecture review, I want those decisions recorded as ADRs, so that I don't list refactors they forbid.
5. As the maintainer, I want each raw measurement to live in one place, the lab notebook, so that correcting a number is a one-place edit.
6. As the maintainer, I want journey-log entries reduced to one line (what was tried, the verdict, a pointer to the notebook entry by date), so that feature records read as design records again.
7. As the maintainer, I want the project memory file renamed to a lab notebook under `docs/`, so that it no longer reads as Claude's own memory.
8. As an agent questioning a number, I want the instructions to tell me the lab notebook is where numbers and verdicts live, so that I check it before re-running an experiment.
9. As the maintainer, I want shipped-feature records in `docs/features/`, so that the path says what they are.
10. As the maintainer, I want every link to a moved record updated, so that nothing points at `docs/compose/`.
11. As the maintainer, I want the stale task checklists dropped from the 12 existing records, so that a shipped record carries no unchecked boxes.
12. As an agent finishing a feature, I want the promotion step written into the issue-tracker config (Problem → [S1], Implementation Decisions → [S2], Out of Scope → [S3], a fresh Report with verification and journey log, no task list, then delete the `.scratch` folder), so that every record has the same shape.
13. As an agent starting a feature, I want in-flight specs, tickets and handoffs in `.scratch/<feature>/` and committed, so that work in flight survives a machine switch.
14. As an agent running a device cycle, I want a device-cycle runbook, so that I follow the test loop without digging it out of a feature record.
15. As an agent chasing a string that stays Chinese, I want a diagnose-untranslated runbook covering both data layers, so that I don't call an asset unreachable after checking only the override layer.
16. As an agent reading a crash, I want a read-a-crash runbook, so that the triage steps aren't buried in the evidence log.
17. As the maintainer, I want the notebook's operating-discipline section moved into the runbooks, so that procedures live with procedures.
18. As an agent editing the staging pipeline, I want the summary contract (payload fields, `mode` values, the skipped lists, pass order) in the staging entry point's docstring, so that it changes in the same edit as the code it describes.
19. As an agent on any turn, I want the instructions to keep a two-line pointer to that docstring, so that I know the contract exists.
20. As an agent naming a concept, I want `GLOSSARY.md` to define the project's terms with the synonyms to avoid, so that docs, tickets and code use one word per concept.
21. As an agent writing prose, I want the game-keyword table called the terminology table everywhere, so that "glossary" only ever means `GLOSSARY.md`.
22. As the maintainer, I want the terminology feature record renamed to match, so that its file name doesn't say "glossary".
23. As an agent writing prose, I want "override layer" used for the downloaded layer and "prime layer" for the APK's, so that prose matches the code's names and grep finds both.
24. As a user reading the README, I want a five-to-ten-line coverage summary with a link to the ledger, so that I get the gist without a second copy of the counts going stale.
25. As the maintainer, I want the finished Indonesian review folded into the Indonesian feature record, so that `docs/` holds only living docs.
26. As the maintainer, I want the artifact-retention notes merged into the notebook's housekeeping section, so that local-machine facts live in one place.
27. As the maintainer, I want `tasks/` retired: the Career-atlas art sources, evidence images, the reference-pack builder and the label validation script moved under the research tools, so that durable files stay findable and nothing ships them.
28. As an agent shipping a label change, I want the shipping rule to name the validation script at its new path, so that the check I'm told to run still exists.
29. As the maintainer, I want the T7, T11, T13 and T14 notes folded into their feature records' journey logs as one-line entries, so that their verdicts survive the folder's removal.
30. As the maintainer, I want T15's open item (the optional win/loss badges) moved into its own `.scratch` ticket, so that open work stays visible after `tasks/` is gone.
31. As the maintainer, I want T14's prototype sprite-table script compared against the shipped sprite-table module and dropped if superseded, so that two versions don't coexist.
32. As the maintainer, I want the instructions' Docs section to become one placement table (kind → home → when to read it), so that one always-loaded pointer reaches every doc.
33. As the maintainer, I want the README's layout section updated in the same change, so that it follows the repo's own rule for layout changes.
34. As the maintainer, I want a reference check proving every path a tracked doc, docstring or build script names still resolves, so that the move breaks no pointer.
35. As the maintainer, I want the exe build and the offline graphics check to pass unchanged, so that the tidy provably touched no shipping behaviour.

## Implementation Decisions

- **No shipping behaviour changes.** The work moves and rewrites docs, one docstring and the paths in research-tool comments. Nothing under the app, the pipeline, the resources or the Android build changes, apart from the staging entry point's docstring.
- **Instructions budget.** The always-loaded instructions target about 12 KB. Each constraint becomes a rule of one to three lines plus a pointer to its ADR, feature record or runbook. Hashes, dates, byte counts and device verdicts leave the instructions. A number stays inline only when the rule can't be stated without it (the Python version, for example).
- **Placement table.** The instructions' Docs section is replaced by the table in Solution. Each row's "read it when" wording is the trigger, written to `/writing-for-agents` pointer discipline: lead with the key word, one trigger per branch.
- **ADRs.** Six start the folder, numbered in this order, each a short paragraph that points to its feature record's journey log:
  1. The install path is re-sign, then the access APK, then write the override layer, then reinstall the normal APK. Code injection and prebaked APKs fail.
  2. The translation is written only after the in-game update.
  3. No package is rebuilt (the rebuild list stays empty, and package `21` in particular): prime-only content reaches the phone by append.
  4. The allowlist is the only gate for translating a config bin. The row-checksum heuristic was measured and dropped.
  5. A config bin the catalog doesn't cover is never rewritten.
  6. A regioned atlas is placed by the device's sprite table, never by the catalog's PC offsets.
- **Lab notebook.** The project memory file moves to `docs/lab-notebook.md` with its content intact: the topic sections first, then the dated entries. Two of its sections move out to runbooks (reading a crash, operating discipline), and the artifact-retention notes merge into its housekeeping section. From now on it is the single source for raw measurements, and other docs cite its entries by date.
- **Journey logs.** In each feature record, a journey-log entry that restates a measurement already in the notebook becomes one line: attempt, verdict, notebook date. Where a record holds evidence that is in no notebook entry, that evidence moves into the notebook first, as a dated entry, so nothing is lost.
- **Feature records.** `docs/compose/spec/` moves to `docs/features/` with the same file names, except that the terminology record is renamed to drop "glossary". The task checklist sections are removed. The record shape (Report, [S1], [S2], [S3]) is unchanged.
- **Promotion step.** It goes into the issue-tracker config: it maps the `/to-spec` template onto the record shape and deletes the `.scratch` folder once the record is written.
- **Runbooks.** Three: device cycle and diagnose untranslated (both taken from the prime-rebuild record), and read a crash (from the notebook). Each source keeps a one-line pointer to its runbook.
- **Staging contract.** The contract moves verbatim into the staging entry point's docstring, apart from terminology fixes. The instructions keep two lines naming where it is.
- **Vocabulary.** All moved prose follows `GLOSSARY.md`: override layer / prime layer, terminology table, device cycle, access APK / normal APK. Code identifiers are left as they are.
- **`tasks/` retirement.** The Career-atlas material moves under the research tools as one folder (art sources, evidence, reference pack, validation script). Every reference in the instructions, the texture record and the atlas research tool is updated. T15's open badge work becomes a `.scratch` ticket. T14's script is diffed against the shipped sprite-table module and deleted if it's superseded, otherwise kept beside the moved material.
- **README.** The coverage section shrinks to a summary that links to the ledger. The layout section and every link to a moved doc are updated.
- **Commits.** Each step lands as a `docs:` commit (or `chore:` for pure moves), so each one can be reviewed and reverted on its own.

## Testing Decisions

- **One seam: references resolve.** A reference check scans every tracked Markdown file, the staging docstring, the research tools and the build scripts for repo paths (backticked or linked), confirms each one exists, and confirms nothing still names the old memory file, `docs/compose/` or `tasks/`. It's a research-tool script run by hand from the project root, like the existing offline checks. It tests what a reader experiences (does every pointer land?) rather than how the docs are worded.
- **No-regression guard.** The exe build succeeds, and the offline graphics check passes unchanged. Both prove no bundled resource or imported path moved.
- **Size check.** The instructions file is at or under about 12 KB, and each removed constraint's evidence can be found in its new home (spot-checked per ADR).
- **Prior art.** The offline graphics check and the payload `--check` modes are the repo's existing by-hand verification scripts, and the reference check follows their shape (exit code plus a printed list of failures).

## Out of Scope

- Splitting the notebook's topic sections into their feature records. That is a separate later spec (`notebook-split`).
- Any change to the coverage ledger's numbers, the catalog, the runtime, or shipping code beyond the one docstring.
- The Android app's own README and third-party notice, which stay where they are.
- The architecture review of the pipeline (`/improve-codebase-architecture`), which follows this tidy.
- Finishing the optional badge art. It only moves into a ticket here.

## Further Notes

- The glossary was seeded during the grilling that produced this spec (25 terms). Moved prose should be checked against it, and any new term added there rather than defined inline.
- The coverage-ledger rule ("updated in the same change as the work") and the feature-record rule ("consult the record before changing that pass") keep their meaning and are restated as placement-table triggers.
- The reference check doubles as the guard for the later notebook split.
