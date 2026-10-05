"""The languages a patch can install: the catalog each reads, and the terms its staged text expands to.

A catalog directory *is* its language. Each one holds a `catalog.json.gz` with the same schema and the
same tables, only the target strings differ, so the pipeline takes a catalog path and nothing else,
and everything language-specific is looked up from that path here.

Only the English catalog carries the full set of texture payloads. Another language's directory holds
just the payloads it re-draws, named exactly as the English ones are (`<HASH>.blocks` / `<HASH>.assets`,
plus `previews/<HASH>.png` for the review render). `payload_path` falls back to the English file for
every other edit, so a language starts from the English images and replaces them one at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from resource_tokens import RESOURCE_TOKENS


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    catalog: str  # directory name under the resources folder
    # What {Energy}/{LordExp}/{LordHp} expand to, in the word order the catalog itself uses.
    resource_terms: dict[str, str] = field(default_factory=dict)


ENGLISH = Language("en", "English", "catalog", dict(RESOURCE_TOKENS))
LANGUAGES: dict[str, Language] = {
    ENGLISH.code: ENGLISH,
    # The Indonesian catalog keeps the game's English terms but puts the head noun first: it writes
    # "EXP Chessplayer" 8 times and "HP Chessplayer" 3 times, never the English order.
    "id": Language("id", "Bahasa Indonesia", "catalog_id", {
        "{Energy}": "Energy",
        "{LordExp}": "EXP Chessplayer",
        "{LordHp}": "HP Chessplayer",
    }),
}
DEFAULT_LANGUAGE = ENGLISH.code


def get(code: str) -> Language:
    """The language for <code>; raises ValueError for one this patcher does not ship."""
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"unknown language {code!r}; expected one of {', '.join(LANGUAGES)}") from None


def catalog_dir(resources: Path, code: str) -> Path:
    """The catalog directory for <code> under <resources> (the folder holding `catalog/`)."""
    return Path(resources) / get(code).catalog


def for_catalog(catalog: Path) -> Language:
    """The language a catalog directory holds, by its name; an unrecognised name reads as English."""
    name = Path(catalog).name
    return next((language for language in LANGUAGES.values() if language.catalog == name), ENGLISH)


def payload_path(catalog: Path, name: str) -> Path:
    """<catalog>'s own copy of payload <name>, or the English catalog's beside it when it has none."""
    own = Path(catalog) / name
    if own.exists():
        return own
    fallback = Path(catalog).parent / ENGLISH.catalog / name
    return fallback if fallback.exists() else own
