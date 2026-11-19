"""The Windows patcher's game-data pull: copy the phone's override layer into a session, whole or changed files only.

`GameDataPull` is mixed into `patcher_core.Patcher`, its methods moved there verbatim. They use the
patcher's `adb`, `ui`, `work`, `run_owner`, `apk_journal` and `data_version`, and its `log`, `step`,
`done`, `producer_identity` and `preserve_recovery_snapshot`. `patcher_core` re-exports `PULL_RECORD`,
`LAYER_NAME`, `PULL_BATCH_CHARS`, `parse_device_hashes` and `reusable_files`.
"""
from __future__ import annotations

import json
import re
import shutil
import tarfile
import uuid
from datetime import datetime
from pathlib import Path

import pristine_delta
from adb_device import PACKAGE
from pristine_layer import LAYER
from ui_strings import PatchError
from windows_checkpoints import Checkpoints

# Written into a session once its layer copy matches the phone; a later run copies unchanged files from it.
PULL_RECORD = "pull.json"
# Phone paths a partial pull accepts; anything else falls back to the full pull. Also keeps them shell-safe.
LAYER_NAME = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")
# Characters of file names per `tar` command, well under adb's command length on old devices.
PULL_BATCH_CHARS = 3000


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
                or {".", ".."} & set(name.split("/")) or name in hashes):
            return None
        hashes[name] = digest
    return hashes or None


def reusable_files(device: dict[str, str], sources: list[Path]) -> tuple[dict[str, Path], list[str]]:
    """Split <device> into the files some <sources> folder holds at the same SHA-256, and the rest."""
    found: dict[str, Path] = {}
    missing = []
    for name, digest in sorted(device.items()):
        for source in sources:
            path = source / name
            if path.is_file() and pristine_delta.sha256_file(path) == digest:
                found[name] = path
                break
        else:
            missing.append(name)
    return found, missing


class GameDataPull:
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
            shutil.rmtree(session / LAYER, ignore_errors=True)
            for part in session.glob("pull-*.tar"):
                part.unlink()
            self.ui.set_step("pull", "active", "~2 GB")
            record = self.pull_everything(session)
        (session / PULL_RECORD).write_text(json.dumps({"data_version": self.data_version,
                                           "target": {"serial": self.adb.serial,
                                                      "android_user": self.adb.android_user,
                                                      "package": PACKAGE}, **record}, indent=1),
                                           encoding="utf-8")
        self.preserve_recovery_snapshot(session)
        if self.apk_journal is not None:
            Checkpoints(self.run_owner, session).publish_snapshot(self.apk_journal.record["apks"], self.producer_identity())
        self.done("pull", info.strip())
        return session

    def pull_everything(self, session: Path) -> dict:
        """Pull the whole override layer, and the Watchdog folder, as one tar kept as the session's backup."""
        backup = session / "device-backup.tar"
        self.adb.exec_out_to_file(f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache packages Watchdog", backup)
        game = session / LAYER.parent
        game.mkdir(parents=True, exist_ok=True)  # a failed partial pull leaves it behind
        # Extract straight into builtin/: renaming the folder afterwards fails at random on Windows,
        # while a scanner still holds some of the 2 GB of files just written (seen 2026-10-17).
        with tarfile.open(backup) as tar:
            members = [m for m in tar.getmembers() if m.name.startswith("packages/") and m.isfile()]
            for member in members:
                member.name = "builtin/" + member.name.removeprefix("packages/")
            tar.extractall(game, members=members, filter="data")
        layer = session / LAYER
        hashes = {name: pristine_delta.sha256_file(layer / name)
                  for name in (member.name.removeprefix("builtin/") for member in members)}
        return {"mode": "full", "files": len(members), "pulled_bytes": backup.stat().st_size, "sha256": hashes}

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
        found, missing = reusable_files(device, [previous / "staged", previous / LAYER])
        layer = session / LAYER
        for name, source in found.items():
            (layer / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, layer / name)
        self.log(f"  {len(found)} of {len(device)} files unchanged since {previous.name}; "
                 f"pulling {len(missing)}")
        batches: list[list[str]] = []
        for name in missing:
            if not batches or sum(len(item) + 1 for item in batches[-1]) + len(name) > PULL_BATCH_CHARS:
                batches.append([])
            batches[-1].append(name)
        pulled_bytes = 0
        for index, batch in enumerate(batches):
            part = session / f"pull-{index}.tar"
            self.adb.exec_out_to_file(f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache/packages "
                                      + " ".join(batch), part)
            wanted = set(batch)
            with tarfile.open(part) as tar:
                members = [m for m in tar.getmembers() if m.isfile() and m.name.removeprefix("./") in wanted]
                for member in members:
                    member.name = member.name.removeprefix("./")
                tar.extractall(layer, members=members, filter="data")
            pulled_bytes += part.stat().st_size
            part.unlink()
        for name in missing:
            path = layer / name
            if not path.is_file() or pristine_delta.sha256_file(path) != device[name]:
                self.log(f"  {name} did not arrive as the phone holds it: pulling everything")
                return None
        self.log(f"  pulled {pulled_bytes / 1e6:.1f} MB instead of the whole layer")
        return {"mode": "changed", "files": len(device), "pulled_files": len(missing),
                "pulled_bytes": pulled_bytes, "copied_from": previous.name, "sha256": device}
