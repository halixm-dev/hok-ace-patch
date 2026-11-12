# Recovery-only release 1.10.1.2

Status: done

Base: bb7e4ea, android-v1.10.1.1. User chose recovery only. Exclude unfinished automatic-continuation
work and preserve the original checkout without resetting or bulk staging.

- Scoped Re-download fallback for the logged missing texture slot.
- Mixed packages and missing texture slots in one explicit review.
- Review → direct deletion → game downloads → explicit Downloads finished → existing translation flow.
- Retain snapshot/hash checks, rollback, normal APK restoration and pristine-delta safeguards.

Measurements belong in docs/lab-notebook.md. The affected Redmi is unavailable; the original cause
and that phone's deletion/download/repatch cycle remain unverified.

Verification: 18 offline recovery regressions, 3 B-tree checks, 99 JVM tests, lint and bilingual
UI checks pass. Four emulator coordinator checks and recovery-card captures pass; see the lab notebook.
