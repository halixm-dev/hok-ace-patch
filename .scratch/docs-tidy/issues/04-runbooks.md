# 04: Runbooks

**What to build:** procedures an agent follows live in `docs/runbooks/`:

- **device cycle**: the device test loop a device-gated change follows, taken from the prime-rebuild record
- **diagnose untranslated**: tracing a string that stays Chinese across both data layers, taken from the same record
- **read a crash**: built from the notebook's crash-reading and operating-discipline sections

Each source keeps a one-line pointer to its runbook in place of the moved text. Prose follows `GLOSSARY.md` (prime layer / override layer, device cycle, access APK / normal APK).

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] Three runbooks exist, each written as ordered steps that end on a checkable completion criterion
- [ ] The prime-rebuild record and the notebook hold pointers, not copies
- [ ] No measurement is lost: evidence the procedures carried stays in the notebook
- [ ] The reference check passes
