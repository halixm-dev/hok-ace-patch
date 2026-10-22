# On a rooted phone, write the override layer directly

ADR 0001 sends every install through a temporary access APK because, without root, `run-as` from a debuggable build is the only way into the game's files, and that costs re-signing the game. When the user picks the **Root** shell provider, the Android patcher's worker runs as uid 0 and writes the override layer itself: no access APK, no re-signing, no APK install or reinstall, whatever APK is installed stays. The trade is a second write path to test and keep in step with the first, against keeping the game's own signature, so WeChat/QQ direct login keeps working on a phone first patched through root. ADR 0001 still holds for the Shizuku and wireless-debugging providers, which run as shell (uid 2000). Both paths share one pristine delta per phone and the same refusal before any game file is written. Design and evidence: [`.scratch/shell-providers/spec.md`](../../.scratch/shell-providers/spec.md).

## Consequences

- A phone patched through root keeps the game's own launcher name; `APP_NAME` belongs to the normal APK, which root never installs.
- A phone already patched through Shizuku keeps its re-signed normal APK under root: going back to the original signature means uninstalling the game, which wipes its data.
- Shizuku started with root (uid 0) is refused with a message naming the Root provider, so each provider has one write path.
- Hiding root from the game's anti-cheat is the user's job; the patcher never touches it.
