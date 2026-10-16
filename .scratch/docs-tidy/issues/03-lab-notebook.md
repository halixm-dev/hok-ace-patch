# 03: Lab notebook

**What to build:** the project memory file becomes `docs/lab-notebook.md`, its content intact (topic sections first, dated entries after), so it no longer reads as Claude's own memory. The artifact-retention notes merge into its housekeeping section and their standalone doc is removed. A short header states that the notebook is the single source for raw measurements and device verdicts, and that other docs cite its entries by date.

**Blocked by:** 01

**Status:** done

- [x] The notebook exists under `docs/`, the root memory file is gone, and no content is lost (a diff shows only the move, the header and the merged retention notes)
- [x] The artifact-retention doc is gone and its content is in the housekeeping section
- [x] Every reference is updated (instructions, README, records, research tools)
- [x] Both old names are on the retired-names list and the reference check passes
