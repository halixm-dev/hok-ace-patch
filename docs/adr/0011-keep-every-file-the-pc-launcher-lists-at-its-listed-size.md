# Keep every file the PC launcher lists at its listed size

On the PC edition, the Windows patcher never writes `LocalFileList.json` (at the game root), never changes the size of a file that list names, and refuses to run while the game (`wxq*.exe`) or its launcher (`王者万象棋.exe`) is open. The launcher checks the listed files against its server list on start. A mismatch makes it repair the install, and a repair also empties `WXQ_Data\Package\builtin` (`GameToLauncherConfig.ini` `CleanableResFolders`), so every translated package comes back Chinese.

The list names every package file, and the engine rewrites the ones it patches in place: one English install on a scratch copy (2026-11-20) changed the bytes of 16 files in packages `1`, `10`, `15`, `19`, `20`, `21` and `1050016095`, each index and each shard. Every one kept its exact listed size, the shards kept their modification times, and the engine left `LocalFileList.json` alone (`launcher_manifest.updated` false). The list records only `file` and `file_size`, and the fork's PC installs, which the same engine writes, survive launcher starts (user reports, 2026-11-18), so the launcher is taken to compare sizes. The PC cycles of 2026-11-21 (launcher 26111.0.4.30004, data 1.11.0.2) confirmed it: the launcher started without a repair after an English install, an Indonesian install and Remove translation. The trade is the window title: `WXQ_Data\StreamingAssets\Config\AppTitleName.txt` is listed, and a translated title has another size, so it stays 王者万象棋.

## Considered Options

- **Translate the title and update its size in `LocalFileList.json`.** The fork tried this (azydev 1.10.1.3). It worked in game, but the next launcher start found a mismatch against its server list, repaired the install, and the whole translation went with it.
- **Write only files the list does not name.** This record's first wording, after the fork's note that the patched packages were not listed. On the 2026-11-20 install they are, and the engine has no other way to patch a package, so that rule would leave nothing to install.

## Consequences

- A launcher repair or update still replaces patched packages; the player runs Install again, and receipts that no longer describe the files are dropped rather than restored.
- `tools/research/check_pc_install.py` fails when `LocalFileList.json` changes or a listed file leaves its listed size.
- The engine also deletes the launcher's QtsVFS watchdog ledgers (`QtsDataFolder\QtsVFSCache\Watchdog`, not listed); the launcher rebuilds them.
