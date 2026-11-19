"""The shared interface strings (resources/ui/strings.json) and the user-facing PatchError.

Moved verbatim out of `patcher_core`, which re-exports every name here. Imported after `patcher_core`
puts `tools/` on the path, for `languages`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import languages

# As `patcher_core.BUNDLE`: the PyInstaller bundle, or the repository's resources/ from source.
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1] / "resources"))


UI_STRINGS = json.loads((BUNDLE / "ui" / "strings.json").read_text(encoding="utf-8"))["strings"]
# The language choice in ① also sets the interface language (DESIGN.md, Wording and language).
_interface_language = languages.DEFAULT_LANGUAGE


def set_interface_language(code: str) -> None:
    global _interface_language
    _interface_language = languages.get(code).code


def _render(key: str, language: str, values: dict[str, object]) -> str:
    text = UI_STRINGS[key][language]
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def ui_text(key: str, **values: object) -> str:
    """The shared interface string <key> (resources/ui/strings.json) in the interface language."""
    return _render(key, _interface_language, values)


class PatchError(Exception):
    """Expected failure meant for the user: shared strings <keys>, joined by blank lines.

    ``str()`` is the English text, for the log, which stays raw; ``shown()`` is the interface language.
    """

    def __init__(self, *keys: str, **values: object) -> None:
        self.keys, self.values = keys, values
        super().__init__(self._text("en"))

    def _text(self, language: str) -> str:
        return "\n\n".join(_render(key, language, self.values) for key in self.keys)

    def shown(self) -> str:
        return self._text(_interface_language)
