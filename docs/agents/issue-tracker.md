# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a spec ships: promote it to a feature record

`.scratch/` holds work in flight; a shipped feature's record lives in `docs/features/<feature-slug>.md`. When the last ticket of a spec lands:

1. Create `docs/features/<feature-slug>.md` with the record shape: `## Report`, `## [S1] Problem`, `## [S2] Design`, `## [S3] Out of Scope`.
2. Map the spec's sections: Problem → `[S1]`, Implementation Decisions → `[S2]`, Out of Scope → `[S3]`.
3. Write a fresh `## Report`: what landed, the verification commands and their results, and the journey log (what was tried, the verdict, and what was withdrawn).
4. Add no task list. The tickets' checklists stay behind; anything still owed is a sentence in the Report.
5. Delete the `.scratch/<feature-slug>/` folder in the same change.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
