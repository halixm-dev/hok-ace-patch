"""Drive `pc_edition.run` through a whole PC sequence on a scratch copy of the PC edition, in each language.

Run from the project root, against a **copy** of the game (never the installed one), with the game and
its launcher closed (the jobs' process guard refuses otherwise):

    .venv\\Scripts\\python.exe tools\\research\\check_pc_install.py --game <scratch copy> --work <dir>

The copy must start untranslated (Check says *not installed*). For each order of the two languages
(`en` then `id`, then `id` then `en`) it runs:

    install A -> check -> install A -> install B -> check -> restore

and fails when any of these does not hold:

- restore returns every package file to the bytes it had at the start (SHA-256 of every file under
  `WXQ_Data\\Package\\builtin`);
- the second install of A changes no package file;
- installing B goes through the receipts: the engine restores, then installs, in that one job;
- `<work>\\replacements\\` is empty whenever the engine starts an install or a scan;
- `LocalFileList.json` keeps its bytes, and every file it lists keeps its listed size (ADR 0011);
- Check answers *installed* in the language just installed, and *not installed* after restore.

The engine also deletes the launcher's QtsVFS watchdog ledgers (`QtsDataFolder\\QtsVFSCache\\Watchdog`,
unlisted; the launcher rebuilds them), so those are left out of the byte comparison. Exit code 0 means
every step held; each failure is printed. Writes only into <game> and <work>.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

import pc_edition  # noqa: E402

BUILTIN = Path("WXQ_Data") / "Package" / "builtin"
MANIFEST = "LocalFileList.json"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def packages(game: Path) -> dict[str, str]:
    """SHA-256 of every file under `builtin`, by path relative to <game>."""
    root = game / BUILTIN
    return {str(path.relative_to(game)): _sha(path) for path in sorted(root.rglob("*")) if path.is_file()}


def launcher_list(game: Path, original: bytes) -> list[str]:
    """Failures of the launcher list: its own bytes, and the size of every file it lists."""
    failures = []
    data = (game / MANIFEST).read_bytes()
    if data != original:
        failures.append(f"{MANIFEST} changed")
    for entry in json.loads(data.decode("utf-8-sig")):
        path = game / entry["file"]
        if path.is_file() and path.stat().st_size != int(entry["file_size"]):
            failures.append(f"{entry['file']} is {path.stat().st_size} bytes, listed {entry['file_size']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=Path, required=True, help="a scratch copy of the PC edition")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--orders", default="en:id,id:en", help="language pairs A:B, comma-separated")
    args = parser.parse_args()
    game, work = pc_edition.resolve(args.game), args.work

    failures: list[str] = []
    calls: list[str] = []
    engine = pc_edition._engine

    def watched(action, game_root, catalog, work_dir):
        if action in ("install", "status"):
            leftover = list((Path(work_dir) / "replacements").iterdir())
            if leftover:
                failures.append(f"{action}: replacements holds {len(leftover)} entries as the engine starts")
        calls.append(action)
        return engine(action, game_root, catalog, work_dir)

    pc_edition._engine = watched
    log = lambda line: print("    " + line)  # noqa: E731

    def job(action: str, language: str) -> dict:
        calls.clear()
        started = time.perf_counter()
        answer = pc_edition.run(action, game, work, language, log=log)
        print(f"  {action} {language}: {answer['state']} in {time.perf_counter() - started:.1f} s, engine {calls}")
        return answer

    def expect(answer: dict, state: str, language: str | None, step: str) -> None:
        if answer["state"] != state or (language and answer.get("language") != language):
            failures.append(f"{step}: Check says {answer['state']} {answer.get('language')}, expected {state} {language}")

    original_list = (game / MANIFEST).read_bytes()
    print("hashing the packages")
    pristine = packages(game)
    first = job("status", "en")
    expect(first, pc_edition.NOT_INSTALLED, None, "start")
    if first["state"] != pc_edition.NOT_INSTALLED:
        print("the copy is not untranslated; restore it or make a fresh copy")
        return 1

    for order in args.orders.split(","):
        a, b = order.split(":")
        print(f"order {a} then {b}")
        job("install", a)
        failures += [f"install {a}: {item}" for item in launcher_list(game, original_list)]
        expect(job("status", a), pc_edition.INSTALLED, a, f"check after install {a}")
        before = packages(game)
        job("install", a)
        after = packages(game)
        changed = sorted(name for name in before if before[name] != after.get(name))
        if changed:
            failures.append(f"second install {a} changed {changed}")
        job("install", b)
        if calls[:1] != ["restore"] or "install" not in calls:
            failures.append(f"install {b} over {a}: engine calls {calls}, expected a restore, then an install")
        failures += [f"install {b}: {item}" for item in launcher_list(game, original_list)]
        expect(job("status", b), pc_edition.INSTALLED, b, f"check after switching to {b}")
        job("restore", b)
        restored = packages(game)
        differ = sorted(name for name in pristine if pristine[name] != restored.get(name))
        if differ or set(restored) != set(pristine):
            failures.append(f"restore after {a} then {b}: {len(differ)} files differ from the start {differ[:5]}, "
                            f"{sorted(set(restored) ^ set(pristine))[:5]} added or removed")
        failures += [f"restore: {item}" for item in launcher_list(game, original_list)]
        expect(job("status", a), pc_edition.NOT_INSTALLED, None, f"check after restore ({a} then {b})")

    for failure in failures:
        print("FAIL", failure)
    print("OK" if not failures else f"{len(failures)} failures")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
