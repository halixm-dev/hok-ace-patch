# 04: Share-code pass for a candidate bin

**What to build:** an offline build that can translate a lineup bin's share codes for one device cycle. The lineup bins join `extra_text.CANDIDATE_ASSETS` with their measurements. A run with `--cycle-asset` on one of them writes it with each code decoded, its text fields translated, then re-encoded, re-deflated and re-base64'd. A run without the flag leaves the bin untouched. Nothing goes onto `SAFE_ASSETS` here (ADR 0004).

- The generic protobuf rewrite does not see inside the codes, so the code transform is its own step. Every field other than the translated text stays byte-identical, at the protobuf and the bin level.
- If ticket 02 found a recomputable checksum, the pass recomputes it. If ticket 02 found none, record that it was checked.
- Idempotent: running the pass on its own output changes nothing. Every translated code decodes with the same steps the game's decoder uses, and the decoded fields read back as the targets.
- A bin present in only one layer reaches the override layer by append, like any other candidate.
- Update the staging contract (the `build_patch` docstring) in the same change, then run the contract and reference checks.

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] The lineup bins on `CANDIDATE_ASSETS` with their measured string counts
- [ ] `--cycle-asset` build writes the translated codes; a build without it leaves them pristine
- [ ] Translated codes decode and read back; a second run is a no-op
- [ ] Checksum handled per ticket 02's verdict
- [ ] Staging contract updated; `check_staging_contract.py` and `check_references.py` pass
- [ ] Control and cycle builds in a working folder outside the repo, ready for ticket 05
