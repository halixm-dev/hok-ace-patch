# Never write a file the PC launcher lists

On the PC edition, the Windows patcher writes only package files the launcher does not list in `WXQ_Data\StreamingAssets\LocalFileList.json`, and it refuses to run while the game (`wxq*.exe`) or its launcher (`王者万象棋.exe`) is open. The launcher checks every listed file against its server list on start. A mismatch makes it repair the install, and a repair also empties `WXQ_Data\Package\builtin` (`GameToLauncherConfig.ini` `CleanableResFolders`), so every translated package comes back Chinese. The patched packages are not listed, so the translation survives as long as nothing listed changes. The trade is the window title: `AppTitleName.txt` is listed, so it stays 王者万象棋.

## Considered Options

- **Translate the title and update its size in `LocalFileList.json`.** The fork tried this (azydev 1.10.1.3). It worked in game, but the next launcher start found a mismatch, repaired the install, and the whole translation went with it.

## Consequences

- A launcher repair or update still replaces patched packages; the player runs Install again, and receipts that no longer describe the files are dropped rather than restored.
