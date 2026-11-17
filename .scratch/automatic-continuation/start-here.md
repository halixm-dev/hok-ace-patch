# Implement one ticket per chat

## Current execution override

The user's 2026-11-11 coordinator request supersedes the per-chat/test timing
instructions below. One fresh implementation worker at a time implements 01–18;
dependencies advance when interfaces exist. Pass 1 authors tests but runs only
syntax/import/compile/build checks. Keep `Status: ready-for-agent`,
`Implementation: complete`, `Verification: pending`. Pass 2 runs validation and
fixes; resolve only after acceptance passes. Safety requirements remain unchanged.
Read [coordinator.md](coordinator.md) and ticket Comments for current progress,
preserved baseline and immutable external fixture locations. No commit, release,
feature promotion or scratch deletion while required gates remain open.

The user approved this design, not a release or a destructive phone cycle. These 19 ordered tickets form one combined release. Read [spec.md](spec.md) once, then give the smaller model this prompt with the next ticket path.

```text
Implement D:\Projects\hok-ace-android-en\.scratch\automatic-continuation\issues\01-probes-and-fixtures.md.

Read AGENTS.md, the ticket, and its named reference sections.
Check dependencies and git status before editing.
Implement this ticket only. Preserve unrelated changes.
Update the affected feature record in the same change as its pass/workflow.
Run its checks. Record exact results and remaining device/fixture gates
in the ticket's Comments. Mark resolved only when its acceptance criteria pass.
If an invariant cannot be met, explain the concrete blocker; do not weaken
identity, consent, rollback or read-back checks.
Do not run a destructive phone cycle without separate informed consent.
Do not publish, release or commit unless I ask.
```

Change the ticket path for each chat. Numeric order is simplest; all listed dependencies must be resolved. Missing fixtures are open gates, not passing results.

| Need | Read |
|---|---|
| Scope/decisions | [spec.md](spec.md) |
| State/API/trust rules | [architecture.md](architecture.md) |
| Commands/interruption cases | [validation.md](validation.md) |
| Inspected facts | [evidence.md](evidence.md) |
| Work now | Next numbered file in [issues/](issues/) |

Each handoff reports changed files, passed checks, open gates and next ticket. Keep full results in the ticket so the next chat can recover context.

When fixing a regression introduced as an expected-current-failure probe in ticket 01, convert it to an ordinary passing assertion. Keep every new safety regression observable.

| Change | Existing record to update with that ticket |
|---|---|
| Windows/Android repatch, Remove, delta or recovery ownership | `docs/features/language-switch.md` |
| APK/setup/standalone workflow | `docs/features/standalone-patcher-app.md`, and the Android patcher record if applicable |
| Android provider/service behavior | `docs/features/android-shell-providers.md` |
| Damaged-file deletion/download | `docs/features/update-stuck-redownload.md` |
| Mixed-package restoration/classification | `docs/features/asset-restore.md` |
| Speed or trust-check reuse | `docs/features/patch-speed.md` |
| Shared UX/copy | `PRODUCT.md`, `DESIGN.md` and the affected feature record |

Preserve unrelated uncommitted portions when touching an existing record. Implementation ticket Comments record the exact change/check; the feature record describes current behavior/evidence. Ticket 19 consolidates the new feature and final release verdict rather than postponing all documentation until then.

Planning added Automatic continuation and Stop safely to `GLOSSARY.md`, plus ADR 0010. They describe the accepted design, not shipped behavior. Update `PRODUCT.md`, `DESIGN.md` and feature records with implementation in tickets 13/19.
