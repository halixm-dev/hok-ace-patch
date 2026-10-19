"""Check that both patchers show only strings the shared strings file holds, in both languages.

``resources/ui/strings.json`` is the one vocabulary of the Windows patcher and the Android patcher. This
reads the file and the patchers' sources as text (nothing is imported or built) and fails when:

- a key lacks English or Indonesian, names an unknown platform, or its two languages carry different
  ``{name}`` placeholders, or two Android keys share an English text but not its Indonesian;
- the Android patcher shows a literal the file has no English for. Literals are taken from the calls that
  put text on screen (``ui``, ``text``, ``button``, ``eyebrow``, ``message``, ``show``, ``technicalButton``,
  ``UiText.text`` and ``UiText.progress``). A literal with no capital letter, digit or space is a tag or an
  action key, and a literal with a ``$`` template is composed of checked parts; both are skipped;
- either patcher looks a key up that the file lacks, or for another platform, or fills placeholders the
  string does not have: ``UiText.string(context, "key", "name" to value)`` and ``template(code, "key", ...)``
  on Android, ``ui_text("key", name=value)`` on Windows.

Text that reaches the screen through a variable (worker progress lines, update-check results, installer
errors) is not seen here; ``AppUpdateCheckerTest`` and ``InterfaceProbeTest`` cover the ones that matter.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\check_ui_strings.py

Exit code 0 means both patchers are on the file; otherwise one line per failure is printed. It imports
nothing from ``app/`` or ``tools/``, and nothing imports it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRINGS = ROOT / "resources" / "ui" / "strings.json"
ANDROID = ROOT / "android" / "app" / "src" / "main" / "java"
WINDOWS = ROOT / "app" / "hok_patcher.py"

LANGUAGES = ("en", "id")
PLATFORMS = {"android", "windows"}
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# A Kotlin string literal without templates or nested quotes.
LITERAL = re.compile(r'"((?:[^"\\$]|\\.)*)"')
ANDROID_SINKS = re.compile(r"(?<![\w.])(?:ui|text|button|eyebrow|message|show|technicalButton)\(|"
                           r"\bUiText\.(?:text|progress)\(")
ANDROID_LOOKUPS = re.compile(r"\b(?:UiText\.string|string|template)\(\s*[^,()]+,\s*\"(\w+)\"")
WINDOWS_LOOKUPS = re.compile(r"\bui_text\(\s*[\"'](\w+)[\"']")


def _arguments(source: str, start: int) -> str:
    """The text between the parenthesis that opens at <start> - 1 and the one that closes it."""
    depth, index, quoted = 1, start, False
    while index < len(source) and depth:
        char = source[index]
        if quoted:
            if char == "\\":
                index += 1
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    return source[start:index - 1]


def _unescape(literal: str) -> str:
    return re.sub(r"\\(.)", lambda match: {"n": "\n", "t": "\t"}.get(match.group(1), match.group(1)), literal)


def _shown(literal: str) -> bool:
    return bool(literal) and (" " in literal or bool(re.search(r"[A-Z0-9]", literal)))


def _check_file(strings: dict) -> list[str]:
    failures = []
    # The Android patcher finds a key by its English, so one English text has one Indonesian.
    seen: dict[str, str] = {}
    for key, entry in strings.items():
        if "android" in entry.get("platforms", []):
            other = seen.setdefault(entry.get("en", ""), key)
            if other != key and strings[other].get("id") != entry.get("id"):
                failures.append(f"{key}: same English as {other} but different Indonesian")
        for language in LANGUAGES:
            if not entry.get(language):
                failures.append(f"{key}: no {language}")
        unknown = set(entry.get("platforms", [])) - PLATFORMS
        if unknown or not entry.get("platforms"):
            failures.append(f"{key}: platforms {sorted(unknown) or 'missing'}")
        names = [set(PLACEHOLDER.findall(entry.get(language, ""))) for language in LANGUAGES]
        if names[0] != names[1]:
            failures.append(f"{key}: placeholders differ, en {sorted(names[0])}, id {sorted(names[1])}")
    return failures


def _check_lookup(strings: dict, platform: str, where: str, key: str, filled: set[str]) -> list[str]:
    entry = strings.get(key)
    if entry is None:
        return [f"{where}: key {key!r} is not in the strings file"]
    failures = []
    if platform not in entry.get("platforms", []):
        failures.append(f"{where}: key {key!r} is not marked for {platform}")
    wanted = set(PLACEHOLDER.findall(entry["en"]))
    if filled != wanted:
        failures.append(f"{where}: key {key!r} fills {sorted(filled)}, the string has {sorted(wanted)}")
    return failures


def _check_android(strings: dict) -> list[str]:
    english = {entry["en"]: key for key, entry in strings.items() if "android" in entry.get("platforms", [])}
    failures = []
    for path in sorted(ANDROID.rglob("*.kt")):
        source = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()
        for match in ANDROID_SINKS.finditer(source):
            # Join "a " + "b" across lines before reading the literals.
            arguments = re.sub(r'(?<!\\)"\s*\+\s*"', "", _arguments(source, match.end()))
            for literal in LITERAL.findall(arguments):
                text = _unescape(literal)
                if _shown(text) and text not in english:
                    line = source.count("\n", 0, match.start()) + 1
                    failures.append(f"{name}:{line}: {text!r} is not in the strings file")
        for match in ANDROID_LOOKUPS.finditer(source):
            call = _arguments(source, source.index("(", match.start()) + 1)
            filled = set(re.findall(r'"(\w+)"\s+to\b', call))
            line = source.count("\n", 0, match.start()) + 1
            failures += _check_lookup(strings, "android", f"{name}:{line}", match.group(1), filled)
    return sorted(set(failures))


def _check_windows(strings: dict) -> list[str]:
    source = WINDOWS.read_text(encoding="utf-8")
    failures = []
    for match in WINDOWS_LOOKUPS.finditer(source):
        call = _arguments(source, source.index("(", match.start()) + 1)
        filled = set(re.findall(r"\b(\w+)\s*=", call))
        line = source.count("\n", 0, match.start()) + 1
        failures += _check_lookup(strings, "windows", f"app/hok_patcher.py:{line}", match.group(1), filled)
    return failures


def main() -> int:
    data = json.loads(STRINGS.read_text(encoding="utf-8"))
    if list(data.get("languages", [])) != list(LANGUAGES):
        print(f"strings.json: languages are {data.get('languages')}, expected {list(LANGUAGES)}")
        return 1
    strings = data["strings"]
    failures = _check_file(strings) + _check_android(strings) + _check_windows(strings)
    for failure in failures:
        print(failure)
    if not failures:
        print(f"OK: {len(strings)} strings, each in {' and '.join(LANGUAGES)}; both patchers resolve to them.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
