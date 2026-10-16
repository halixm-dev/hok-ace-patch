"""Give one Chinese game term one translation everywhere: the catalog's glossary, applied as it loads.

The catalog was translated string by string, so a keyword reads differently from card to card: `夺取`
(the Steal keyword, link `href=200`) is mostly "Steal" but also "Plunder", "Seizure", "Capture",
"Snatch", "Siphon" or "drain", and `整备` (the Prepare keyword, `href=11`) is mostly "Prepare" but also
"Ready", "Readiness" or "Maintenance". The glossary keeps the default names, Steal and Prepare; Plunder
and Readiness are the unofficial community translation's. The catalog is
the PC pipeline's file and is not edited here, so the correction is made in memory: `install` wraps
`adaptive.load_catalog`, and every pass — the scanner, which loads the catalog itself, the prime append,
the texture and extra-text passes — reads the corrected strings.

A rule is keyed on the **Chinese** source, not on the English: it rewrites a target only when its
source contains the term, so "steal" in a line of dialogue that never says `夺取` is left alone. Within
such a target it rewrites only the measured variant words, never inside a `{placeholder}` or a
`<tag>` (translate_table compares both against the source), and never a phrase listed in `keep`,
which another word of the same source owns (`摄灵` is "Soul Snatch" inside a `夺取` string).
"""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Markup and placeholders the client and translate_table read; a rule never rewrites inside one.
_PROTECTED = re.compile(r"(\{[^{}]*\}|<[^<>]*>)")


def _after_icon(match: re.Match) -> bool:
    """True when <match> follows a keyword icon: the client draws each keyword's icon as a box-drawing
    glyph (`╊` Steal, `╬` Prepare) just before its name, which is a name and keeps its capital."""
    return match.start() > 0 and "─" <= match.string[match.start() - 1] <= "╿"


@dataclass(frozen=True)
class Term:
    """One Chinese term and the English it always reads as.

    <variants> are (regex, replacement) pairs tried in order on every unprotected run of a target
    whose source contains <source>. A pattern that names a group `w` copies that word's case onto the
    replacement ("drains" -> "steals", "Seizure" -> "Steal"), unless <proper> is set, in which case the
    term is a name and keeps its capital everywhere; a pattern without one is a phrase fix whose
    replacement is written as given. <keep> lists English phrases that translate a different word of
    the same source and must survive the rewrite.
    """

    source: str
    canonical: str
    variants: tuple[tuple[str, str], ...]
    keep: tuple[str, ...] = ()
    proper: bool = False
    _compiled: tuple = field(init=False, repr=False, compare=False)
    _protected: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", tuple(
            (re.compile(pattern), replacement) for pattern, replacement in self.variants))
        kept = "".join(f"|{re.escape(phrase)}" for phrase in self.keep)
        object.__setattr__(self, "_protected", re.compile(f"({_PROTECTED.pattern[1:-1]}{kept})"))

    def rewrite(self, source: str, target: str) -> str:
        """<target> with this term's variants replaced, or <target> itself when <source> lacks the term."""
        if self.source not in source or not target:
            return target
        parts = self._protected.split(target)
        for index in range(0, len(parts), 2):  # odd indices are tags, placeholders and kept phrases
            text = parts[index]
            for pattern, replacement in self._compiled:
                text = pattern.sub(lambda match, r=replacement: self._cased(match, r), text)
            parts[index] = text
        return "".join(parts)

    def _cased(self, match: re.Match, replacement: str) -> str:
        word = match.groupdict().get("w")
        if word is None or self.proper or word[:1].isupper() or _after_icon(match):
            return replacement
        return replacement[:1].lower() + replacement[1:]


ENGLISH_TERMS: tuple[Term, ...] = (
    # 夺取: take Levels from another Hero. "Steal" is the default name (the link label reads it 7 times
    # in 11); "Plunder" is the community translation's. `掠夺` is a different word and keeps its own
    # "Plunder" ("Plunder Blade"). "Soul Snatch" is `摄灵`, a different keyword drawn with the same
    # glyph, so it is kept.
    Term("夺取", "Steal", (
        (r"(?i:\bto capture\b)", "Steal"),  # "triggers to capture": the keyword, mistranslated
        (r"(?i:\bcapturing the entry\b)", "Steal Trait"),
        (r"(?i:\bsteal the blessing\b)", "Steal Blessing"),  # 夺取祝福
        (r"(?i:\bto steal reinforcements\b)", "Steal Reinforcements"),  # 1张夺取援兵
        (r"\bCaptureCard\b", "Steal Card"),
        (r"(?P<w>\b(?i:plunder|captur|snatch|siphon|drain)ing\b)", "Stealing"),
        (r"(?P<w>\b(?i:plundered|seized|captured|snatched|siphoned|drained)\b)", "Stolen"),
        (r"(?P<w>\b(?i:plunders|captures|snatches|siphons|drains)\b)", "Steals"),
        (r"(?P<w>\b(?i:plunder|capture|seizure|snatch|siphon|drain)\b)", "Steal"),
    ), keep=("Soul Snatch", "soul snatch")),
    # 整备: a Hero's effect that triggers at the start of each Round. "Prepare" is the default name (45
    # of the link's 55 labels); "Readiness" is the community translation's. It is a keyword, so it
    # keeps its capital.
    Term("整备", "Prepare", (
        (r"(?P<w>\b(?i:readiness|maintenance)\b)", "Prepare"),
        (r"(?P<w>\bReady\b)", "Prepare"),
        (r"\bPrepare series\b", "Prepare Series"),
    ), proper=True),
)

# The Indonesian catalog keeps the game's keywords in English ("Seri Steal", "Efek Prepare"), with the
# same variants, so it takes the English glossary plus its own two misreadings of `夺取`: "Kejang"
# (Seizure, in its medical sense) and "PIunder", Plunder spelled with a capital I.
INDONESIAN_TERMS: tuple[Term, ...] = ENGLISH_TERMS + (
    Term("夺取", "Steal", (
        (r"\bKejang\b", "Steal"),
        (r"\bPIunder\b", "Steal"),
    )),
)


def apply(data: dict, terms: tuple[Term, ...]) -> Counter:
    """Apply <terms> to a loaded `catalog.json.gz` in place; returns the targets changed, per canonical term.

    Covers the two places a translation comes from: `unique` (Chinese -> English) and the
    `english_updates` rows that carry their Chinese source (index 4), which re-translate records the
    game ships in English. `contextual` rows carry no source a rule can be keyed on.
    """
    changed: Counter = Counter()

    def rewrite(source: str, target: str) -> str:
        for term in terms:
            new = term.rewrite(source, target)
            if new != target:
                changed[term.canonical] += 1
            target = new
        return target

    if terms:
        unique = data.get("unique", {})
        for source, target in unique.items():
            unique[source] = rewrite(source, target)
        for row in data.get("english_updates", []):
            if len(row) >= 5:
                row[3] = rewrite(row[4], row[3])
    return changed


def install() -> None:
    """Make `adaptive.load_catalog` return the catalog with its language's glossary applied.

    Idempotent. The scanner calls `load_catalog` by its module name, so the wrapper has to replace the
    runtime's own function rather than be called beside it. The returned catalog carries
    `terminology`, the per-term count of changed targets, for the run's log.
    """
    from wxq_patch import adaptive

    if getattr(adaptive.load_catalog, "_terminology", False):
        return

    def load_catalog(folder: Path):
        from languages import for_catalog

        with gzip.open(Path(folder) / "catalog.json.gz", "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        changed = apply(data, for_catalog(folder).terms)
        catalog = adaptive.Catalog(data)
        catalog.terminology = changed
        return catalog

    load_catalog._terminology = True
    adaptive.load_catalog = load_catalog
