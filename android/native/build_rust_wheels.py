"""Cross-build the Rust unit crates the Android app loads as Chaquopy wheels (`rust/DECISIONS.md` ADR-019).

Each crate in ``CRATES`` is a PyO3 crate (abi3): a rust-anything crate whose Python package sits in
``<crate>/python/<package>``, which the wheel carries with the binary as ``<package>/_native.so``, or a
plain extension module, carried as ``<package>.abi3.so``. This builds for ``aarch64-linux-android`` with the NDK's clang,
links it against Chaquopy's ``libpython3.12.so`` (Android resolves an extension's symbols only through
its own DT_NEEDED libraries) with 16 KiB load alignment, and writes
``<package>-<version>-cp312-cp312-android_24_arm64_v8a.whl`` with the package's Python files and
``_native.so``. The switch-on block in the original module then imports the package from
site-packages, as it does from ``<crate>/python`` on Windows. A wheel built here ships only once
``android/app/build.gradle.kts`` installs it: ``hok_astc`` is built but not installed, because the phone's
``astc_encoder`` wheel gives other bytes (``-ffp-contract=fast``) and switching needs a device cycle.

    .venv\\Scripts\\python.exe android\\native\\build_rust_wheels.py --ndk <sdk>\\ndk\\28.2.13676358
        --python-target <gradle cache>\\target-3.12.12-0-arm64-v8a.zip --work <dir> --output android\\wheels

Each crate's ``rust-toolchain.toml`` pins its toolchain with the ``aarch64-linux-android`` target.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRATES = {
    "rust/stale-blocks-rs": "stale_blocks_rs",
    "crates/hok_astc": "hok_astc",
    "crates/hok_codecs": "hok_codecs",
}
TARGET = "aarch64-linux-android"
API = 24
TAG = f"cp312-cp312-android_{API}_arm64_v8a"
sys.path.insert(0, str(ROOT / "tools" / "research"))
from check_android_native import inspect_elf  # noqa: E402


def _wheel(package: str, version: str, files: dict[str, bytes], output: Path) -> Path:
    metadata = f"{package}-{version}.dist-info"
    files[f"{metadata}/METADATA"] = f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n".encode()
    files[f"{metadata}/WHEEL"] = (f"Wheel-Version: 1.0\nGenerator: hokace-build-rust-wheels\n"
                                  f"Root-Is-Purelib: false\nTag: {TAG}\n").encode()
    rows = [(name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode(),
             len(data)) for name, data in sorted(files.items())]
    rows.append((f"{metadata}/RECORD", "", ""))
    record = io.StringIO(newline="")
    csv.writer(record).writerows(rows)
    files[f"{metadata}/RECORD"] = record.getvalue().encode()
    target = output / f"{package}-{version}-{TAG}.whl"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as wheel:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            wheel.writestr(info, data)
    return target


def _build(crate: Path, env: dict[str, str], target_dir: Path) -> Path:
    # From the crate's folder, so rustup takes the toolchain its rust-toolchain.toml pins.
    subprocess.run(["cargo", "build", "--release", "--locked", "--target", TARGET, "--target-dir", str(target_dir)],
                   check=True, env=env, cwd=crate)
    name = tomllib.loads((crate / "Cargo.toml").read_text(encoding="utf-8"))["package"]["name"]
    return target_dir / TARGET / "release" / f"lib{name.replace('-', '_')}.so"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--python-target", type=Path, required=True,
                        help="Chaquopy target-3.12.x-0-arm64-v8a.zip from Gradle's cache")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    work, output = args.work.resolve(), args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    lib_dir = work / "python-target" / "jniLibs" / "arm64-v8a"
    with zipfile.ZipFile(args.python_target) as archive:
        member = "jniLibs/arm64-v8a/libpython3.12.so"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "libpython3.12.so").write_bytes(archive.read(member))
    config = work / "pyo3-android.txt"
    config.write_text("implementation=CPython\nversion=3.12\nshared=true\nabi3=true\nlib_name=python3.12\n"
                      f"lib_dir={lib_dir.as_posix()}\npointer_width=64\nsuppress_build_script_link_lines=false\n",
                      encoding="utf-8")
    linker = args.ndk / "toolchains/llvm/prebuilt/windows-x86_64/bin" / f"{TARGET}{API}-clang.cmd"
    if not linker.is_file():
        raise SystemExit(f"no NDK linker at {linker}")
    env = dict(os.environ, PYO3_CONFIG_FILE=str(config),
               CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER=str(linker),
               CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS=" ".join([
                   "-C", "link-arg=-Wl,-z,max-page-size=16384",
                   "-C", "link-arg=-Wl,-z,common-page-size=16384",
                   "-C", f"link-arg=-L{lib_dir.as_posix()}", "-C", "link-arg=-lpython3.12"]))
    report = {"ndk": str(args.ndk), "python_target": str(args.python_target), "tag": TAG, "wheels": []}
    for crate_path, package in CRATES.items():
        crate = ROOT / crate_path
        binary = _build(crate, env, work / "target")
        native = binary.read_bytes()
        elf = inspect_elf(native)
        if elf["machine"] != 183 or not elf["aligned_16k"]:
            raise SystemExit(f"{binary.name}: machine {elf['machine']}, aligned_16k {elf['aligned_16k']}")
        python = crate / "python" / package
        if python.is_dir():
            files = {f"{package}/_native.so": native}
            for path in sorted(python.glob("*.py")):
                files[f"{package}/{path.name}"] = path.read_bytes()
        else:
            files = {f"{package}.abi3.so": native}
        version = tomllib.loads((crate / "Cargo.toml").read_text(encoding="utf-8"))["package"]["version"]
        if package == "hok_codecs":
            notices = f"{package}-{version}.dist-info/licenses"
            files[f"{notices}/GPL-3.0.txt"] = (ROOT / "android/native/licenses/GPL-3.0.txt").read_bytes()
            files[f"{notices}/NOTICE.md"] = (ROOT / "rust/hokace/oodle/NOTICE.md").read_bytes()
        wheel = _wheel(package, version, files, output)
        report["wheels"].append({"path": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                                 "native_sha256": hashlib.sha256(native).hexdigest(), "aligned_16k": True})
        print(f"Built {wheel.name}", flush=True)
    (output / "rust-build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
