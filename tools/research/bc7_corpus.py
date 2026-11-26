"""Capture, replay and time the PC edition's hand-written BC7 modes (`tools/bc7_mode6.py`).

Tickets `.scratch/pc-bc7-rust/` (mode 7) and `.scratch/pc-bc7-search/` (modes 6, 5 and 4). Run from
the project root, against a **copy** of the PC edition (packages `0 1 10 15 19`,
`LocalFileList.json`, `WXQ.exe`), never the installed game:

    .venv\\Scripts\\python.exe tools\\research\\bc7_corpus.py capture --game <copy> --work <dir>
    .venv\\Scripts\\python.exe tools\\research\\bc7_corpus.py synthetic --work <dir>
    .venv\\Scripts\\python.exe tools\\research\\bc7_corpus.py replay --work <dir> [--backend python|native] [--final]
    .venv\\Scripts\\python.exe tools\\research\\bc7_corpus.py time-build --game <copy> --work <dir> \\
        [--languages en id] [--runs 3] [--encoder python|native]

``capture`` runs one instrumented cold `pc_catalog.build` per language with the Python encoder, each
in a fresh work folder, and records every block `encode_block` searched past etcpak, with the atlas
being ported. ``synthetic`` adds the hand-made cases: blank, solid, transparent colored pixels, alpha
edges and tied partition scores, plus seeded random blocks. Each record holds the 64 input bytes, the
final `encode_block` bytes, then for each of `MODES` the Python reference's block and its decoded
RGBA (`<work>/corpus/<name>.bin`, `RECORD` bytes each, with `<name>.json` beside it).

``replay`` re-encodes every record's input in every mode with the chosen backend and fails on the
first block or decoded pixel that differs; with ``--final`` it also compares `encode_block`'s bytes.
It then times `encode_block` over each corpus. ``time-build`` runs the unprofiled cold builds, each in
its own process and fresh work folder, then one warm re-run per language, and prints the medians.
Capture overhead never enters a timing. Writes only under <work>.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import bc7_mode6  # noqa: E402

MODES = ((6, 0), (5, 0), (4, 0), (4, 1), (7, 0))  # (mode, index mode), in `ENCODERS` order
MODE_BYTES = 16 + 64  # one mode's block and its decoded RGBA
RECORD = 64 + 16 + MODE_BYTES * len(MODES)  # input, final encode_block bytes, then each mode


def _pixels(raw: bytes) -> list[tuple[int, int, int, int]]:
    return [tuple(raw[i:i + 4]) for i in range(0, 64, 4)]


def _use(backend: str) -> None:
    """Make `encode_block` search with <backend> from here on, counters reset."""
    bc7_mode6._BACKEND.clear()
    os.environ[bc7_mode6.ENCODER_ENV] = backend
    for counter in (bc7_mode6.SEARCH_CALLS, bc7_mode6.MODE7_CALLS):
        for key in counter:
            counter[key] = 0
    bc7_mode6.backend_name()


def _record(raw: bytes, final: bytes | None = None) -> bytes:
    """One corpus record for 64 input bytes, from the Python reference."""
    if final is None:
        _use("python")
        final = bc7_mode6.encode_block(_pixels(raw))
    reference = bc7_mode6.mode_backend("python")
    return raw + final + b"".join(b"".join(reference(raw, mode, index_mode)) for mode, index_mode in MODES)


def _modes(record: bytes) -> list[tuple[bytes, bytes]]:
    """A record's per-mode ``(block, decoded RGBA)``, in `MODES` order."""
    out = []
    for n in range(len(MODES)):
        at = 80 + n * MODE_BYTES
        out.append((record[at:at + 16], record[at + 16:at + MODE_BYTES]))
    return out


def _environment() -> dict:
    import etcpak  # noqa: F401
    import texture2ddecoder  # noqa: F401
    from importlib.metadata import version

    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "cpu": platform.processor(), "cpus": os.cpu_count(),
            "etcpak": version("etcpak"), "texture2ddecoder": version("texture2ddecoder"),
            "patcher": (ROOT / "VERSION").read_text(encoding="utf-8").strip()}


def _game_version(game: Path) -> str | None:
    """The launcher list's version field, if it carries one."""
    try:
        data = json.loads((game / "LocalFileList.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    for key in ("version", "Version", "resVersion", "ResVersion"):
        if isinstance(data, dict) and key in data:
            return str(data[key])
    return None


def _write(work: Path, name: str, records: list[bytes], meta: dict) -> None:
    folder = work / "corpus"
    folder.mkdir(parents=True, exist_ok=True)
    blob = b"".join(records)
    (folder / f"{name}.bin").write_bytes(blob)
    meta = {**meta, "records": len(records), "record_bytes": RECORD, "modes": MODES,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "inputs_sha256": hashlib.sha256(b"".join(r[:64] for r in records)).hexdigest(),
            "finals_sha256": hashlib.sha256(b"".join(r[64:80] for r in records)).hexdigest()}
    (folder / f"{name}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{name}: {len(records)} records, sha256 {meta['sha256'][:16]}")


def capture(game: Path, work: Path, languages: list[str]) -> None:
    import mobile_graphics as mg
    import pc_catalog

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    current = {"atlas": None}

    def tracking(function, hash_of):
        def wrapper(*args, **kwargs):
            current["atlas"] = hash_of(args)
            try:
                return function(*args, **kwargs)
            finally:
                current["atlas"] = None
        return wrapper

    mg.port_atlas = tracking(mg.port_atlas, lambda args: str(args[1]["hash"]).upper())
    mg.label_atlas = tracking(mg.label_atlas, lambda args: str(args[1]).upper())

    for language in languages:
        seen: list[tuple[bytes, bytes, str | None]] = []
        calls = {"encode_block": 0, "searched": 0, "mode7": 0}
        reference_encode = bc7_mode6.encode_block

        def encode_block(pixels):
            calls["encode_block"] += 1
            searched, mode7 = bc7_mode6.SEARCH_CALLS["python"], bc7_mode6.MODE7_CALLS["python"]
            final = reference_encode(pixels)
            if bc7_mode6.SEARCH_CALLS["python"] > searched:
                calls["searched"] += 1
                calls["mode7"] += bc7_mode6.MODE7_CALLS["python"] - mode7
                seen.append((bytes(c for p in pixels for c in p), final, current["atlas"]))
            return final

        _use("python")
        bc7_mode6.encode_block = encode_block
        try:
            build_work = work / f"capture-{language}"
            if build_work.exists():
                raise SystemExit(f"{build_work} exists; capture needs a fresh work folder")
            pc_catalog.build(game, ROOT / "resources", language, build_work, version=version)
        finally:
            bc7_mode6.encode_block = reference_encode
        records, atlases = [], {}
        kept = {f"{m}/{i}": 0 for m, i in MODES}
        kept["etcpak"] = 0
        for raw, final, atlas in seen:
            record = _record(raw, final)
            records.append(record)
            winner = next((f"{m}/{i}" for (m, i), (block, _) in zip(MODES, _modes(record)) if block == final),
                          "etcpak")
            kept[winner] += 1
            atlases[atlas or "?"] = atlases.get(atlas or "?", 0) + 1
        distinct = len({r[:64] for r in records})
        _write(work, f"game-{language}", records,
               {"language": language, "game": str(game), "game_version": _game_version(game),
                "atlas_blocks": atlases, "calls": calls, "kept": kept, "distinct_inputs": distinct,
                "environment": _environment()})


def _synthetic_inputs(seed: int = 7, random_blocks: int = 2000) -> list[bytes]:
    """Hand-made edge cases, then seeded random blocks of the kinds labels are made of."""
    cases: list[list[tuple[int, int, int, int]]] = [
        [(0, 0, 0, 0)] * 16,  # blank
        [(255, 255, 255, 255)] * 16,
        [(200, 100, 50, 255)] * 16,  # solid
        [(255, 0, 255, 0)] * 16,  # transparent but colored
        [(17, 200, 33, i * 17) for i in range(16)],  # alpha ramp
        [(255, 255, 255, 255 if i % 4 < 2 else 0) for i in range(16)],  # alpha edge, vertical
        [(255, 255, 255, 255 if i < 8 else 0) for i in range(16)],  # alpha edge, horizontal
        [(255, 0, 0, 255) if i % 2 else (0, 0, 255, 255) for i in range(16)],  # checker columns: ties
        [(255, 0, 0, 255) if (i // 4 + i) % 2 else (0, 255, 0, 255) for i in range(16)],  # checker
        [(0, 0, 0, 255)] * 8 + [(255, 255, 255, 255)] * 8,  # two halves: several partitions tie at zero
        [(i * 16, 255 - i * 16, 128, 255) for i in range(16)],  # gradient
        [(255, 255, 255, a) for a in (0, 0, 40, 200, 0, 30, 220, 255, 10, 180, 255, 255, 120, 255, 255, 255)],
        [(240, 200, 120, 255) if i in (5, 6, 9, 10) else (240, 200, 120, 3) for i in range(16)],
    ]
    rng = random.Random(seed)
    for n in range(random_blocks):
        kind = n % 4
        if kind == 0:  # anything
            pixels = [tuple(rng.randrange(256) for _ in range(4)) for _ in range(16)]
        elif kind == 1:  # two colors split by a random mask, antialiased alpha
            a, b = (tuple(rng.randrange(256) for _ in range(3)) for _ in range(2))
            mask = rng.randrange(1 << 16)
            pixels = [(*(b if mask >> i & 1 else a), rng.choice((0, 255, rng.randrange(256))))
                      for i in range(16)]
        elif kind == 2:  # white glyph edge over transparency
            pixels = [(255, 255, 255, rng.choice((0, 0, 255, 255, rng.randrange(256)))) for _ in range(16)]
        else:  # few distinct values, so partition scores tie
            palette = [tuple(rng.randrange(0, 256, 85) for _ in range(4)) for _ in range(2)]
            pixels = [rng.choice(palette) for _ in range(16)]
        cases.append(pixels)
    return [bytes(c for p in pixels for c in p) for pixels in cases]


def synthetic(work: Path) -> None:
    records = [_record(raw) for raw in _synthetic_inputs()]
    _write(work, "synthetic", records, {"seed": 7, "environment": _environment()})


def _corpora(work: Path) -> list[tuple[str, bytes]]:
    return [(path.stem, path.read_bytes()) for path in sorted((work / "corpus").glob("*.bin"))]


def replay(work: Path, backend: str, final: bool = False) -> int:
    """Parity on every record in every mode (and, with <final>, `encode_block`'s bytes), then
    `encode_block` timed over each corpus."""
    encode = bc7_mode6.mode_backend(backend)
    _use(backend)
    failures = 0
    for name, blob in _corpora(work):
        if len(blob) % RECORD:
            print(f"{name}: {len(blob)} bytes is not a whole number of {RECORD}-byte records")
            return 1
        count = len(blob) // RECORD
        for n in range(count):
            record = blob[n * RECORD:(n + 1) * RECORD]
            raw = record[:64]
            for (mode, index_mode), want in zip(MODES, _modes(record)):
                got = encode(raw, mode, index_mode)
                if got != want:
                    part = "block" if got[0] != want[0] else "decoded pixels"
                    print(f"MISMATCH {name}[{n}] mode {mode}/{index_mode} {part}: input {raw.hex()} "
                          f"expected {want[0].hex()} got {got[0].hex()}")
                    failures += 1
                    if failures >= 5:
                        return 1
            if final and bc7_mode6.encode_block(_pixels(raw)) != record[64:80]:
                print(f"FINAL MISMATCH {name}[{n}] input {raw.hex()}")
                failures += 1
        print(f"{name}: {count} records x {len(MODES)} modes, {backend} "
              f"{'matches' if not failures else 'DIFFERS'}"
              + (f"; encode_block matches, searched {dict(bc7_mode6.SEARCH_CALLS)}, "
                 f"mode 7 {dict(bc7_mode6.MODE7_CALLS)}" if final and not failures else ""))
    for name, blob in _corpora(work):
        inputs = [_pixels(blob[n * RECORD:n * RECORD + 64]) for n in range(len(blob) // RECORD)]
        runs = []
        for _ in range(3):
            started = time.perf_counter()
            for pixels in inputs:
                bc7_mode6.encode_block(pixels)
            runs.append(time.perf_counter() - started)
        print(f"{name}: encode_block via {backend} over {len(inputs)} blocks: median "
              f"{statistics.median(runs):.3f} s ({', '.join(f'{r:.3f}' for r in runs)})")
    return 1 if failures else 0


def time_build(game: Path, work: Path, languages: list[str], runs: int, encoder: str) -> None:
    """Cold builds in fresh processes and work folders, then one warm re-run of the last."""
    results: dict[str, dict] = {}
    env = {**os.environ, bc7_mode6.ENCODER_ENV: encoder}
    for language in languages:
        cold, warm = [], []
        for run in range(runs):
            folder = work / f"build-{encoder}-{language}-{run}"
            if folder.exists():
                raise SystemExit(f"{folder} exists; a cold build needs a fresh work folder")
            for kind, bucket in (("cold", cold), ("warm", warm) if run == runs - 1 else (None, None)):
                if kind is None:
                    continue
                started = time.perf_counter()
                out = subprocess.run([sys.executable, str(ROOT / "tools" / "pc_catalog.py"), "--game", str(game),
                                      "--language", language, "--work", str(folder)],
                                     capture_output=True, text=True, env=env, check=True)
                wall = time.perf_counter() - started
                summary = json.loads(out.stdout[out.stdout.rindex("\n{") + 1:])
                bucket.append({"wall": round(wall, 2), **summary["timings"], "cached": summary["cached"],
                               "patched": summary["patched"], "skipped": summary["skipped"]})
                print(f"{language} {kind} {run}: wall {wall:.1f} s, build {summary['timings'].get('total')} s, "
                      f"atlases {summary['timings'].get('atlases')} s, patched {summary['patched']}", flush=True)
        results[language] = {"cold": cold, "warm": warm,
                             "cold_median_total": statistics.median(r["total"] for r in cold),
                             "cold_median_atlases": statistics.median(r["atlases"] for r in cold),
                             "cold_median_wall": statistics.median(r["wall"] for r in cold),
                             "warm_total": warm[0]["total"] if warm else None}
    report = {"encoder": encoder, "game": str(game), "game_version": _game_version(game),
              "environment": _environment(), "results": results}
    path = work / f"timings-{encoder}.json"
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: {m: v[m] for m in v if m.endswith("median_total") or m.endswith("atlases")
                          or m == "warm_total"} for k, v in results.items()}, indent=1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("capture", "synthetic", "replay", "time-build"))
    parser.add_argument("--game", type=Path)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--languages", nargs="+", default=["en", "id"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--backend", choices=("python", "native"), default="python")
    parser.add_argument("--encoder", choices=("python", "native"), default="python")
    parser.add_argument("--final", action="store_true", help="replay: compare encode_block's bytes too")
    args = parser.parse_args()
    if args.command in ("capture", "time-build") and args.game is None:
        parser.error("--game is required")
    if args.command == "capture":
        capture(args.game, args.work, args.languages)
    elif args.command == "synthetic":
        synthetic(args.work)
    elif args.command == "replay":
        return replay(args.work, args.backend, args.final)
    else:
        time_build(args.game, args.work, args.languages, args.runs, args.encoder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
