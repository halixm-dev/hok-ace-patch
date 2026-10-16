# 07: ADRs 0001-0006

**What to build:** `docs/adr/` holds the six load-bearing decisions, numbered in this order. Each is one short paragraph (context, decision, why) in the domain-modeling ADR format and points to the feature-record journey log that holds the evidence:

1. The install path is re-sign, then the access APK, then write the override layer, then reinstall the normal APK. Code injection and prebaked APKs fail.
2. The translation is written only after the in-game update.
3. No package is rebuilt, package `21` in particular: prime-only content reaches the phone by append.
4. The allowlist is the only gate for translating a config bin. The row-checksum heuristic was measured and dropped.
5. A config bin the catalog doesn't cover is never rewritten.
6. A regioned atlas is placed by the device's sprite table, never by the catalog's PC offsets.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Six ADRs exist, each one paragraph, each using `GLOSSARY.md` terms
- [ ] Each cites its record (and notebook entry by date where the verdict lives there)
- [ ] The reference check passes
