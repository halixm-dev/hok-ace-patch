"""Stream desktop control inputs into the feasibility app's own private scratch directory."""
from __future__ import annotations

import argparse
import hashlib
import re
import secrets
import socket
import struct
import subprocess
import time
from pathlib import Path

PACKAGE = "dev.halixm.hokacepatcher"
ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--file", nargs=2, action="append", default=[], metavar=("SOURCE", "PRIVATE_NAME"),
                        help="developer file for a new private session; can be repeated")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", args.session):
        parser.error("Session must contain only letters, numbers and hyphens (1–64)")
    full = any((args.game, args.apk, args.control))
    if full and not all((args.game, args.apk, args.control)):
        parser.error("Supply --game, --apk and --control together")
    if full and (not args.game.is_dir() or not args.apk.is_file() or not args.control.is_file()):
        parser.error("Matching game directory, normal APK and desktop control report are required")
    if not full and not args.file:
        parser.error("Supply a full control bundle or --file")
    adb = [str(args.adb), "-s", args.serial]
    jobs = []
    if full:
        jobs = [(path, "game/" + path.relative_to(args.game).as_posix())
                for path in sorted(args.game.rglob("*")) if path.is_file()]
        if any(path.is_symlink() for path in args.game.rglob("*")):
            parser.error("Scratch transfer refuses symlinks")
        jobs += [(args.apk, "normal.apk"), (args.control, "control.json"),
                 (ROOT / "tools/research/check_graphics.py", "oracle/tools/research/check_graphics.py")]
    for source, name in args.file:
        path = Path(source)
        if not path.is_file() or path.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or (
                name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/"))):
            parser.error("Invalid private file transfer")
        jobs.append((path, name))
    if len({name for _, name in jobs}) != len(jobs):
        parser.error("Duplicate private destination")
    total = sum(path.stat().st_size for path, _ in jobs)
    token = secrets.token_hex(32)
    port = int(subprocess.check_output([*adb, "forward", "tcp:0", "tcp:37491"], text=True).strip())
    process = subprocess.Popen([*adb, "shell", "am", "instrument", "-w", "-r", "-e", "class",
                                "dev.halixm.hokacepatcher.ScratchReceiverTest", "-e", "session", args.session,
                                "-e", "token", token, PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                connection = socket.create_connection(("127.0.0.1", port), timeout=60)
                # An adb forward can accept TCP before the device listener is ready.
                connection.sendall(token.encode("ascii") + struct.pack(">IQ", len(jobs), total))
                if connection.recv(1) != b"\x01":
                    connection.close()
                    raise ConnectionError("Scratch receiver is not ready")
                break
            except (ConnectionError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)
        with connection:
            for index, (path, name) in enumerate(jobs, 1):
                with path.open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").digest()
                    source.seek(0)
                    encoded = name.encode("utf-8")
                    connection.sendall(struct.pack(">H", len(encoded)) + encoded + struct.pack(">Q", path.stat().st_size) + digest)
                    while payload := source.read(1024 * 1024):
                        connection.sendall(payload)
                if connection.recv(1) != b"\x01":
                    raise RuntimeError(f"Device failed to verify {name}")
                if index % 100 == 0 or index == len(jobs):
                    print(f"Verified {index}/{len(jobs)} files", flush=True)
        output = process.communicate(timeout=60)[0].decode("utf-8", errors="replace")
        print(output)
        if process.returncode or "FAILURES" in output or "OK (1 test)" not in output:
            raise RuntimeError("Device scratch receiver failed")
    finally:
        if process.poll() is None:
            process.kill()
        subprocess.run([*adb, "forward", "--remove", f"tcp:{port}"], check=True)
    print("Scratch session ready: files/scratch/" + args.session)


if __name__ == "__main__":
    main()
