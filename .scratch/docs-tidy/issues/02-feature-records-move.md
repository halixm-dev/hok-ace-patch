# 02: Feature records move to docs/features/

**What to build:** the 12 shipped-feature records live in `docs/features/` under their current names. The exception is the terminology record, renamed so its file name no longer says "glossary". Each record drops its stale task-checklist section and otherwise keeps its shape (Report, [S1], [S2], [S3]). The issue-tracker config gains the promotion step: when a `.scratch` spec ships, map Problem → [S1], Implementation Decisions → [S2], Out of Scope → [S3], write a fresh Report (what landed, verification commands and results, journey log), add no task list, then delete the `.scratch` folder.

**Blocked by:** 01

**Status:** done

- [x] Every record is in `docs/features/`, and `docs/compose/` no longer exists
- [x] No record carries a task-checklist section
- [x] The promotion step is in the issue-tracker config
- [x] Every reference to a moved record is updated (instructions, README, notebook, other records, research tools)
- [x] The old folder name is on the retired-names list and the reference check passes

## Comments

- Implementation: the terminology record is now `docs/features/terminology-table.md`. Dropping the task lists kept their information: open (unchecked) items became a plain `### Still owed` list at the end of each Report, and `prime-only-append.md`'s dated evidence subsections, which had sat under `## Tasks`, moved to the end of its Report verbatim.
