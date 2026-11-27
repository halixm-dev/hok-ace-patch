# wxq_patch runtime: what the patchers reach, its data, and the port traps

Research for ADR-003 (`rust/DECISIONS.md:26`). Measured on 2026-11-27 against `resources/runtime/wxq_patch/*.pyc`
(CPython 3.12 bytecode, loaded with `.venv\Scripts\python.exe` 3.12.10, `resources/runtime` appended to `sys.path`).
Method: `marshal` + `dis` over every code object; a call graph built from `LOAD_GLOBAL`/`LOAD_NAME`
(resolved through each module's globals), `module.attr` pairs, and `LOAD_ATTR` method names (over-approximated: any
method of that name in any runtime class), plus the lazy `IMPORT_NAME`/`IMPORT_FROM` sites, read by hand.
Sizes are `len(co_code)` summed over a function and its nested code objects (bytes of bytecode, not of source).
Line numbers `Lnn` are the `co_firstlineno` / `starts_line` the bytecode carries for the missing `.py`.

## 1. Entry points and the reached runtime

### What this repo calls (excluding `tools/research/`)

| Runtime name | Callers |
|---|---|
| `adaptive.load_catalog` (L133), `adaptive.Catalog` (L59) | `tools/build_device_patch.py:632`, `tools/device_extensions.py:381`, `tools/pc_catalog.py:454,478`, `android/app/src/main/python/android_bridge.py:141,146,729`, `build_storage.py:62` |
| `adaptive.scan` (L183) | `tools/build_device_patch.py:680`, `tools/build_mobile_patch.py:73` |
| `adaptive.discover` (L160) | `tools/device_extensions.py:170,382` |
| `adaptive.translate_table` (L88) | `tools/package_rebuild.py:106` |
| `adaptive.run` / `_run` (L824), `receipt_root` (L263), `pending_recovery`, `recover_pending` | `app/pc_edition.py:272,333,399,409` |
| `qtsvfs.QtsPackage` (`__init__`, `entries`, `shard_paths`, `index_path`, `build_slot_map`, `extract`), `parse_index`, `iter_chunk_slots` | 13 `from wxq_patch.qtsvfs import QtsPackage` sites, e.g. `tools/qts_insert.py:69`, `tools/pristine_delta.py:557`, `tools/qts_relocate.py:592-621` |
| `unity_package_installer.stage_unity_package`, `capacity_report` | `tools/build_device_patch.py:615,686,707`, `tools/build_mobile_patch.py:70,105` |
| `installation.discover_installations`, `resolve_game_root` | `app/pc_edition.py:102,125` |

No caller imports `gemini`, `protobuf_i18n`, `pipeline`, `glossary`, `hok_terminology`, `combined_installer`, or any data module
(grep of `tools app android/app/src/main/python`; `glossary.items` at `tools/build_device_patch.py:639` is a local dict,
`installer.write_bytes` at `app/adb_driver.py:32` is a `Path`).

### Monkeypatches (the runtime calls these by module attribute, so the Rust port must expose the same seams)

- `tools/engine_hooks.py:62-75`: replaces `adaptive.load_catalog` (whole replacement: reads the gzip JSON itself and
  builds `adaptive.Catalog(data)`, `engine_hooks.py:90-107`), and in a PC job wraps `adaptive.scan` and replaces
  `adaptive.receipt_root`. The original `load_catalog` stays reachable: `android_bridge.py:141,146,729` call it without
  `engine_hooks.install()` unless `build_patch` already ran in the process.
- `tools/qts_relocate.py:585-621`: replaces `qtsvfs.QtsPackage.build_slot_map` with a B-tree-aware version.

### Reached logic (call graph closure)

| Module | Reached | Reached bytes / module bytes | Reached functions (bytes) |
|---|---|---|---|
| `adaptive` | 32 | 23,216 / 25,370 | `_run` 3610, `commit` 3026, `scan` 2404, `prune_stale_state` 1862, `translate_table` 1400, `recover` 1384, `clear_watchdog_state` 1050, `Catalog.__init__` 956, `_matching_restore_items` 782, `_matching_install_files` 732, `discover` 582, `recover_pending` 532, `_merge_watchdog_cleanup` 416, `apply_graphic_payload` 402, `find_restore` 400, `_stage_launcher_manifest` 376, `_matching_package_hash_targets` 356, `_receipt_matches_live` 348, `receipt_root` 334, `_watchdog_dirs` 314, `write_json` 312, `_stage_package_hashes` 270, `fields` 260, `pending_recovery` 236, `safe_path` 166, `load_catalog` 160, `run` 160, `_make_writable` 134, `Catalog.lookup` 118, `_matches_hash` 104, `mutation_lock` 30. Unreached: `main` 2154 |
| `qtsvfs` | 25 | 10,760 / 11,328 | `insert_slot_position_references` 2720, `iter_chunk_slots` 1164, `QtsPackage.extract` 1004, `find_slot_position_references` 948, `parse_index` 702, `QtsPackage.__init__` 502, `_find_first_entry` 340, `build_slot_map` 266, `_skip_padding` 190, `_u32` 54, frozen dataclasses `IndexEntry`, `ChunkSlot` (generated `__init__/__eq__/__hash__/__repr__`). Unreached: `from_flat_dir`, `payload_capacity` |
| `installer` | 12 | 12,332 / 30,692 | `_merge_preceding_slot_donation_plans` 3906, `_find_fit` 2548, `_apply_preceding_slot_donations` 1656, `_plan_preceding_slot_donation` 1614, `_slot_bytes` 686, `_apply_official_chunk_metadata` 476, `_load_qtsvfs` 400, `_assert_game_stopped` 380, `sha256_file` 296, `_moved_slot_offsets` 166, `_qtsvfs_bin_dir` 132, `_compress` 72. Unreached: `stage_patch` 10882, `install` 2370, `_native_qtsvfs_read_canary`, `_build_official_descriptor`, `revert` |
| `unity_package_installer` | 5 | 11,640 / 14,902 | `stage_unity_package` 7218, `build_official_metadata_batch` 2136 (PC only), `capacity_report` 1028, `_fit_with_preceding_donations` 786, `_replacement_files` 472. Unreached: `stage_full_unity_package`, `main` |
| `native_verify` | 4 | 7,838 / 7,838 | `verify_staged_package` 3174, `_verify_structural` 2648, `_verify_changed_positions` 1402, `_verify_contents` 614 (PC only, lazy import at `stage_unity_package` offset 6480) |
| `package_metadata` | 4 | 5,086 / 5,174 | `query_package_hash` 2882, `stage_package_hash_metadata_batch` 1152, `_record` 556, `find_package_hash_entry` 496 (PC only) |
| `installation` | 6 | 4,736 / 4,736 | `config_candidates` 1476, `registry_candidates` 1350 (`winreg`), `discover_installations` 1208, `resolve_game_root` 320, `available_drives` 250, `likely_folders` 132 (PC only) |
| `launcher_metadata` | 4 | 1,814 / 1,814 | `stage_local_file_list` 864, `_load_entries` 464, `local_file_list_mismatches` 390, `_name_key` 96 (PC only) |
| `gemini` | 1 | 800 / 5,354 | `validate_translation` 800 only |
| `protobuf_i18n` | 3 | 554 / 2,622 | `decode_varint` 180, `encode_varint` 188, `ProtobufError` |

Totals: about 78.8 KB of bytecode reached across both editions. The **mobile** closure is 39.3 KB: `adaptive`
(`Catalog`, `load_catalog`, `scan`, `discover`, `translate_table`, `fields`, `apply_graphic_payload`: 6.3 KB),
`qtsvfs` 10.8 KB, `installer` slot planners 11.4 KB, `unity_package_installer` 9.5 KB, `validate_translation`,
varints. The mobile pipeline passes its own `metadata_builder` (`tools/build_device_patch.py:705-712`), so
`stage_unity_package` skips `build_official_metadata_batch` and the `native_verify` import: both sit behind
`metadata_builder is build_official_metadata_batch` (`stage_unity_package` offsets 6460-6474).
The **PC** path (`adaptive._run`, offset 1808) calls `stage_unity_package` without `metadata_builder`. It therefore
reaches `build_official_metadata_batch`, `native_verify` and `package_metadata.query_package_hash`, which all load the game's
own `WXQ_Data\Plugins\x86_64\QtsVFS.dll` + `QtskDB.dll` through `ctypes.CDLL` (`installer._load_qtsvfs`,
`installer._qtsvfs_bin_dir`). A Rust PC edition must either FFI-load that DLL or reimplement what it computes. Binding the
game's DLL at run time is a different question from ADR-005's "no C/C++ bound", and the ADR needs a ruling on it.
`_assert_game_stopped` shells out to `tasklist /FO CSV /NH` and matches `wxq.exe`, `wxqbase.exe`, `wxq_helper.exe`, `wxqhelper.exe`.

Never reached from any entry point: all of `pipeline` (27 functions), `combined_installer` (17), `glossary` (8),
`gemini.GeminiBatchTranslator` and its helpers, `protobuf_i18n.parse_i18n/serialize_i18n/I18nRecord`.

### Logic vs data modules

- Logic: `adaptive`, `qtsvfs`, `installer`, `unity_package_installer`, `native_verify`, `package_metadata`, `installation`,
  `launcher_metadata`, `protobuf_i18n`, `gemini` (one function); unreached logic: `pipeline`, `combined_installer`, `glossary`.
- Data (no functions, or one import-time helper): the 21 `direct_*` modules, `remaining_content_groups`,
  `live_config_content_groups`, `update_20260904_content_groups`, `hok_terminology`, plus the dict constants in `glossary`.

**No data module is read by reached code.** The data constants that reached functions load are only small ones in
logic modules: `adaptive.CJK_RE`, `INTERNAL_INDEX` (`WXQ_Data\Package\builtin\0\0.db`), `WATCHDOG_DB_NAMES`
(`BrokenList.db`, `PatchList.db`, `StorageStatus.db`, `History.db`), the four `gemini` regexes, the `COMP_*`/`DESCRIPTOR_*`/
`MAX_QTS_PAGE_SIZE` ints, `launcher_metadata.LOCAL_FILE_LIST`, `package_metadata.PACKAGE_MARKER`/`MAX_PACKAGE_NAME`, and
`unity_package_installer.PACKAGE_ID`. Importing `adaptive` still imports them all: `adaptive` imports `installer`
(offset 182), `installer` imports `pipeline` (offset 138, for `package_dir` and `parse_i18n`, neither reached), and
`pipeline` imports every data module (offsets 210-478) and `glossary` -> `hok_terminology`. The data is loaded but never consulted;
the text the patchers write comes from `resources/catalog*/catalog.json.gz` through `Catalog`.
Under ADR-004 the Rust core needs none of it. ADR-003's generator is only needed if the Rust port has to cover `pipeline`, which no caller reaches.

## 2. Data module shapes and a lossless dump

| Module.value | Shape | Entries |
|---|---|---|
| `direct_achievement_details_01/02/03` | `dict[str,str]` | 500 / 500 / 565 |
| `direct_remaining_group_overrides_01..07` | `dict[str,str]` | 500 ×6, 357 |
| `direct_equipment_overrides` | `dict[str,str]` | 763 |
| `direct_additional_group_overrides` | `dict[str,str]` | 665 |
| `direct_update_20260820_content` / `_main` | `dict[str,str]` | 661 / 123 |
| `direct_fidelity_corrections` (`CONTENT` / `MAIN`) | `dict[str,str]` | 113 / 15 |
| `direct_live_config_overrides`, `direct_content_overrides`, `direct_semantic_fidelity_corrections`, `direct_system_group_overrides`, `direct_main_overrides` | `dict[str,str]` | 113, 59, 42, 51, 26 |
| `remaining_content_groups`, `update_20260904_content_groups`, `live_config_content_groups` | `dict[str, dict[str,int]]` (`zh_hash`/`en_hash`) | 98, 16, 5 |
| `hok_terminology` (9 dicts) | `dict[str,str]` | 1-281 |
| `glossary` `NAME_ALIASES`, `GLOSSARY_ALIASES`, `CONTROL_TERM_ALIASES`, `GLOBAL_ENGLISH_ALIASES` | `dict[str, tuple[str,...]]` | 81, 207, 15, 28 |
| `pipeline` merged views (`CONTENT_GROUPS` 221, `CONTENT_TRANSLATION_OVERRIDES` 60, `PC_SETTINGS_TRANSLATION_OVERRIDES` 9, ...) | as above, built at import | |

The direct override modules hold 7,553 string pairs in about 1.14 MB of UTF-8 JSON.
- No value is callable. Two modules run code at import: `direct_achievement_details_02` and `_03` define
  `_polish_achievement_detail_02/03` (`str.replace` chains, gated on `'三分' in source`, `'棋手' in source`, `'阶' in source`) and
  build the dict with a comprehension over it (`direct_achievement_details_02` module code offsets 4666-4710). The generator
  must dump the **import-time value**, not the literal constants in the code object.
- `json.dumps(v, ensure_ascii=False)` -> `json.loads` is exactly equal for every `dict[str,str]` and `dict[str,dict[str,int]]`
  value, key order included. It is **not** equal for the tuple-valued `glossary`/`pipeline` dicts, because tuples come back as lists.
- Strings: no lone surrogates and no non-BMP characters. Many hold newlines, and two hold `\x0b` (vertical tab;
  `direct_remaining_group_overrides_06`, a hero biography). Emitting either through a hand-written Rust literal would be fragile.
- Ints in `*_content_groups` run from 64,635,018,962,464,455 to 18,436,112,764,235,244,627, above `i64::MAX`. They need `u64`, and any
  JSON reader that goes through f64 (JavaScript, some Kotlin parsers) corrupts them.

Proposed generator output: one UTF-8 JSON file per module, `{"module": ..., "values": {NAME: value}}`, written with
`ensure_ascii=False`, insertion order kept. Tuples become arrays, and a `"tuples": [NAME,...]` list names the values to read back as tuples.
Ints are written as JSON integers. Rust reads them with `serde_json` (`preserve_order` feature → `IndexMap`), with `u64` for the groups.
The generator re-imports the runtime and checks `strict_eq(original, revived)` (type-exact, ordered) before writing. Gzip each file (as
`catalog.json.gz` already is) or embed with `include_bytes!`.

## 3. Network code

The closure contains no use of `httpx`, `urllib`, `email`, `asyncio`, `anyio`, `socket` or `ssl`. The full set of
external names the reached functions load is: `collections`, `contextlib`, `ctypes`, `dataclasses.replace`, `errno`, `gzip`, `hashlib`, `json`,
`lz4.block`, `mmap`, `os`, `pathlib`, `re`, `shutil`, `stat`, `struct`, `subprocess.run`, `tempfile`, `time`, `uuid`, `winreg`.
They are still **imported**. `gemini` imports `asyncio` and `httpx` at module level (offsets 18, 94), and `adaptive` imports `gemini` (offset 166)
for `validate_translation`. After `import wxq_patch.adaptive`, `sys.modules` holds `httpx.*`, `asyncio.*`, `email.*`, `http.client`,
`urllib.request`, `ssl` and `socket`. That is an import side effect only, so a Rust port needs no HTTP stack. The only HTTP caller is
`GeminiBatchTranslator._request`, which nothing reaches.

## 4. Decompilers for 3.12

| Tool | 3.12 support (own docs) | Result here |
|---|---|---|
| uncompyle6 3.9.3 | "accepts bytecodes from Python version 1.0 to version 3.8" (https://github.com/rocky/python-uncompyle6) | Tried in a throwaway venv (`pip install` from PyPI, run with `-I`): `Unsupported Python version, 3.12.0, for decompilation` |
| decompyle3 3.9.3 | runs on and targets 3.7-3.8 (https://github.com/rocky/python-decompile3) | Same venv: `Unsupported Python version, 3.12.0, for decompilation` |
| pycdc (Decompyle++) | Has an opcode map `bytes/python_3_12.cpp` (https://github.com/zrax/pycdc/tree/master/bytes). Open issue #575 "Unsupported opcode: CALL_INTRINSIC_1"; #426 (3.12, `BEFORE_WITH`) closed | Not installed, not on PyPI, so not tried. `adaptive` uses `CALL_INTRINSIC_1` (`fields` offset 256) and `BEFORE_WITH` (`load_catalog` offset 54), so expect partial output |
| PyLingual | "all released Python versions since 3.6"; uses translation and segmentation ML models; checks its output by recompiling (https://github.com/syssec-utd/pylingual) | Not tried: installed from a source clone with uv plus models, so not a well-known PyPI package |

Verdict: no installed or PyPI tool decompiles this bytecode. Port from `dis` output (the method used here), and treat any
pycdc or PyLingual output as a reading aid that must be checked against `dis`.

## 5. Semantic traps in the reached logic

1. **Regex lookahead.** `gemini.PLACEHOLDER_RE` = `\{[^{}]*\}|%(?:\d+\$)?[-+0 #]*(?:\d+|\*)?(?:\.\d+)?[diuoxXfFeEgGaAcspn%](?![A-Za-z])`.
   The `regex` crate supports no look-around (https://docs.rs/regex/latest/regex/#syntax), so use `fancy-regex` or code the
   `(?![A-Za-z])` check by hand. The other patterns are `CJK_RE` `[㐀-䶿一-鿿豈-﫿]`, `TAG_RE`
   `<(?:/?[A-Za-z][^>]*|/)>` and `CONTROL_TOKEN_RE` `[╀-╿]`, all with flags=32 (`re.UNICODE`). Python's `\d` means any Unicode
   `Nd` here, which matches the default `regex` `\d`. `validate_translation` compares `Counter(findall)` multisets and the
   ordered `findall` lists for tags.
2. **Code-point lengths.** `validate_translation` (gemini L47-70) rejects when `len(translated) > max(len(source)*8, 48)` and
   `len(source) >= 4`. `len` counts code points (`chars().count()`), not bytes. It also compares `str.count(';')`.
3. **`str.strip()` / `isspace`.** The Python whitespace set includes `\x1c`-`\x1f`, `\x85` and `　`. Measured: `' \x1c\x1f\x85　x'.strip() == 'x'`.
   Rust `str::trim` skips `\x1c`-`\x1f`. `validate_translation` returns `(False,'empty')` on `not translated.strip()`.
4. **`casefold` and Windows path order.** `receipt_root` = `sha256(str(game.resolve()).casefold().encode())[:24]` (L263;
   mirrored at `tools/engine_hooks.py:44-51`). `casefold` is full Unicode folding (`ß`→`ss`), not `to_lowercase`. `sorted()` on
   `WindowsPath` compares `str(self).lower().split(sep)` (CPython 3.12 `Lib/pathlib.py:485-535`), so the order is case-insensitive.
   On Android (`PosixPath`) it is case-sensitive. Sorted paths: `QtsPackage.__init__` shard list
   (`sorted(p for p in glob(f"{id}_*.db") if p.is_file())`, L397), `discover` (`sorted(builtin.iterdir())`, L166, names
   `isdecimal()`), `_replacement_files` (`sorted(glob('*.assets'), key=lambda p: p.name)`, L48), plus the receipt and state
   globs in `find_restore`, `recover_pending` and `prune_stale_state`. All are **lexicographic**, so `21_10.db` sorts before `21_2.db`.
5. **Dict and Counter order reaches output.** `scan` returns `dict(total)` built from a `Counter` in first-increment order (L260).
   `translate_table` returns a `Counter`. `Catalog.context`/`english_updates` keep JSON row order. ADR-004's equal-summary bar needs
   insertion-ordered maps (`IndexMap`), not `HashMap`. `stage_unity_package` writes JSON with `indent=2, sort_keys=True` (offset 6696),
   `write_json` with `indent=2` (unsorted, `ensure_ascii=True`), and `launcher_metadata.stage_local_file_list` with `ensure_ascii=False,
   separators=(', ', ': ')`. Byte-equal output needs a Python-compatible JSON writer: `\uXXXX` with surrogate pairs under
   `ensure_ascii`, Python's float `repr`, and its separators. `serde_json` does none of these by default.
6. **Varint width.** `protobuf_i18n.decode_varint` loops while `shift < 70`, so up to 10 bytes can give values up to 2^70 as a Python int.
   A Rust `u64` would overflow or wrap. Use `u128` or replicate the bound and error exactly. `encode_varint` raises on negative values.
7. **Hex identity strings.** `Catalog.lookup` and `translate_table` key `context` by `(f"{asset:016X}", key, source)`
   (uppercase, zero-padded). `Catalog.__init__` parses `table_hashes` and `graphics[].hash` with `int(h, 16)`. `lookup` falls
   back to `unique.get(source)`, which is evaluated eagerly.
8. **UTF-8 decode errors as control flow.** `translate_table` decodes fields 10/18 with strict `.decode('utf-8')`.
   `scan` catches `(ProtobufError, UnicodeDecodeError)` and counts `unrecognized_tables` only when the hash is in
   `catalog.known` (L231-234). It catches `(ValueError, OSError, KeyError, LZ4BlockError)` per asset and records `str(exc)` as the
   skip `reason` (L212-215), re-raises `PermissionError` (L210), and catches `(RuntimeError, ValueError, KeyError)` around staging to
   count `capacity_skipped` (L243). `unity_package_installer._fit_with_preceding_donations` uses `RuntimeError` to fall back
   (L75, L96), and `_replacement_files` skips a non-hex stem on `ValueError` from `int(stem,16)` (L50-51). Rust needs typed errors that
   map onto these same classes. The PC report and the log also carry Python's own messages (`str(KeyError(k))` is `repr(k)`, plus lz4's
   message text), but the mobile summary keeps only `skipped_count` (`tools/build_device_patch.py:872`).
9. **Floats.** The only float is `report['seconds'] = round(time.monotonic() - start, 3)` (`_run` L990). It is timing, and ADR-004
   exempts it. f-strings use `{n:,}` thousands separators in log lines only.
10. **Big-int arithmetic.** The slot planners (`installer._find_fit`, `_merge_preceding_slot_donation_plans`, `qtsvfs.insert_slot_position_references`)
    use `//`, `%`, `-` and `&` on offsets. Python `//` and `%` floor toward negative infinity, while Rust `/` and `%` truncate,
    so any subtraction that can go negative needs `div_euclid`/`rem_euclid`. Sizes go through `struct.pack_into`/`unpack_from`, whose format strings fix the width.
11. **`sorted` stability.** Python's sort is stable, and so is Rust's `sort_by`. Do not use `sort_unstable` anywhere ties are possible
    (`installer._find_fit`, `_merge_preceding_slot_donation_plans`, `package_metadata.stage_package_hash_metadata_batch`).
12. **Frozen dataclasses.** `IndexEntry`, `ChunkSlot` and `I18nRecord` are `frozen=True, eq=True`, so they hash and compare by every field.
    `stage_unity_package` uses `dataclasses.replace`. A Rust struct with derived `Eq + Hash` fits.

## Recommended port order

1. `protobuf_i18n.decode_varint`/`encode_varint` and `adaptive.fields` (tiny, pure).
2. `gemini.validate_translation` with its four regexes (traps 1-3). Record it against a corpus of every catalog pair.
3. `adaptive.Catalog` + `load_catalog` (the gzip JSON, ordered maps) and the `engine_hooks` load path that wraps it.
4. `adaptive.translate_table` (pure bytes→bytes + counts). It is the core of the text pass, and checking it per table is easy.
5. `qtsvfs` (`parse_index`, `iter_chunk_slots`, `QtsPackage`, `extract`, the slot-position references), with the
   `qts_relocate` B-tree `build_slot_map` as the version to match.
6. `adaptive.discover` + `scan` (path sorting, exception mapping, the `total` order).
7. `installer` slot planners + `unity_package_installer.stage_unity_package` / `capacity_report` with the caller-supplied
   metadata builder. This finishes the mobile closure (39.3 KB).
8. PC only: `installation`, `launcher_metadata`, `package_metadata`, `native_verify`, `build_official_metadata_batch`
   (blocked on a ruling about the game's `QtsVFS.dll`), then `adaptive.commit`/`recover`/`_run`/`prune_stale_state`/watchdog.
9. Last and optional: the data generator for the 25 data modules. Nothing reached reads them (section 1), so it only matters if
   `pipeline` is ever ported.
