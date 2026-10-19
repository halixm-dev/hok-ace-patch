# 15: Windows single column with progress in ②

**What to build:** The Windows patcher becomes one centred column, at most 720 px wide: hero, ① Language, ② Start, the log. See the [spec](../spec.md) and the [home screen brief](../home-screen-brief.md).

- The seven-row step sidebar goes.
- ② opens with the short "Before you start" checklist, then device status and the working folder (free space, Change…), then Start.
- Once a run starts, Start becomes a bar with "Step N of 7 · <step>". The result becomes **Run again** or **Try again**.
- The log sits below in a fixed-height panel, and the page scrolls when the window is short.

**Blocked by:** 14, 06

**Status:** ready-for-agent

- [ ] Sidebar gone; single column
- [ ] Device, folder and Start inside ②
- [ ] Bar and step line during a run
- [ ] Checked at 100 % and 150 % scaling in both languages
