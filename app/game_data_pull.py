"""The Windows patcher's game-data pull: copy the phone's override layer into a session, whole or changed files only.

`GameDataPull` is mixed into `patcher_core.Patcher`, its methods moved there verbatim. They use the
patcher's `adb`, `ui`, `work`, `run_owner`, `apk_journal` and `data_version`, and its `log`, `step`,
`done`, `producer_identity` and `preserve_recovery_snapshot`. `patcher_core` re-exports `PULL_RECORD`,
`LAYER_NAME`, `PULL_BATCH_CHARS` and `parse_device_hashes`.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable

import pristine_delta
from adb_device import PACKAGE, ByteReader
from pristine_layer import LAYER
from ui_strings import PatchError
from windows_checkpoints import Checkpoints

# Written into a session once its layer copy matches the phone; a later run copies unchanged files from it.
PULL_RECORD = "pull.json"
# Phone paths a partial pull accepts; anything else falls back to the full pull. Also keeps them shell-safe.
LAYER_NAME = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")
# Characters of file names per `tar` command, well under adb's command length on old devices.
PULL_BATCH_CHARS = 3000
TRANSFER_BLOCK = 256 * 1024
# Batch writes to the second file during a full pull to reduce HDD head movement.
BACKUP_BUFFER = 4 * 1024 * 1024
# Seconds between progress events, so the window redraws smoothly without flooding its queue.
PROGRESS_INTERVAL = 0.1


class _PullStream:
    """Count actual wire bytes, including tar padding, and optionally tee the recovery backup."""

    def __init__(self, source: ByteReader, backup: BinaryIO | None, progress: Callable[[int, float], None],
                 offset: int = 0):
        self.source = source
        self.backup = backup
        self.progress = progress
        self.size = 0
        self.offset = offset
        self.last_update = time.monotonic()
        self.last_size = 0
        self.rate = 0.0

    def read(self, size: int) -> bytes:
        data = self.source.read(size)
        if self.backup is not None:
            self.backup.write(data)
        self.size += len(data)
        now = time.monotonic()
        elapsed = now - self.last_update
        if elapsed >= PROGRESS_INTERVAL:
            sample = (self.size - self.last_size) / elapsed
            self.rate = sample if not self.rate else 0.8 * self.rate + 0.2 * sample
            self.progress(self.offset + self.size, self.rate)
            self.last_update, self.last_size = now, self.size
        return data


def _write_hashed(source: BinaryIO, output: BinaryIO, buffer: memoryview) -> str:
    """Copy <source> into <output> through <buffer>; the SHA-256 of the bytes copied."""
    digest = hashlib.sha256()
    while count := source.readinto(buffer):
        chunk = buffer[:count]
        digest.update(chunk)
        output.write(chunk)
    return digest.hexdigest()


def _extract_pull(stream: _PullStream, layer: Path, wanted: set[str] | None) -> dict[str, str]:
    """Consume one plain device tar in order. A session is published only after all checks pass."""
    hashes = {}
    buffer = memoryview(bytearray(TRANSFER_BLOCK))
    with tarfile.open(fileobj=stream, mode="r|", bufsize=TRANSFER_BLOCK) as archive:
        for member in archive:
            if not member.isfile():
                continue
            name = member.name.removeprefix("./")
            if wanted is None:
                if not name.startswith("packages/"):
                    continue
                name = name.removeprefix("packages/")
            elif name not in wanted:
                continue
            target = layer / name
            # Apply the standard extraction confinement check to the remapped member.
            if (not name or Path(name).anchor or ".." in Path(name).parts or ":" in name
                    or any(Path(part).is_reserved() for part in Path(name).parts)):
                raise tarfile.FilterError(f"Invalid package path: {name}")
            tarfile.data_filter(member.replace(name=name), layer)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                # Give the filesystem the final length before sequential writes.
                # A short tar member raises before the session can be published.
                output.truncate(member.size)
                hashes[name] = _write_hashed(source, output, buffer)
    # tarfile stops at the end marker. Drain the child before checking its exit status.
    while stream.read(TRANSFER_BLOCK):
        pass
    return hashes


def parse_device_hashes(output: str) -> dict[str, str] | None:
    """`sha256sum` output run in the phone's `packages/`, as {`<package id>/<file>`: SHA-256}.

    None when any line is not a plain digest and layer path, so the caller falls back to the full pull.
    """
    hashes: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        name = name.removeprefix("./")
        if (len(digest) != 64 or digest.strip("0123456789abcdef") or not LAYER_NAME.fullmatch(name)
                or name.startswith("-") or any(part.endswith(".") or Path(part).is_reserved() for part in name.split("/"))
                or name in hashes):
            return None
        hashes[name] = digest
    return hashes or None


def _copy_reusable(device: dict[str, str], sources: list[Path], layer: Path) -> list[str]:
    """Hash the bytes being copied, so a cache hit takes one source read and matches the phone."""
    missing = []
    buffer = memoryview(bytearray(TRANSFER_BLOCK))
    for name, expected in sorted(device.items()):
        target = layer / name
        for directory in sources:
            source = directory / name
            if not source.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as cached, target.open("xb") as output:
                matched = _write_hashed(cached, output, buffer) == expected
            if matched:
                break
            target.unlink()
        else:
            missing.append(name)
    return missing


class GameDataPull:
    def _pull_progress(self, received: int, rate: float) -> None:
        self.event("working", "read_game_data", bytes_done=received, bytes_per_second=rate)

    def pull_game_data(self) -> Path:
        self.step("pull", "~2 GB")
        info = self.adb.shell(f"run-as {PACKAGE} cat files/QtsVFSCache/packages/1/1.info", check=False)
        if '"version"' not in info:
            raise PatchError("error_game_data_missing")
        self.log(f"Game data version: {info.strip()}")
        self.data_version = info.strip()
        session_id = str(uuid.uuid4()) if self.run_owner is not None else datetime.now().strftime("%Y%m%d-%H%M%S")
        if self.run_owner is not None:
            self.run_owner.update(children={**self.run_owner.record["children"], "data_session": session_id})
        session = self.work / "sessions" / session_id
        session.mkdir(parents=True)
        previous = self.previous_session(session)
        record = None
        if previous:
            try:
                record = self.pull_changed(session, previous)
            except (OSError, tarfile.TarError, PatchError) as error:
                self.log(f"  the partial pull failed ({error}): pulling everything")
        if record is None:
            if (session / LAYER).exists():
                shutil.rmtree(session / LAYER)
            self.ui.set_step("pull", "active", "~2 GB")
            record = self.pull_everything(session)
        target = {"serial": self.adb.serial, "android_user": self.adb.android_user, "package": PACKAGE}
        record.update(data_version=self.data_version, target=target)
        pristine_delta.write_atomic(session / PULL_RECORD, json.dumps(record, indent=1).encode("utf-8"))
        self.preserve_recovery_snapshot(session)
        if self.apk_journal is not None:
            Checkpoints(self.run_owner, session).publish_snapshot(self.apk_journal.record["apks"], self.producer_identity())
        self.done("pull", info.strip())
        return session

    def pull_everything(self, session: Path) -> dict:
        """Pull the whole override layer, and the Watchdog folder, as one tar kept as the session's backup."""
        backup = session / "device-backup.tar"
        temporary = backup.with_suffix(".tar.tmp")
        command = f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache packages Watchdog"
        try:
            with self.adb.exec_out_stream(command) as source, temporary.open("wb", buffering=BACKUP_BUFFER) as output:
                stream = _PullStream(source, output, self._pull_progress)
                hashes = _extract_pull(stream, session / LAYER, None)
            if "1/1.info" not in hashes:
                raise PatchError("error_game_data_missing")
            temporary.replace(backup)
        finally:
            temporary.unlink(missing_ok=True)
        return {"mode": "full", "files": len(hashes), "pulled_bytes": stream.size, "sha256": hashes}

    def previous_session(self, session: Path) -> Path | None:
        """The newest other session whose layer copy matched the phone when it was pulled."""
        candidates = (path for path in (self.work / "sessions").iterdir() if path.is_dir())
        # UUID ownership names have no chronological ordering. Timestamp chooses
        # candidates only; every reused byte still has to match the live hash.
        for old in sorted(candidates, key=lambda path: (path / PULL_RECORD).stat().st_mtime_ns
                          if (path / PULL_RECORD).is_file() else 0, reverse=True):
            if old != session and (old / PULL_RECORD).is_file() and (old / LAYER).is_dir():
                try:
                    target = json.loads((old / PULL_RECORD).read_text(encoding="utf-8")).get("target")
                except (OSError, ValueError):
                    continue
                if target == {"serial": self.adb.serial, "android_user": self.adb.android_user, "package": PACKAGE}:
                    return old
        return None

    def pull_changed(self, session: Path, previous: Path) -> dict | None:
        """Pull only the files the phone holds at bytes <previous> has no copy of; None to pull everything.

        The phone hashes its layer, each file another session holds at that SHA-256 is copied from it, and
        the rest is pulled and checked against the phone's hash. The session's layer then holds exactly
        the phone's bytes, so every later step reads what a full pull would have given it. This session
        keeps no backup tar, which only a full pull writes.
        """
        self.ui.set_step("pull", "active", "comparing with the last run")
        output = self.adb.exec_out(f"run-as {PACKAGE} sh -c "
                                   f"'cd files/QtsVFSCache/packages && find . -type f -exec sha256sum {{}} +'")
        device = parse_device_hashes(output)
        if not device or "1/1.info" not in device:
            self.log("  the phone's file hashes did not read: pulling everything")
            return None
        layer = session / LAYER
        missing = _copy_reusable(device, [previous / "staged", previous / LAYER], layer)
        self.log(f"  {len(device) - len(missing)} of {len(device)} files unchanged since {previous.name}; "
                 f"pulling {len(missing)}")
        batches: list[list[str]] = []
        for name in missing:
            if not batches or sum(len(item) + 1 for item in batches[-1]) + len(name) > PULL_BATCH_CHARS:
                batches.append([])
            batches[-1].append(name)
        pulled_bytes = 0
        for batch in batches:
            command = f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache/packages " + " ".join(batch)
            with self.adb.exec_out_stream(command) as source:
                stream = _PullStream(source, None, self._pull_progress, pulled_bytes)
                hashes = _extract_pull(stream, layer, set(batch))
            for name in batch:
                if hashes.get(name) != device[name]:
                    self.log(f"  {name} did not arrive as the phone holds it: pulling everything")
                    return None
            pulled_bytes += stream.size
        self.log(f"  pulled {pulled_bytes / 1e6:.1f} MB instead of the whole layer")
        return {"mode": "changed", "files": len(device), "pulled_files": len(missing),
                "pulled_bytes": pulled_bytes, "copied_from": previous.name, "sha256": device}
