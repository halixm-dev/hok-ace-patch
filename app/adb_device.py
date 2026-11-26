"""The ADB client the Windows patcher drives a phone through, bound to one phone and Android user.

Moved verbatim out of `patcher_core`, which re-exports `Adb`, `PACKAGE` and `NO_WINDOW`.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import apk_tools
from ui_strings import BUNDLE, PatchError

if TYPE_CHECKING:
    from patch_session import OwnedRun


PACKAGE = "com.tencent.tmgp.osgame"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class Adb:
    def __init__(self, work: Path, *, serial: str | None = None, android_user: int | None = None,
                 owner: OwnedRun | None = None) -> None:
        self.serial, self.android_user, self.owner = serial, android_user, owner
        self.boundary = None
        self.progress = None
        target = work / "adb"
        target.mkdir(parents=True, exist_ok=True)
        # Run adb from a persistent folder so its background server never locks the PyInstaller temp dir.
        for item in (BUNDLE / "adb").iterdir():
            if not (target / item.name).exists() or (target / item.name).stat().st_size != item.stat().st_size:
                shutil.copy2(item, target / item.name)
        self.exe = str(target / "adb.exe")

    def bind(self, serial: str, android_user: int | None = None) -> None:
        if (not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", serial)
                or self.serial is not None and self.serial != serial
                or self.android_user is not None and android_user is not None and self.android_user != android_user):
            raise PatchError("error_run_target", detail=serial)
        self.serial = serial
        if android_user is not None:
            self.android_user = android_user

    def _argv(self, args: tuple[str, ...]) -> list[str]:
        if args and args[0] in {"start-server", "devices"} and len(args) == 1:
            return [self.exe, *args]
        if not self.serial or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", self.serial):
            raise PatchError("error_run_target", detail="Select the saved phone first")
        if not args or args[0] not in {"shell", "exec-out", "pull", "push", "install", "uninstall",
                                         "reconnect", "get-state", "get-serialno", "wait-for-device"}:
            raise PatchError("error_run_target", detail="Unsafe ADB target override")
        return [self.exe, "-s", self.serial, *args]

    def _process_options(self) -> dict:
        return self.owner.subprocess_options() if self.owner is not None else {}

    def assert_target(self) -> int:
        """Refuse Android-user switching before any device mutation."""
        value = self.shell("am get-current-user").strip()
        if not value.isdecimal():
            raise PatchError("error_run_target", detail="Cannot verify Android user")
        user = int(value)
        if self.android_user is not None and user != self.android_user:
            raise PatchError("error_run_target", detail=f"Android user {user}")
        self.android_user = user
        # run-as and the shared package paths used here target Android's owner user.
        if user != 0:
            raise PatchError("error_run_target", detail="Use the phone's owner profile (user 0)")
        return user

    def run(self, *args: str, check: bool = True) -> str:
        if self.boundary is not None:
            self.boundary()
        if args and args[0] in {"push", "install", "uninstall", "reconnect"}:
            self.assert_target()
        result = subprocess.run(self._argv(args), capture_output=True, text=True, encoding="utf-8",
                                errors="replace", creationflags=NO_WINDOW, timeout=180, **self._process_options())
        output = (result.stdout + result.stderr).strip()
        if check and result.returncode != 0:
            raise PatchError("error_adb_failed", command=" ".join(args), output=output)
        return output

    def shell(self, command: str, check: bool = True) -> str:
        if command != "am get-current-user":
            self.assert_target()
        return self.run("shell", command, check=check)

    def exec_out(self, command: str) -> str:
        self.assert_target()
        return self.run("exec-out", command)

    def exec_out_to_file(self, command: str, target: Path) -> None:
        if self.boundary is not None:
            self.boundary()
        self.assert_target()
        with target.open("wb") as out:
            result = subprocess.run(self._argv(("exec-out", command)), stdout=out, stderr=subprocess.PIPE,
                                    creationflags=NO_WINDOW, timeout=180, **self._process_options())
        if self.progress is not None:
            self.progress(target.stat().st_size)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise PatchError("error_read_failed", output=stderr)

    def installed_identity(self) -> dict | None:
        """Independently read installed bytes, with path/hash stability across the pull."""
        self.assert_target()
        listed = self.shell(f"pm list packages --user 0 {PACKAGE}").strip()
        if listed == "":
            return None
        if listed != f"package:{PACKAGE}":
            raise PatchError("error_apk_identity", detail="Package enumeration is ambiguous")
        path_output = self.shell(f"pm path {PACKAGE}").strip()
        match = re.fullmatch(r"package:(/data/app/[A-Za-z0-9_./=+~-]+\.apk)", path_output)
        if match is None or ".." in match[1].split("/"):
            raise PatchError("error_apk_identity", detail="Cannot verify a single installed APK")
        remote = match[1]
        before = self.shell(f"sha256sum '{remote}'").split()
        if len(before) != 2 or not re.fullmatch("[0-9a-f]{64}", before[0]):
            raise PatchError("error_apk_identity", detail="Installed APK hash unavailable")
        with tempfile.TemporaryDirectory(prefix="apk-audit-", dir=Path(self.exe).parent) as temporary:
            local = Path(temporary) / "observed.apk"
            self.run("pull", remote, str(local))
            parse_error = None
            try:
                identity = apk_tools.apk_identity(local)
                digest = identity["sha256"]
            except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as error:
                parse_error = error
                try:
                    with local.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                except OSError as read_error:
                    raise PatchError("error_read_failed", output=read_error) from read_error
            after = self.shell(f"sha256sum '{remote}'").split()
            if before != after or self.shell(f"pm path {PACKAGE}").strip() != path_output:
                raise PatchError("error_apk_identity", detail="Installed APK changed during observation")
            if digest != before[0]:
                raise PatchError("error_read_failed", output="APK copied over USB differs from the phone's checksum")
            if parse_error is not None:
                raise PatchError("error_apk_identity", detail=parse_error) from parse_error
            if identity["package"] != PACKAGE:
                raise PatchError("error_apk_identity", detail="Installed APK belongs to another package")
            return identity

    def install(self, apk: Path) -> None:
        """Reconcile commit-before-lost-reply; transport Success alone is never proof."""
        self.assert_target()
        try:
            expected = apk_tools.apk_identity(apk)
        except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as error:
            raise PatchError("error_apk_identity", detail=error) from error
        failure = None
        try:
            output = self.run("install", "-r", str(apk), check=False)
        except (OSError, PatchError) as error:
            failure, output = error, str(error)
        if self.installed_identity() == expected:
            return
        if "INSTALL_FAILED_VERIFICATION_FAILURE" in output:
            raise PatchError("error_play_protect_blocked") from failure
        raise PatchError("error_install_failed", output=output) from failure

    @staticmethod
    def kill_server(work: Path) -> None:
        adb = work / "adb" / "adb.exe"
        if adb.exists():
            subprocess.run([str(adb), "kill-server"], creationflags=NO_WINDOW, capture_output=True)
