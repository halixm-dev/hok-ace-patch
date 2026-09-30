# A guide for an AI agent: fixing the strings that are still untranslated (Chessplayer names, the Card menu's faction tab, and the rest)

This guide was written from the experience of the project `hok-ace-mobile-en-v1` (an English patcher for
王者万象棋 / HOK ACE, `com.tencent.tmgp.osgame`, Android, without root). Use it for a similar project: a
Unity + QtsVFS (Tencent) game with a patcher that writes the translation into the game data on the phone.

Read `README.md` first. Every "tested" claim below comes from a test on the phone (Infinix X6853), game
versions 1.3.0.4 and 1.4.0.1.

The numbers quoted here are the ones that project measured on its own data. This repo has since measured
its own 1.4.0.1 data — `docs/compose/spec/prime-rebuild.md` §S1 and `README.md` — and those figures are the
ones to trust for this repo.

---

## 1. The mental model: why the strings are still Mandarin

The Android game data has **two layers**:

| Layer | Location | Contents |
|---|---|---|
| Prime (built into the APK) | `assets/bin/Data/Package/builtin/<id>/` inside the APK | Every asset as the APK was built |
| Override (downloaded) | `files/QtsVFSCache/packages/<id>/` (read via `run-as`) | Only the assets that **changed** since the APK was built |

The game reads override first, then falls back to prime. An older patcher only modified override, so **an
asset that exists only in the APK was never touched**. On 1.3.0.4, 413 of the catalog's 497 text tables
(loading tips, chessplayer names, most of the UI) and all 72 arena/map textures existed only in the APK.

Other reasons a string stays Mandarin:

1. The string is in an asset the **PC catalog does not cover** (not a language table) → the `extra_text`
   pass.
2. The string is in a **Unity prefab** (package 19) or a definition table → often *unsafe* to change
   (see §5).
3. The string comes from the **launcher**, not from game data (e.g. "正在初始化游戏", the login title) →
   it cannot be patched through the data at all.
4. The translation exists but is **too long** for the mobile layout (e.g. the "Chessplayer" tab overlaps
   "Combat Power") → that is a text-length problem, not a missing string.

---

## 2. The diagnosis flow (work through it in order)

1. **Screenshot and record the exact Mandarin string** (ask the user, or
   `adb exec-out screencap -p > s.png`). Copy the original characters, e.g. `瑶妹`, `棋手`.
2. **Look it up in the catalog**: `resources/catalog/catalog.json.gz` → the `unique` key is a map from
   Mandarin to the PC patcher's official English. `table_hashes`/`schema` show which tables are covered.
   ```python
   import gzip, json
   cat = json.load(gzip.open("resources/catalog/catalog.json.gz"))
   print(cat["unique"].get("瑶妹"))   # -> "Yaria"
   ```
   On Windows, set `PYTHONIOENCODING=utf-8` before printing CJK (cp1252 will crash).
3. **Find the asset that holds the string**, in both layers:
   - override: the dump from the phone (`run-as <pkg> tar -cf - -C files/QtsVFSCache packages`)
   - prime: extract it from the APK (`package_rebuild.extract_prime`)
   Read each asset with `QtsPackage(...).build_slot_map()` + `extra_text.read_raw`, then search the bytes
   for that UTF-8 string. Note the **package id** and the **file hash** (16 hex digits).
4. **Classify the result**:

| Finding | Action |
|---|---|
| The hash is in `catalog.known` and the asset only exists in prime | Add the package to `REBUILD_PACKAGES` (§3) |
| The hash is in `catalog.known` and the asset is in override | It should already work; check the stager log (was the asset dropped for not fitting its slot?) |
| Not a catalog table, but protobuf display text | Add the hash to `DISPLAY_ASSETS` in `extra_text.py` after testing it (§4) |
| A Unity prefab in package 19 / a definition table | See §5 — already proven to crash or hang |
| Not found in the data at all | Probably the launcher or native code; report that it cannot be patched |

---

## 3. The main fix: rebuild the package whole (this is what fixed the Chessplayer names)

The chessplayer names on the Chessplayer page (`瑶妹`→Yaria, `镜`→Jing, `乔汐`→Qiao Xi, `白歌`→Bai Ge, and
so on) live in text tables of package **1** that exist only in the APK. The solution is to build the
override package for package 1 again, whole.

Code: `tools/package_rebuild.py`, `tools/qts_builder.py`, called from
`build_device_patch.rebuild_prime_packages`.

How it works:

1. `extract_prime(apk, REBUILD_PACKAGES, work/"prime")` — copy the package's `.db` files out of the APK.
2. For each override asset: read the raw bytes (from override, or from prime when an override entry has no
   data of its own), run `transform` (catalog table → `adaptive.translate_table`, graphics →
   `mobile_graphics`, `SAFE_ASSETS` → `pb_text.rewrite`).
3. Add the **prime-only assets that changed** after translation. Prime-only assets that did not change are
   left out — the game keeps reading those from the APK.
4. Build with Tencent's official builder: `QtsVFS.dll` + `QtskDB.dll` from the PC game
   (`WXQ_Data/Plugins/x86_64`, bundled in this repo as `resources/qtsvfs/`). The PC format equals the
   Android format (the entry key and chunk hash are derived from the file hash and the contents).
5. `qts_builder.finalize`: remove the records only the builder writes (the global-index node, the
   export-setting and remain-dir nodes), copy the `QTSF_PACKAGE` node and the entry flags from the
   original override package.
6. **Read back**: every asset is read again and compared byte-for-byte; the package node must be
   identical. Never push to the phone if the read-back fails.

Traps already found:

- `MaxStorageSize` **must** be set (1 GiB). If it is not, the builder reads uninitialised memory and writes
  one storage file per asset.
- The packed compression flag is `level << 16 | type` (level 5 by default).
- Only rebuild the packages that actually need it (`REBUILD_PACKAGES = ("1", "1050016095")`). Other
  packages are fine in place; a rebuild means recompressing hundreds of MB.
- A package that gets rebuilt is skipped by the in-place stager and by the `extend` pass
  (`skip=rebuilt`).

Result on 1.3.0.4: package 1 = 684 assets (97 translated from override + 303 new tables from the APK);
package 1050016095 = 66 arena/map textures.

---

## 4. Non-catalog assets: `extra_text.py`

For strings that are not in any catalog language table but exist in protobuf display assets:

- `pb_text.rewrite` replaces strings that match `catalog.unique` **exactly** (plus `OFFICIAL_FIXES`).
- AI opponent names (`BOT_NAME_ASSETS`, ~11k names) are romanised with `pypinyin`, because there is no
  official translation for them.
- Only hashes in `SAFE_ASSETS` are modified. It is an **allowlist, not a blocklist**: replacing every
  matching string in the other config assets broke the login screen, because some Mandarin strings there
  are *lookup keys*.
- Packages `10` (skill-editor labels) and `14` (gameplay scripts) are excluded: the Mandarin there is
  logic.

To add a new asset to `DISPLAY_ASSETS`: add **one at a time** (or a small set), test it on the phone
(loading through to "Click to Enter Game", open the Card menu, the lobby), then record the result in a
comment — including the failures. The list of proven-damaging hashes lives in the comments of
`extra_text.py`:

- Loading stalls at 40–80%: newbie unlock rewards `41974B12`, one of the small label tables
  `8B5C2394/A07BC11B/4CEF98BE/63922EF4/7E3F57D7/3914DBBF/14DEEB2E`.
- Card menu breaks (cards become grey placeholders): hero role guide
  `DD11D75B/CA340C43/BBFD4BE9/CAC6E38D`.

---

## 5. What has already been tried and FAILED (do not repeat without a new idea)

| Attempt | Result |
|---|---|
| Change the name in chessplayer definition `A8BC70BB87700709` field 37 | The lobby hangs while loading, even after every reference in packages 1 and 14 was renamed too. The name on the Chessplayer page is fixed through package 1's text tables (§3), not through this definition. |
| Rewrite every Unity prefab label in package 19 (`UNITY_TEXT_PACKAGES = {"19"}`) | The lobby hangs. |
| Rewrite **only the faction names** in the 15 package-19 prefabs that display them (the Card menu's faction tab) | The game crashes at start: `stack corruption detected`. The package-19 prefabs are now left alone. |
| Code injection into the APK | Killed by anti-cheat. |
| A "prebaked" APK with translated assets | `IsPrebuild errorCode:151`. |
| Modifying the language packages inside the APK before the update | Tencent's updater uses binary diffs; the diff breaks. |

### The Card menu's faction tab

Status: **not safely solved** through the prefabs. Suggested next steps for the following agent:

1. First check whether the faction names are also in a **catalog text table that is prime-only** in
   package 1. If they are, the §3 rebuild may already have translated them — verify on the phone before
   touching a prefab.
2. If the label only exists in a package-19 prefab, do not rewrite its serialized string (a changed length
   crashes). Options not yet tried: replace it with a string of the **same or shorter byte length with
   padding**, so the serialized layout does not shift; or find out whether the prefab takes its text from
   a table key (and then translate the table). Test one prefab first.
3. If there is no safe way, document it as a known limit.

---

## 6. The device test loop

1. Make sure the game data has fully updated to the login screen (after a game update: clear the data,
   download it again, then patch again).
2. Build the patch offline against a data dump first (`python tools/build_device_patch.py --runtime
   resources/runtime --game <dump> --catalog resources/catalog --work <w> --output <o> --apk <apk>
   --builder resources/qtsvfs`). It needs Python **3.12** (the compiled `wxq_patch` runtime).
3. Push to `files/QtsVFSCache/packages/<id>/`, and delete `files/QtsVFSCache/Watchdog/*` (see
   `app/patcher_core.py`).
4. Open the game and check `adb logcat` for QtsVFS errors; screenshot the login screen.
5. After logging in (the user must use *Scan to login*; direct WeChat/QQ login does not work on a re-signed
   APK): check the loading tips, the Chessplayer page, the lobby, the Card menu, the arena artwork.
6. Back up `packages` + `Watchdog` before pushing, so you can roll back.

## 7. Working rules

- One change per test; record the result (success/failure + symptom + date) in a comment next to the hash.
- Use the official translation from the PC catalog; do not translate freely unless there is no equivalent
  (and then put it in `OFFICIAL_FIXES` with a reason).
- Do not change the length or structure of a binary asset you do not understand; always read back before
  pushing.
- Do not claim something is "translated" before the user has seen it on the phone after logging in.
