"""Cross-build pinned LZ4 and both Zstandard bindings with 16 KiB ELF alignment."""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
from pathlib import Path

from build_wheels import TAG, _source, _wheel

SOURCES = {
    "lz4": ("4.3.2", "e1431d84a9cfb23e6773e72078ce8e65cad6745816d4cbf9ae67da5ea419acda"),
    "zstandard": ("0.22.0", "8226a33c542bcb54cd6bd0a366067b610b41713b64c9abec1bc4533d69f51e70"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--python-headers", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.work = args.work.resolve()
    args.output = args.output.resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    clang = args.ndk / "toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe"
    common = [str(clang), "--target=aarch64-linux-android24", "-O3", "-fPIC", "-pthread",
              "-fvisibility=hidden", "-I" + str(args.python_headers)]
    link = ["-shared", "-Wl,-z,max-page-size=16384", "-Wl,-z,common-page-size=16384",
            "-L" + str(args.python_libs), "-lpython3.12"]
    import cffi
    report = {"tag": TAG, "ndk": str(args.ndk), "cffi_generator": cffi.__version__, "wheels": []}
    for name in SOURCES:
        source = _source(name, args.work, SOURCES)
        files = {path.relative_to(source).as_posix(): path.read_bytes()
                 for path in (source / name).rglob("*")
                 if path.is_file() and path.suffix in (".py", ".pyi")}
        jobs = []
        if name == "lz4":
            library = source / "lz4libs"
            for module, units in [("_version", ["lz4.c"]), ("block/_block", ["lz4.c", "lz4hc.c"]),
                                  ("frame/_frame", ["lz4.c", "lz4hc.c", "lz4frame.c", "xxhash.c"])]:
                jobs.append(("lz4/" + module, [source / "lz4" / (module + ".c")] +
                             [library / unit for unit in units], ["-I" + str(library)]))
        else:
            flags = ["-I" + str(source / "c-ext"), "-I" + str(source / "zstd"),
                     "-DZSTD_SINGLE_FILE", "-DZSTDLIB_VISIBLE=", "-DZDICTLIB_VISIBLE=", "-DZSTDERRORLIB_VISIBLE="]
            jobs.append(("zstandard/backend_c", [source / "c-ext/backend_c.c"], flags))
            # Use the upstream CFFI generator with an Android preprocessor, without editing source.
            import distutils.ccompiler
            import distutils.sysconfig
            compiler = distutils.ccompiler.new_compiler(compiler="unix")
            compiler.set_executable("preprocessor", [str(clang), "--target=aarch64-linux-android24", "-E"])
            factory = distutils.ccompiler.new_compiler
            customize = distutils.sysconfig.customize_compiler
            try:
                distutils.ccompiler.new_compiler = lambda *a, **kw: compiler
                # The preprocessor is already explicitly configured for Android; Windows host
                # sysconfig has no Unix compiler settings and must not replace those arguments.
                distutils.sysconfig.customize_compiler = lambda selected: None
                generated = runpy.run_path(str(source / "make_cffi.py"))
            finally:
                distutils.ccompiler.new_compiler = factory
                distutils.sysconfig.customize_compiler = customize
            cffi_source = args.work / "zstandard-cffi.c"
            generated["ffi"].emit_c_code(str(cffi_source))
            jobs.append(("zstandard/_cffi", [cffi_source, source / "zstd/zstd.c"],
                         ["-I" + str(source / "zstd")]))
        for module, units, flags in jobs:
            objects = args.work / module.replace("/", "-")
            objects.mkdir(exist_ok=True)
            compiled = []
            for index, unit in enumerate(units):
                obj = objects / f"{index}.o"
                subprocess.run([*common, *flags, "-c", str(unit), "-o", str(obj)], check=True)
                compiled.append(str(obj))
            binary = objects / "extension.so"
            subprocess.run([*common, *compiled, *link, "-o", str(binary)], check=True)
            files[module + ".so"] = binary.read_bytes()
            print(f"Built {module}", flush=True)
        wheel = _wheel(source, files, name, args.output, SOURCES)
        report["wheels"].append({"path": str(wheel), "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                                 "source_sha256": SOURCES[name][1]})
    (args.output / "compression-build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
