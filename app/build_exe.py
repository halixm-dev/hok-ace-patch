"""Build the single-file patcher exe with PyInstaller.

Run from the project root:  .venv\\Scripts\\python.exe app\\build_exe.py
Output: dist\\HOK ACE Mobile English Patcher.exe (PyInstaller scratch goes to build\\, safe to delete).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
RESOURCES = ROOT / "resources"
NAME = "HOK ACE Mobile English Patcher"

# Stdlib modules the compiled translation runtime imports at run time; PyInstaller cannot see them.
HIDDEN_IMPORTS = [
    "asyncio", "bisect", "bz2", "calendar", "concurrent.futures", "csv", "ctypes", "dataclasses",
    "email", "email.message", "email.parser", "gzip", "heapq", "http", "http.client", "inspect",
    "ipaddress", "lzma", "mimetypes", "mmap", "select", "selectors", "socket", "ssl", "tempfile",
    "textwrap", "tokenize", "unicodedata", "urllib.parse", "urllib.request", "uuid", "dis", "quopri",
    "sqlite3", "struct", "zlib",
]


def build() -> None:
    sep = ";"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(APP), "--paths", str(ROOT / "tools"),
        "--add-data", f"{RESOURCES / 'adb'}{sep}adb",
        "--add-data", f"{RESOURCES / 'runtime'}{sep}runtime",
        "--add-data", f"{RESOURCES / 'catalog'}{sep}catalog",
        "--add-data", f"{RESOURCES / 'key' / 'cert.der'}{sep}key",
        "--add-data", f"{RESOURCES / 'key' / 'key.pk8'}{sep}key",
        "--add-data", f"{RESOURCES / 'icon.ico'}{sep}.",
        "--add-data", f"{RESOURCES / 'icon.png'}{sep}.",
        "--icon", str(RESOURCES / "icon.ico"),
        "--collect-data", "customtkinter",
        "--collect-data", "archspec",
        "--collect-all", "astc_encoder",
        "--collect-all", "texture2ddecoder",
        "--collect-all", "ooz",
    ]
    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]
    args.append(str(APP / "hok_patcher.py"))
    subprocess.run(args, check=True)


if __name__ == "__main__":
    build()
