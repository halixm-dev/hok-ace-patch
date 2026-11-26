"""Build the single-file patcher exe with PyInstaller.

Run from the project root:  .venv\\Scripts\\python.exe app\\build_exe.py
Output: dist\\HOK ACE Language Patcher.exe (PyInstaller scratch goes to build\\, safe to delete).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
RESOURCES = ROOT / "resources"
NAME = "HOK ACE Language Patcher"
NATIVE_CRATE = ROOT / "crates" / "hok_bc7"
NATIVE_OUT = ROOT / "build" / "native"

# Stdlib modules the compiled translation runtime imports at run time; PyInstaller cannot see them.
HIDDEN_IMPORTS = [
    "asyncio", "bisect", "bz2", "calendar", "concurrent.futures", "csv", "ctypes", "dataclasses",
    "email", "email.message", "email.parser", "gzip", "heapq", "http", "http.client", "inspect",
    "ipaddress", "lzma", "mimetypes", "mmap", "select", "selectors", "socket", "ssl", "tempfile",
    "textwrap", "tokenize", "unicodedata", "urllib.parse", "urllib.request", "uuid", "dis", "quopri",
    "sqlite3", "struct", "zlib",
]


def build_native() -> Path:
    """`crates/hok_bc7` in release mode, for this interpreter (64-bit Python 3.12), as a .pyd."""
    if shutil.which("cargo") is None:
        sys.exit("cargo not found: install Rust with rustup (https://rustup.rs); the toolchain "
                 "crates/hok_bc7/rust-toolchain.toml pins is fetched on first build")
    # rustup reads rust-toolchain.toml from the working folder, so cargo runs inside the crate.
    env = {**os.environ, "PYO3_PYTHON": sys.executable}
    subprocess.run(["cargo", "build", "--release", "--locked"], cwd=NATIVE_CRATE, env=env, check=True)
    NATIVE_OUT.mkdir(parents=True, exist_ok=True)
    target = NATIVE_OUT / "hok_bc7.pyd"
    shutil.copyfile(NATIVE_CRATE / "target" / "release" / "hok_bc7.dll", target)
    return target


def build() -> None:
    build_native()
    sep = ";"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(APP), "--paths", str(ROOT / "tools"), "--paths", str(NATIVE_OUT),
        "--add-data", f"{ROOT / 'VERSION'}{sep}.",
        "--add-data", f"{RESOURCES / 'adb'}{sep}adb",
        "--add-data", f"{RESOURCES / 'runtime'}{sep}runtime",
        "--add-data", f"{RESOURCES / 'catalog'}{sep}catalog",
        # Indonesian: its own catalog.json.gz and re-drawn textures; every other texture payload is
        # read from catalog/ beside it (languages.payload_path), so the two must ship side by side.
        "--add-data", f"{RESOURCES / 'catalog_id'}{sep}catalog_id",
        # This repo's own sprite art for the regioned atlases, read beside the catalogs
        # (mobile_graphics.SPRITE_ART); without it the Career atlas loses its labels and repairs.
        "--add-data", f"{RESOURCES / 'sprites'}{sep}sprites",
        # The strings data updates added after the catalog was built (catalog_supplement._data_dir).
        "--add-data", f"{RESOURCES / 'catalog_supplement'}{sep}catalog_supplement",
        # resources/qtsvfs is not shipped: no package is laid out whole (REBUILD_PACKAGES is empty),
        # so the exe never loads Tencent's builder. It stays in the repo for --builder runs from source.
        "--add-data", f"{RESOURCES / 'key' / 'cert.der'}{sep}key",
        "--add-data", f"{RESOURCES / 'key' / 'key.pk8'}{sep}key",
        "--add-data", f"{RESOURCES / 'ui' / 'strings.json'}{sep}ui",
        "--add-data", f"{RESOURCES / 'ui' / 'theme.json'}{sep}ui",
        # Shared UI fonts and their licenses. The app loads the fonts privately at startup.
        "--add-data", f"{RESOURCES / 'fonts'}{sep}fonts",
        "--add-data", f"{RESOURCES / 'icon.ico'}{sep}.",
        "--add-data", f"{RESOURCES / 'icon.png'}{sep}.",
        "--icon", str(RESOURCES / "icon.ico"),
        "--collect-data", "customtkinter",
        "--collect-data", "archspec",
        "--collect-all", "astc_encoder",
        "--collect-all", "texture2ddecoder",
        "--collect-all", "ooz",
        # The extra-text pass romanises the opponent names with pypinyin, which carries its own
        # dictionary data; --hidden-import alone would ship the code without it.
        "--collect-all", "pypinyin",
    ]
    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]
    # Checkpoint readers are shipping code; research probes are deliberately not bundled.
    # Their producer identity hashes the actual onefile exe and extracted native bundle,
    # so local changes and codec bytes are covered without trusting VERSION metadata.
    args += ["--hidden-import", "run_artifacts"]
    # The PC edition: `hok_patcher` imports its workflow only for a PC job, and `bc7_mode6` imports the
    # native BC7 encoder only when it encodes; named here so the freeze never depends on finding them.
    # `hok_bc7` is its native BC7 search (`build_native`); the frozen smoke test fails without it.
    for module in ("pc_edition", "pc_catalog", "engine_hooks", "bc7_mode6", "etcpak", "hok_bc7"):
        args += ["--hidden-import", module]
    args.append(str(APP / "hok_patcher.py"))
    subprocess.run(args, check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--native-only"]:
        print(build_native())
    else:
        build()
