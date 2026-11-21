"""Every hook this repo puts into the translation runtime, `wxq_patch.adaptive`, in one place.

The runtime ships as compiled bytecode from the PC patcher, so this repo changes what it does only by
replacing three of its module attributes. Each is looked up by name at call time (`adaptive._run`
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

`install()` is idempotent: a hook already in place is never wrapped twice, and a second PC install
only moves the receipts root. The PC hooks are taken only when the caller passes `receipts`, which
only a PC job does; a PC job runs in its own child process, so they never reach a mobile run.

Measured on the 2026-11-20 runtime: between `scan` and `commit` the engine records no hash of a
replacement file, only the source files' fingerprints; `commit` hashes the staged packages itself.
That is what makes rewriting the replacements after the scan safe.
"""
from __future__ import annotations

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
    """Put the hooks in place: `load_catalog` always, `scan` and `receipt_root` when <receipts> is given.

    <receipts> is the PC edition's receipts root, `<work>/pc/receipts`; each game's receipts go into
    `<receipts>/<game id>`. <log> takes the PC `scan` hook's one line per run.
    """
    from wxq_patch import adaptive

    if not getattr(adaptive.load_catalog, "_engine_hooks", False):
        adaptive.load_catalog = _load_catalog_hook(adaptive.Catalog)
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


def _load_catalog_hook(catalog_class):
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
