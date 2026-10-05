"""Shared table and texture result counters for the desktop and Android workflows."""
from __future__ import annotations

def count_translated(summary: dict) -> tuple[int, int]:
    """(text tables, textures) written by build_patch.

    A rebuilt package holds both kinds and its `replacement_count` covers both, so it carries the
    texture share in `textures`; classifying it by mode alone would report package 1's tables as
    images, or package 1050016095's images as tables. A package the append pass added to carries the
    same split for the same reason.
    """
    text = images = 0
    for package in summary.get("packages", []):
        count = package["stage_report"]["replacement_count"]
        if package.get("mode") == "graphics":
            images += count
        elif package.get("mode") in ("rebuilt", "added-from-apk"):
            textures = package.get("textures", 0)
            images += textures
            text += count - textures
        else:
            text += count
    return text, images


def count_untranslated_graphics(summary: dict) -> int:
    """Textures the run found but could not translate, so they stay in Chinese.

    These live in build_patch's separate `graphics_skipped` list, not in `packages`: a package whose
    every texture was skipped writes no directory, and the installer pushes by directory. The append
    pass reports the textures it could not add the same way, in `append_skipped` — where a package that
    got some of its assets can also appear, naming the share that stays Chinese.
    """
    return (sum(entry.get("skipped_count", 0) for entry in summary.get("graphics_skipped", []))
            + sum(entry.get("textures", 0) for entry in summary.get("append_skipped", [])))


def count_untranslated_text(summary: dict) -> int:
    """Text tables the run translated but could not apply, so they stay in Chinese.

    These live in build_patch's `text_skipped` list. A package that loses tables can still have an
    output directory behind it — and one that loses all of them has none — so `packages` alone
    cannot say what did not make it. The append pass reports the tables it could not add in
    `append_skipped`; its entries count both kinds, so the tables are what is left after `textures`.
    That list carries the same two shapes, a package the pass could not add to at all and the refused
    share of one it did add to.
    """
    return (sum(entry.get("dropped_count", 0) for entry in summary.get("text_skipped", []))
            + sum(entry.get("assets", 0) - entry.get("textures", 0)
                  for entry in summary.get("append_skipped", [])))
