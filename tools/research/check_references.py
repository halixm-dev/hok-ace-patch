"""Check that every repo path the docs, the staging docstring, the research tools and the build scripts name still exists.

A reference is a token in single or double backticks that reads as a repo path -- it has a ``/`` or
``\\`` separator and its first segment is a top-level entry of the repo -- or the target of a Markdown
link, which resolves against the linking file's own directory. Each must name a file or directory git
tracks (or an untracked file it does not ignore). A bare file name has no root to resolve against,
so it is not a reference; a renamed top-level doc is caught by ``RETIRED_NAMES``. Tokens with
placeholders (``<HASH>``, ``*``, ``{x}``), paths git ignores (build output, ``dist/``,
``artifacts/``, ``work/``, the patcher's data folder) and anything outside the repo are not
references. Fenced code blocks in Markdown are skipped.

A line that names an entry of ``RETIRED_NAMES`` fails too. Each docs move that
retires a name adds the old name here.

``.scratch/`` is work in flight -- its specs and tickets name the old and new homes on purpose -- so
it is not scanned.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\check_references.py

Exit code 0 means every reference resolves; otherwise one ``file:line: reason`` per failure is
printed. It imports nothing from ``app/`` or ``tools/``, and nothing imports it.
"""
from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]

# Names a docs move has retired: any mention of one in a scanned file is a failure.
RETIRED_NAMES: tuple[str, ...] = (
    "MEMORY.md", "docs/artifact-retention.md", "docs/compose", "docs/indonesian-translation-review.md",
    "tasks/", "terminology-glossary.md",
)

# Paths named on purpose while absent: an old name kept as history, a file inside a third-party
# archive, a script's output, a home created when first needed. Each goes once its mention does.
KNOWN_ABSENT: dict[str, str] = {
    "docs/agent-guide-untranslated-strings.md": "folded into the prime-rebuild record; named as history",
    "tools/apply_device_patch.sh": "the standalone-app record's problem statement describes the old layout",
    "docs/FTL.TXT": "a path inside the FreeType archive",
    "tools/research/career_atlas/preview_sheet.png": "written by tools/research/career_atlas/validate_assets.py",
    "tools/research/career_atlas/preview_in_context.png": "written by tools/research/career_atlas/validate_assets.py",
}

# Work in flight, which names old and new homes on purpose.
SKIPPED_ROOTS = (".scratch/",)

# Scanned besides every Markdown file: the staging entry point, the build scripts.
EXTRA_FILES = (
    "tools/build_device_patch.py",
    "app/build_exe.py",
    "build.bat",
    "setup.bat",
    "run.bat",
    "android/app/build.gradle.kts",
)
RESEARCH_DIR = "tools/research/"
RESEARCH_SUFFIXES = (".py", ".sh")

BACKTICK = re.compile(r"``(.+?)``|`([^`\n]+)`")
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```|~~~)")
PLACEHOLDER = re.compile(r"[<>*{}$%?\[\]|]|\.\.\.")
TRIM_CHARS = "\"'(),;"
LINE_SUFFIX = re.compile(r":[\d,-]+$")
REPEATED_SLASH = re.compile(r"/+")
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()


class Reference(NamedTuple):
    """One path a scanned file names: where, as written, and the repo path it must resolve to."""

    path: str
    line: int
    written: str
    target: str


def _git(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, input=stdin, capture_output=True,
                            text=True, encoding="utf-8", check=False)
    # check-ignore exits 1 when nothing is ignored; anything above that is git failing.
    if result.returncode > 1:
        raise SystemExit(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def _repo_files() -> list[str]:
    """Tracked files plus untracked ones git does not ignore, as posix paths."""
    listed = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    files = sorted({p for p in listed.split("\0") if p and (ROOT / p).is_file()})
    if not files:
        raise SystemExit("git lists no files: run from inside the repo")
    return files


def _known(files: list[str]) -> set[str]:
    """Every file and every directory above one."""
    known: set[str] = set()
    for path in files:
        known.add(path)
        parts = path.split("/")
        for i in range(1, len(parts)):
            known.add("/".join(parts[:i]))
    return known


def _ignored(paths: set[str]) -> set[str]:
    """The paths git ignores, by their own name or by a directory above them.

    A path that does not exist cannot tell git it is a directory, so each one and every ancestor is
    also asked with a trailing slash, which is what a ``build/`` pattern matches.
    """
    asked: dict[str, set[str]] = {}
    for path in paths:
        asked.setdefault(path, set()).add(path)
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            asked.setdefault("/".join(parts[:i]) + "/", set()).add(path)
    if not asked:
        return set()
    out = _git("check-ignore", "-z", "--no-index", "--stdin", stdin="\0".join(sorted(asked)) + "\0")
    return {path for name in out.split("\0") for path in asked.get(name, ())}


def _scanned(files: list[str]) -> list[str]:
    def wanted(path: str) -> bool:
        if path.startswith(SKIPPED_ROOTS):
            return False
        if path.endswith(".md") or path in EXTRA_FILES:
            return True
        return path.startswith(RESEARCH_DIR) and path.endswith(RESEARCH_SUFFIXES)
    return [p for p in files if wanted(p)]


def _clean(token: str) -> str | None:
    """A candidate path from one backticked piece, or None when it is not path-shaped."""
    token = token.strip(TRIM_CHARS).replace("\\", "/")
    if not token or PLACEHOLDER.search(token) or token.startswith(("/", "./", "../")) or "://" in token:
        return None
    token = REPEATED_SLASH.sub("/", LINE_SUFFIX.sub("", token.split("(", 1)[0]))
    return token.rstrip("/").rstrip(".:") or None


def _resolves(ref: Reference, known: set[str], suffixes: set[str]) -> bool:
    """A known path, a ``module.attribute`` reference to a known ``module.py``, or known absent."""
    if ref.target in known or ref.target in KNOWN_ABSENT:
        return True
    module, dot, attribute = ref.target.rpartition(".")
    return bool(dot) and "/" not in attribute and attribute.lower() not in suffixes \
        and f"{module}.py" in known


def _retired(name: str) -> re.Pattern[str]:
    """``name`` as a whole path word: ``tasks/`` must not match inside ``subtasks/``."""
    return re.compile(rf"(?<![\w.-]){re.escape(name)}")


def _references(path: str, text: str, roots: set[str]) -> list[Reference]:
    found: list[Reference] = []
    markdown = path.endswith(".md")
    fenced = False
    base = posixpath.dirname(path)
    for number, line in enumerate(text.splitlines(), 1):
        if markdown and FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in BACKTICK.finditer(line):
            for piece in (match.group(1) or match.group(2)).split():
                target = _clean(piece)
                if target and "/" in target and target.split("/")[0] in roots:
                    found.append(Reference(path, number, piece, target))
        if not markdown:
            continue
        for match in LINK.finditer(line):
            raw = match.group(1)
            if "://" in raw or raw.startswith(("#", "mailto:")):
                continue
            target = LINE_SUFFIX.sub("", unquote(raw.split("#", 1)[0]))
            if not target:
                continue
            if target.startswith("/"):
                resolved = posixpath.normpath(target.lstrip("/"))
            else:
                resolved = posixpath.normpath(posixpath.join(base, target))
            if not resolved.startswith(".."):
                found.append(Reference(path, number, raw, resolved))
    return found


def check() -> list[str]:
    files = _repo_files()
    known = _known(files)
    roots = {p.split("/")[0] for p in files}
    suffixes = {posixpath.splitext(p)[1].lstrip(".").lower() for p in files} - {""}
    retired = [(name, _retired(name)) for name in RETIRED_NAMES]
    failures: list[tuple[str, int, str]] = []
    pending: list[Reference] = []
    for path in _scanned(files):
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        pending += [r for r in _references(path, text, roots) if not _resolves(r, known, suffixes)]
        if path == SELF:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            failures += [(path, number, f"names retired {name!r}") for name, rx in retired if rx.search(line)]
    ignored = _ignored({r.target for r in pending})
    failures += [(r.path, r.line, f"missing path {r.written!r}") for r in pending if r.target not in ignored]
    return [f"{path}:{number}: {reason}" for path, number, reason in sorted(failures)]


def main() -> int:
    failures = check()
    for failure in failures:
        print(failure)
    if failures:
        print(f"{len(failures)} broken reference(s)")
        return 1
    print("all references resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
