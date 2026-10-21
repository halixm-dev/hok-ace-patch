# 05: Device cycle and verdict

**What to build:** a device verdict for the translated lineup bin, following `docs/runbooks/device-cycle.md`: the control build first, then the `--cycle-asset` build from ticket 04, one variable apart.

- Screens: Lineup → Official recommendation, Newbie and Advanced, with names and 【Lineup ideas】 text in English. Open a lineup's detail. *Use* one, and it must still load onto the board in a match. Copy its code and import it into My lineups. Play a match to its end, with no QTS-failure popup (`QTSFailureTips`) and no such line in logcat.
- Compare each screen against the control. A screen that draws empty or loses a control is a withdrawal, as with the Diamond Frenzy cover bin.
- Cleared: the bin moves from `CANDIDATE_ASSETS` to `SAFE_ASSETS`; `docs/translation-progress.md` counts it; a feature record is written and this folder promoted (`docs/agents/issue-tracker.md`).
- Withdrawn: record the hash and the failing screen beside the other withdrawals in `tools/extra_text.py`, and the evidence in the lab notebook.
- Then the Indonesian build, the same screens.

**Blocked by:** 04

**Status:** ready-for-human

- [ ] Control and cycle builds on the phone, both languages
- [ ] Every screen above checked against the control
- [ ] Verdict recorded in the lab notebook
- [ ] Cleared: allowlist, coverage ledger and feature record updated; or withdrawn: hash and screen recorded
