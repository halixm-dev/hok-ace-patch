# 11: Rewrite the instructions file

**What to build:** the always-loaded instructions are about 12 KB or less and carry only what an agent needs on every turn:

- commands and the architecture table
- the staging-contract pointer
- each constraint as a rule of one to three lines with a pointer to its ADR, feature record or runbook
- the Docs section replaced by the placement table (kind → home → when to read it)

Hashes, dates, byte counts and device verdicts leave, because they already live in the notebook or the records; a number stays only when the rule can't be stated without it. Each pointer follows `/writing-for-agents`: lead with the trigger word, one trigger per branch. Prose follows `GLOSSARY.md`, and the Agent skills section stays.

**Blocked by:** 03, 04, 05, 07, 08

**Status:** done

- [x] The instructions file is at or under about 12 KB
- [x] Every constraint removed or shortened has its evidence in a named home (spot-checked per ADR)
- [x] The placement table covers every row in the spec's Solution table
- [x] The reference check passes
