# Capture the Python baseline

Status: resolved

1. Trace the PC path through [pc_catalog](../../../tools/pc_catalog.py), [mobile_graphics._reencode](../../../tools/mobile_graphics.py) and [bc7_mode6.encode_block](../../../tools/bc7_mode6.py). Identify blocks that actually reach mode 7, including candidates that lose to an earlier mode. `ENCODERS` holds function references at import time, so instrument the actual call path.
2. On a pristine PC game copy, capture deterministic mode 7 inputs from the title and label atlases for English and Indonesian. Store the replay corpus in the work folder. Add small synthetic cases for blank, solid, transparent colored pixels, alpha edges and tied partition scores. Save expected Python candidate bytes, decoded RGBA and final chosen bytes.
3. Record Python/dependency versions, CPU, game version, language, atlas identifiers and block counts. Time the mode 7 corpus and the whole `pc_catalog.build` separately. Use a fresh catalog work directory for every cold build, repeat each language three times and report medians. Time warm reuse separately. Exclude capture and profiling overhead from timings.

Deliver the fixture generator or replay command, expected digests and baseline measurements. If a game copy is unavailable, carry on with synthetic parity and mark the real-atlas timings pending.
