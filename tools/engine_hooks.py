"""Every hook this repo puts into the translation runtime in one place.

The runtime ships as compiled bytecode from the PC patcher, so this repo changes what it does only by
replacing module attributes. Each is looked up by name at call time (`adaptive._run`
calls `scan` and `commit` through the module, `commit` and `find_restore` call `receipt_root` the
same way), so the replacement is seen by every caller:

- `load_catalog`: the catalog as it loads gets the catalog supplement, the measured mode copies of its
  tables (`catalog_updates.admit_tables`) and the terminology table (`terminology`). Both editions take it; the mobile pipeline installs it before its first load.
- `scan`: the language's resource terms are expanded in the replacements the scan materialized
  (`resource_tokens.expand_staged`). PC edition only: the mobile pipeline calls the same function
  itself, after it has dropped the uncatalogued tables.
- `receipt_root`: the PC edition's receipts live under this patcher's working folder,
  `<receipts>/<game id>`, never in the engine's default folder (the upstream PC patcher's
  `%LOCALAPPDATA%\\HoK Ace English Patch\\adaptive`). PC edition only.
- `lz4`: the four runtime modules that use LZ4 use the Rust backend when the extension loads.
- `qtsvfs`: Rust reads package indexes, shard headers and asset payloads when the extension loads.
- `translate_table`: the Rust wire reader and validator translate whole tables when the extension
  loads. The Python scanner still owns discovery, package I/O and staging.

`install()` is idempotent: a hook already in place is never wrapped twice, and a second PC install
only moves the receipts root. The PC hooks are taken only when the caller passes `receipts`, which
only a PC job does; a PC job runs in its own child process, so they never reach a mobile run.

Measured on the 2026-11-20 runtime: between `scan` and `commit` the engine records no hash of a
replacement file, only the source files' fingerprints; `commit` hashes the staged packages itself.
That is what makes rewriting the replacements after the scan safe.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

# The runtime attributes the hooks replace; `check` and `--smoketest` fail when one is missing.
HOOKED_ATTRIBUTES = ("load_catalog", "scan", "receipt_root")

_state: dict[str, object] = {"receipts": None, "log": print}


def check() -> list[str]:
    """The hooked attributes the runtime lacks (empty when every hook has a place to go)."""
    from wxq_patch import adaptive

    return [name for name in HOOKED_ATTRIBUTES if not callable(getattr(adaptive, name, None))]


def game_id(game: Path) -> str:
    """The engine's own identity for a PC installation: ``sha256(resolved path, casefolded)[:24]``.

    Mirrors `adaptive.receipt_root`, so the receipts folder and the per-install stage of one game share
    a name.
    """
    return hashlib.sha256(str(Path(game).resolve()).casefold().encode()).hexdigest()[:24]


def install(*, receipts: Path | None = None, log=print) -> None:
    """Install the catalog and codec hooks, plus the PC hooks when <receipts> is given.

    <receipts> is the PC edition's receipts root, `<work>/pc/receipts`; each game's receipts go into
    `<receipts>/<game id>`. <log> takes the PC `scan` hook's one line per run.
    """
    from wxq_patch import adaptive

    native = _runtime_extension()
    native_catalog = getattr(native, "RuntimeCatalog", None)
    if not getattr(adaptive.load_catalog, "_engine_hooks", False):
        adaptive.load_catalog = _load_catalog_hook(adaptive.Catalog, native_catalog)
    if native_catalog is not None and not getattr(adaptive.translate_table, "_engine_hooks", False):
        adaptive.translate_table = _translate_table_hook(adaptive.translate_table, adaptive.ProtobufError)
    _install_codecs()
    if getattr(native, "qts_index", None) is not None:
        _install_qts_readers(native)
    if receipts is None:
        return
    missing = check()
    if missing:
        raise RuntimeError(f"translation runtime lacks {', '.join(missing)}; no PC hook installed")

    _state["receipts"] = Path(receipts)
    _state["log"] = log
    if not getattr(adaptive.scan, "_engine_hooks", False):
        adaptive.scan = _scan_hook(adaptive.scan)
    if not getattr(adaptive.receipt_root, "_engine_hooks", False):
        adaptive.receipt_root = _receipt_root


def _install_codecs() -> None:
    import lz4.block
    from types import SimpleNamespace

    import codec_backend

    if codec_backend.backend_name() != "native":
        return
    from wxq_patch import installer, native_verify, qtsvfs, unity_package_installer

    def compress(data: bytes, *, mode: str, compression: int, store_size: bool) -> bytes:
        if (mode, compression, store_size) == ("high_compression", 12, False):
            return codec_backend.lz4_compress(data)
        return lz4.block.compress(data, mode=mode, compression=compression, store_size=store_size)

    bridge = SimpleNamespace(block=SimpleNamespace(
        compress=compress, decompress=codec_backend.lz4_decompress,
    ))
    for module in (installer, native_verify, qtsvfs, unity_package_installer):
        if getattr(module, "lz4", None) is lz4:
            module.lz4 = bridge


def _runtime_extension():
    import codec_backend

    if codec_backend.backend_name() == "native":
        import hok_codecs

        return hok_codecs
    return None


def _install_qts_readers(native) -> None:
    from wxq_patch import qtsvfs

    original_index = qtsvfs.parse_index
    if getattr(original_index, "_engine_hooks", False):
        return
    original_slots = qtsvfs.iter_chunk_slots
    original_extract = qtsvfs.QtsPackage.extract

    def parse_index(index_path):
        try:
            rows = native.qts_index(Path(index_path))
        except (OSError, ValueError):
            return original_index(index_path)
        return {row[0]: qtsvfs.IndexEntry(*row) for row in rows}

    def iter_slots(shard_path, *, include_reserved_variants=False):
        path = Path(shard_path)
        try:
            rows = native.qts_slots(path, bool(include_reserved_variants))
        except (OSError, ValueError):
            yield from original_slots(path, include_reserved_variants=include_reserved_variants)
            return
        for row in rows:
            yield qtsvfs.ChunkSlot(path, *row)

    def extract(self, file_hash, slots=None):
        entry = self.entries.get(file_hash)
        if entry is None:
            return original_extract(self, file_hash, slots)
        if slots is None:
            if self._slots is None:
                self._slots = self.build_slot_map()
            slots = self._slots
        try:
            chunks = {
                chunk_id: (slot.shard_path, slot.payload_offset,
                           slot.compressed_size, slot.uncompressed_size)
                for chunk_id, slot in slots.get(file_hash, {}).items()
            }
            return native.qts_extract(entry.compression, chunks)
        except (AttributeError, OSError, ValueError, OverflowError, TypeError):
            return original_extract(self, file_hash, slots)

    parse_index._engine_hooks = True
    qtsvfs.parse_index = parse_index
    qtsvfs.iter_chunk_slots = iter_slots
    if getattr(native, "qts_extract", None) is not None:
        extract._engine_hooks = True
        qtsvfs.QtsPackage.extract = extract
    if getattr(native, "qts_live_replacements", None) is not None:
        import qts_relocate

        qts_relocate.live_slot_replacements = native.qts_live_replacements


def _translate_table_hook(translate_table, protobuf_error):
    def translate(raw, asset, catalog, *, build_output=True):
        native = getattr(catalog, "_runtime_catalog", None)
        if native is not None:
            try:
                output, counts = native.translate(raw, asset, build_output)
                return output, Counter(counts)
            except (UnicodeError, OverflowError):
                # Let Python construct its UnicodeDecodeError from the exact field bytes.
                pass
            except ValueError as error:
                raise protobuf_error(str(error)) from None
        return translate_table(raw, asset, catalog, build_output=build_output)

    translate._engine_hooks = True
    return translate


def _load_catalog_hook(catalog_class, native_catalog):
    """`adaptive.load_catalog` with the catalog supplement and the language's glossary applied.

    The scanner calls `load_catalog` by its module name, so the hook replaces the runtime's own
    function rather than being called beside it. Before the glossary it merges `catalog_supplement`,
    the strings the game added after the catalog was built, so they obey the same glossary. The
    returned catalog carries `terminology`, the per-term count of changed targets, and `supplemented`,
    the number of strings added, for the run's log.
    """

    def load_catalog(folder: Path):
        import catalog_supplement
        import catalog_updates
        import terminology
        from languages import for_catalog

        with gzip.open(Path(folder) / "catalog.json.gz", "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        language = for_catalog(folder)
        added = catalog_supplement.apply(data, language.code)
        catalog_updates.admit_tables(data)
        changed = terminology.apply(data, language.terms)
        catalog_updates.apply(data, language.code)
        catalog = catalog_class(data)
        if native_catalog is not None:
            catalog._runtime_catalog = native_catalog(
                catalog.unique,
                [(*key, value) for key, value in catalog.context.items()],
                [(*key, value, catalog.english_sources[key]) for key, value in catalog.english_updates.items()],
            )
        catalog.terminology = changed
        catalog.supplemented = added
        return catalog

    load_catalog._engine_hooks = True
    return load_catalog


def _scan_hook(scan):
    def hooked(game: Path, assets: Path, work: Path, *, materialize=True):
        from languages import for_catalog
        from resource_tokens import expand_staged

        result = scan(game, assets, work, materialize=materialize)
        if materialize:
            expand_staged(result[0], _state["log"], for_catalog(assets).resource_terms)
        return result

    hooked._engine_hooks = True
    hooked.__wrapped__ = scan
    return hooked


def _receipt_root(game: Path) -> Path:
    return Path(_state["receipts"]) / game_id(game)


_receipt_root._engine_hooks = True
