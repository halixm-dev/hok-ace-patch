"""Rebuild the pinned Chaquopy FreeType dependency with 16 KiB load alignment."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from build_wheels import _wheel

SOURCE_SHA256 = "ec391504e55498adceb30baceebd147a6e963f636eb617424bcfc47a169898ce"
SOURCE_URL = "https://download.savannah.gnu.org/releases/freetype/freetype-2.9.1.tar.gz"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--cmake", type=Path, required=True, help="Installed SDK cmake directory")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    archive = work / "freetype-2.9.1.tar.gz"
    if not archive.exists():
        urllib.request.urlretrieve(SOURCE_URL, archive)
    check_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    if check_hash != SOURCE_SHA256:
        raise ValueError("FreeType source archive hash differs")
    with tarfile.open(archive) as stream:
        stream.extractall(work, filter="data")
    source = work / "freetype-2.9.1"
    build = work / "freetype-android-static"
    cmake = args.cmake / "bin/cmake.exe"
    subprocess.run([str(cmake), "-S", str(source), "-B", str(build), "-G", "Ninja",
                    "-DCMAKE_MAKE_PROGRAM=" + str(args.cmake / "bin/ninja.exe"),
                    "-DCMAKE_TOOLCHAIN_FILE=" + str(args.ndk / "build/cmake/android.toolchain.cmake"),
                    "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-24",
                    "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
                    "-DBUILD_SHARED_LIBS=OFF", "-DFT_WITH_ZLIB=ON",
                    "-DCMAKE_DISABLE_FIND_PACKAGE_HarfBuzz=TRUE", "-DCMAKE_DISABLE_FIND_PACKAGE_PNG=TRUE",
                    "-DCMAKE_DISABLE_FIND_PACKAGE_BZip2=TRUE"], check=True)
    subprocess.run([str(cmake), "--build", str(build), "--parallel", "4"], check=True)
    compiler = args.ndk / "toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe"
    binary = build / "libfreetype.so"
    subprocess.run([str(compiler), "--target=aarch64-linux-android24", "-shared",
                    "-Wl,--whole-archive", str(build / "libfreetype.a"), "-Wl,--no-whole-archive",
                    "-lz", "-lm", "-Wl,-soname,libfreetype.so", "-Wl,-z,max-page-size=16384",
                    "-Wl,-z,common-page-size=16384", "-o", str(binary)], check=True)
    metadata = work / "freetype-wheel-metadata"
    metadata.mkdir(exist_ok=True)
    (metadata / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: chaquopy-freetype\nVersion: 2.9.1\n"
                                        "Summary: Source-built Android FreeType dependency\nLicense: FreeType License\n",
                                        encoding="utf-8")
    shutil.copyfile(source / "docs/FTL.TXT", metadata / "LICENSE-FTL.txt")
    shutil.copyfile(source / "docs/LICENSE.TXT", metadata / "LICENSE.txt")
    wheel = _wheel(metadata, {"chaquopy/lib/libfreetype.so": binary.read_bytes()}, "chaquopy-freetype",
                   args.output, {"chaquopy-freetype": ("2.9.1", SOURCE_SHA256)})
    report = {"source_url": SOURCE_URL, "source_sha256": SOURCE_SHA256,
              "wheel": str(wheel), "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
              "features": {"system_zlib": True, "harfbuzz": False, "png": False, "bzip2": False},
              "ndk": str(args.ndk), "cmake": str(args.cmake)}
    (args.output / "freetype-build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Built", wheel, flush=True)


if __name__ == "__main__":
    main()
