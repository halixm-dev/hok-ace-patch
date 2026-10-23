# 15: Windows single column with progress in ②

**What to build:** The Windows patcher becomes one centred column, at most 720 px wide: hero, ① Language, ② Start, the log. See the [spec](../spec.md) and the [home screen brief](../home-screen-brief.md).

- The seven-row step sidebar goes.
- ② opens with the short "Before you start" checklist, then device status and the working folder (free space, Change…), then Start.
- Once a run starts, Start becomes a bar with "Step N of 7 · <step>". The result becomes **Run again** or **Try again**.
- The log sits below in a fixed-height panel, and the page scrolls when the window is short.

**Blocked by:** 14, 06

**Status:** done (2026-10-23)

- [x] Sidebar gone; single column
- [x] Device, folder and Start inside ②
- [x] Bar and step line during a run
- [x] Checked at 100 % and 150 % scaling in both languages

## Comments

2026-10-23: One 720 px column in a `CTkScrollableFrame`: hero, ① Language, ② Start, the error card, the log (220 px, scrolls inside itself; the wheel over it does not move the page), then the version. ② opens with *Before you start* (idle and failed), then DEVICE and WORKING FOLDER, then the state heading and the one primary button. While running the button gives way to a determinate bar (`ink` on `disabled-fill`) and `progress_step`, "Step N of 7 · <step>", from `set_step`. The result button reads *Run again* or *Try again*; the end-of-run popup is gone. Checked from source by driving each state and screenshotting it, at 100 % in English and at 150 % (`set_widget_scaling`) in Indonesian. Not run against a phone, and 150 % was simulated in CTk rather than set in Windows display settings.

2026-10-23, after review: not built, and out of this ticket's scope as behaviour: ② shows the phone's status only once Start runs (`wait_for_device` is the only adb poll), so a missing phone is not an idle blocker; only a folder short of space is. The Windows footer is the version alone: Windows has no Technical tools or update check to put in the row.
