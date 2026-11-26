"""Download and launch the Windows Universal ADB Driver installer."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from ui_strings import PatchError


# URL and SHA-256 from Microsoft's ClockworkMod.UniversalADBDriver 1.0.4 WinGet manifest.
INSTALLER_URL = ("https://github.com/koush/adb.clockworkmod.com/releases/download/"
                 "v1.0.0/UniversalAdbDriverSetup.msi")
INSTALLER_SHA256 = "4e77e303bba6cf84588bdb6da91f7a875d406f7930cbe9f4d2aae0b643c0c928"
MAX_INSTALLER_BYTES = 20 * 1024 * 1024
# msiexec exit codes: ERROR_SUCCESS_REBOOT_INITIATED / _REQUIRED, ERROR_CANCELLED / ERROR_INSTALL_USEREXIT.
RESTART_NEEDED_CODES = frozenset({1641, 3010})
CANCELLED_CODES = frozenset({1223, 1602})


def install_adb_driver() -> int:
    """Verify the published MSI, then return the interactive installer's exit code."""
    with TemporaryDirectory(prefix="hok-ace-adb-driver-") as directory:
        installer = Path(directory) / "UniversalAdbDriverSetup.msi"
        with urlopen(INSTALLER_URL, timeout=30) as response:
            payload = response.read(MAX_INSTALLER_BYTES + 1)
        if len(payload) > MAX_INSTALLER_BYTES or hashlib.sha256(payload).hexdigest() != INSTALLER_SHA256:
            raise PatchError("usb_driver_failed")
        installer.write_bytes(payload)
        msiexec = Path(os.environ["SystemRoot"]) / "System32" / "msiexec.exe"
        return subprocess.run([str(msiexec), "/i", str(installer), "/norestart"], check=False).returncode


def driver_outcome(code: int) -> str:
    """The `usb_driver_*` string key for an installer exit code; anything unknown failed."""
    if code == 0:
        return "usb_driver_installed"
    if code in RESTART_NEEDED_CODES:
        return "usb_driver_restart"
    if code in CANCELLED_CODES:
        return "usb_driver_cancelled"
    return "usb_driver_failed"
