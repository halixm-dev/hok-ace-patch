# 01: Shell provider picker and the provider seam

**What to build:** the groundwork both new providers stand on. A home-screen picker for the shell provider, remembered and changeable when no run is in progress; a seam in `WorkerDeviceConnection` so the worker can be started by something other than Shizuku; and the refusal of Shizuku running as uid 0. See the [spec](../spec.md), *Choosing a provider* and *Shared by all providers*.

- Picker with Shizuku, Wireless debugging (Beta) and Root (Beta); Shizuku is the default, and stays selected on a phone that already has a patch.
- Provider written in the diagnostic log header.
- One numbered guide per provider; the two new guides are placeholders until 02 and 03 fill them.
- Shizuku-specific strings become provider-specific; `GAME_MISSING` stays free of any provider name.
- `PrivilegedDeviceService` reads its uid at start: 2000 is today's path; 0 is refused until 03 lands; Shizuku at uid 0 gets *Shizuku is running with root. Choose the Root provider instead.*

**Blocked by:** none

**Status:** ready-for-agent

- [ ] Picker, persistence and log header, with unit tests
- [ ] Starter seam: Shizuku is one implementation, behaviour unchanged
- [ ] Rooted-Shizuku refusal
- [ ] `tools/research/check_ui_strings.py` passes
