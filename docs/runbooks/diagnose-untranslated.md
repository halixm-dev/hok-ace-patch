# Diagnose an untranslated string

Run this when a string still reads Chinese on the phone. It is diagnosed from the data, across **both**
data layers, rather than guessed at: an asset is not unreachable until the prime layer has been checked as
well as the override layer. The design behind the passes it names is in
[`docs/features/prime-rebuild.md`](../features/prime-rebuild.md) and
[`docs/features/prime-only-append.md`](../features/prime-only-append.md).

## Steps

1. **Capture the exact Chinese**, from the user's report or a screenshot:
   `adb exec-out screencap -p > s.png`.
2. **Look it up in the catalog.** `resources/catalog/catalog.json.gz` maps Chinese to the PC patcher's
   official English in `unique`. On Windows set `PYTHONIOENCODING=utf-8`, or printing CJK raises through
   cp1252.

   ```python
   import gzip, json
   cat = json.load(gzip.open("resources/catalog/catalog.json.gz"))
   print(cat["unique"].get("瑶妹"))   # -> "Yaria"
   ```

3. **Find the asset that holds it, in both layers**: the phone's dump for the override layer, and
   `package_rebuild.extract_prime` for the prime layer. Read each candidate through
   `QtsPackage(...).build_slot_map()` and `qts_relocate.read_raw`, and search those bytes for the UTF-8
   string. Note the **package id** and the **asset hash** (16 hex digits). `check_graphics.py --game`'s
   `absent` count is a census of the override layer alone; `tools/research/prime_probe.py` is the census
   that includes the prime layer (`assets/bin/Data/Package/builtin/`).
4. **Classify what you found:**

   | finding | the pass that owns it |
   |---|---|
   | in `catalog.known`, asset prime-only | the append pass, which reaches the override copy without changing the container's shape; a rebuild (`REBUILD_PACKAGES`) is the fallback for a package that must be laid out again whole |
   | in `catalog.known`, asset in the override layer | it should already apply; check whether staging dropped it for not fitting (`text_skipped`) and whether relocation recovered it |
   | not a catalog table, protobuf display text | the allowlist, after a device cycle (`docs/runbooks/device-cycle.md`) |
   | a package-19 prefab, or a definition table | nothing safe (`prime-rebuild.md`, `[S3]`) |
   | in neither layer | the launcher or native code; it cannot be patched through game data |

5. **Rule out the causes that are not a missing translation.** No catalog table covers the asset (the
   extra-text pass, or nothing); it is a prefab or a definition table, where a rewrite is unsafe; it comes
   from the launcher (the login title, `正在初始化游戏`) and is not in game data at all; or the translation
   exists and is **too long** for the mobile layout, which is a text-length problem.

## Done when

The string has a package id and asset hash in a named layer (or is shown to be in neither), and one row of
the table in step 4 names the pass that owns it; a fix that follows goes through a device cycle.
