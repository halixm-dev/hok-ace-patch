"""Cross-build the three pinned codec bindings for Android ARM64 using Chaquopy's headers."""
from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import subprocess
import tarfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SOURCES = {
    "pyooz": ("0.0.8", "98916331773493764483bc6448c9c6166bf2440939abe77cd140509038cc3adf"),
    "astc-encoder-py": ("0.1.12", "03759ac32804cae32bc238e72f94c5ba27e228507df00816b741f7961f1184f9"),
    "texture2ddecoder": ("1.0.6", "88f04d8951018ac13b8dacd07e57e8adad4a6f1cfe5509646e8a1020346a81ca"),
}
TAG = "cp312-cp312-android_24_arm64_v8a"


def _source(name: str, work: Path, sources: dict = SOURCES) -> Path:
    version, expected = sources[name]
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as stream:
        metadata = json.load(stream)
    record = next(item for item in metadata["urls"] if item["packagetype"] == "sdist")
    archive = work / record["filename"]
    if not archive.exists():
        urllib.request.urlretrieve(record["url"], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"Source archive hash mismatch: {name}")
    with tarfile.open(archive) as source:
        source.extractall(work, filter="data")
        directory = work / Path(source.getnames()[0]).parts[0]
    return directory


def _wheel(source: Path, files: dict[str, bytes], name: str, output: Path, sources: dict = SOURCES) -> Path:
    version = sources[name][0]
    normalized = name.replace("-", "_")
    metadata = f"{normalized}-{version}.dist-info"
    files[f"{metadata}/METADATA"] = (source / "PKG-INFO").read_bytes()
    files[f"{metadata}/WHEEL"] = (
        f"Wheel-Version: 1.0\nGenerator: hokace-android-native-spike\n"
        f"Root-Is-Purelib: false\nTag: {TAG}\n"
    ).encode()
    for license_file in source.rglob("*"):
        if license_file.is_file() and license_file.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
            files[f"{metadata}/licenses/{license_file.relative_to(source).as_posix()}"] = license_file.read_bytes()
    rows = []
    for filename, payload in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
        rows.append((filename, "sha256=" + digest, len(payload)))
    rows.append((f"{metadata}/RECORD", "", ""))
    record = io.StringIO(newline="")
    csv.writer(record).writerows(rows)
    files[f"{metadata}/RECORD"] = record.getvalue().encode()
    target = output / f"{normalized}-{version}-{TAG}.whl"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as wheel:
        for filename, payload in sorted(files.items()):
            wheel.writestr(filename, payload)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--python-target", type=Path, required=True,
                        help="Chaquopy target-3.12.x-0-arm64-v8a.zip from Gradle's cache")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    work, output = args.work.resolve(), args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    target = work / "python-target"
    with zipfile.ZipFile(args.python_target) as archive:
        for member in archive.infolist():
            if Path(member.filename).is_absolute() or ".." in Path(member.filename).parts:
                raise RuntimeError("Invalid target archive path")
        archive.extractall(target)
    prebuilt = args.ndk / "toolchains/llvm/prebuilt/windows-x86_64"
    clang = prebuilt / "bin/clang++.exe"
    common = [str(clang), "--target=aarch64-linux-android24", "-std=c++17", "-O2", "-fPIC",
              "-fvisibility=hidden", "-pthread",
              "-I" + str(target / "include/python3.12")]
    link = ["-shared", "-static-libstdc++", "-Wl,-z,max-page-size=16384",
            "-Wl,-z,common-page-size=16384", "-L" + str(target / "jniLibs/arm64-v8a"),
            "-lpython3.12"]
    report = {"ndk": str(args.ndk), "python_target": str(args.python_target), "tag": TAG, "wheels": []}
    for name in SOURCES:
        source = _source(name, work)
        files: dict[str, bytes] = {}
        jobs = []
        if name == "pyooz":
            paths = [source / "ooz/ooz_bindings.cpp"] + [source / "ooz/dep/ooz" / f"{stem}.cpp"
                                                       for stem in ("bitknit", "kraken", "lzna")]
            jobs.append(("ooz", paths, ["-DOOZ_BUILD_DLL=1", "-DPy_LIMITED_API=0x03080000",
                                        "-I" + str(source / "ooz/dep/ooz/simde")]))
        elif name == "texture2ddecoder":
            paths = [path for path in sorted((source / "src").rglob("*"))
                     if path.suffix in (".cpp", ".cxx") and path.name not in ("Texture2DDecoder.cpp", "AssemblyInfo.cpp")]
            jobs.append(("texture2ddecoder/_texture2ddecoder", paths,
                         ["-DPy_LIMITED_API=0x030B0000", "-fms-extensions",
                          "-I" + str(source / "src/Texture2DDecoder")]))
        else:
            tree = ast.parse((source / "setup.py").read_text())
            names = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                         and any(isinstance(item, ast.Name) and item.id == "ASTC_ENCODER_SOURCES" for item in node.targets))
            paths = [source / "src/pybind.cpp", source / "src/astcenc_error_metrics.cpp"] + [
                source / "src/astc-encoder/Source" / filename for filename in names]
            for variant in ("none", "neon"):
                macros = ["-DPy_LIMITED_API=0x03070000", '-DMODULE_NAME="module_name"',
                          f"-DINIT_FUNC_NAME=PyInit__encoder_{variant}",
                          f"-DASTCENC_NEON={int(variant == 'neon')}", "-DASTCENC_SVE=0",
                          "-DASTCENC_SSE=0", "-DASTCENC_AVX=0", "-DASTCENC_POPCNT=0", "-DASTCENC_F16C=0",
                          "-ffp-contract=fast", "-I" + str(source / "src/astc-encoder/Source")]
                jobs.append((f"astc_encoder/_encoder_{variant}", paths, macros))
        for module, paths, flags in jobs:
            objects = work / (name + "-" + module.replace("/", "-"))
            objects.mkdir(exist_ok=True)
            def compile_one(item: tuple[int, Path]) -> Path:
                index, path = item
                obj = objects / f"{index}.o"
                subprocess.run([*common, *flags, "-c", str(path), "-o", str(obj)], check=True)
                return obj
            with ThreadPoolExecutor(max_workers=4) as pool:
                compiled = list(pool.map(compile_one, enumerate(paths)))
            binary = objects / "extension.so"
            subprocess.run([*common, *map(str, compiled), *link, "-o", str(binary)], check=True)
            files[module + ".so"] = binary.read_bytes()
            print(f"Built {module}", flush=True)
        package = "astc_encoder" if name == "astc-encoder-py" else name
        if (source / package).is_dir():
            for path in (source / package).rglob("*"):
                if path.is_file() and (path.suffix in (".py", ".pyi") or path.name == "py.typed"):
                    files[path.relative_to(source).as_posix()] = path.read_bytes()
        wheel = _wheel(source, files, name, output)
        report["wheels"].append({"path": str(wheel), "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                                 "source_sha256": SOURCES[name][1]})
    (output / "build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
