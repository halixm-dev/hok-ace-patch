"""Time the Rust ASTC port on a phone against Arm astcenc built as the Android wheel builds it.

Builds three aarch64 programs and runs each over a codec tap's ``encode_astc`` calls on the phone
connected over adb:

- ``replay``: ``rust/hokace/astcenc``'s replay example, which also checks every output against the
  tap byte for byte (the tap holds the Windows wheel's bytes).
- ``oracle-neon`` and ``oracle-none``: ``astcenc_oracle/oracle.cpp`` with the wheel's two Android
  variants (``android/native/build_wheels.py``: NDK clang, ``-O2``, ``-ffp-contract=fast``,
  ``ASTCENC_NEON=1`` or ``0``). Single-threaded. Fused multiply-add makes their bytes differ from
  the tap, so only their time is reported.

    .venv\\Scripts\\python.exe rust\\harness\\phone_astc_timing.py --tap D:\\scratch\\rust-port\\tap-en ^
        --sdist D:\\scratch\\rust-port\\astc-sdist\\astc_encoder_py-0.1.12 ^
        --ndk %LOCALAPPDATA%\\Android\\Sdk\\ndk\\28.2.13676358 --work D:\\scratch\\rust-port\\phone

``--threads 1,8`` sets the Rust thread counts, ``--limit N`` the first N calls, ``--skip-build`` and
``--skip-push`` reuse an earlier run's programs and staged tap. Everything goes to
``/data/local/tmp/hokace-astc`` on the phone; ``--clean`` removes it afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "rust" / "hokace"
ORACLE = Path(__file__).resolve().parent / "astcenc_oracle" / "oracle.cpp"
TARGET = "aarch64-linux-android"
API = 24
REMOTE = "/data/local/tmp/hokace-astc"
ASTC_SOURCES = (
    "averages_and_directions", "block_sizes", "color_quantize", "color_unquantize", "compress_symbolic",
    "compute_variance", "decompress_symbolic", "diagnostic_trace", "entry", "find_best_partitioning",
    "ideal_endpoints_and_weights", "image", "integer_sequence", "mathlib", "mathlib_softfloat",
    "partition_tables", "percentile_tables", "pick_best_endpoint_format", "quantization",
    "symbolic_physical", "weight_align", "weight_quant_xfer_tables",
)


def _ndk_bin(ndk: Path) -> Path:
    return ndk / "toolchains" / "llvm" / "prebuilt" / "windows-x86_64" / "bin"


def build_replay(ndk: Path) -> Path:
    linker = _ndk_bin(ndk) / f"{TARGET}{API}-clang.cmd"
    if not linker.is_file():
        raise SystemExit(f"no NDK linker at {linker}")
    env = dict(os.environ, CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER=str(linker))
    subprocess.run(["cargo", "build", "--release", "-p", "hokace-astcenc", "--example", "replay",
                    "--target", TARGET], cwd=WORKSPACE, env=env, check=True)
    return WORKSPACE / "target" / TARGET / "release" / "examples" / "replay"


def build_oracle(ndk: Path, sdist: Path, work: Path, neon: bool) -> Path:
    source = sdist / "src" / "astc-encoder" / "Source"
    clang = _ndk_bin(ndk) / "clang++.exe"
    out = work / ("oracle-neon" if neon else "oracle-none")
    subprocess.run([
        str(clang), f"--target={TARGET}{API}", "-std=c++17", "-O2", "-ffp-contract=fast", "-DNDEBUG",
        f"-DASTCENC_NEON={int(neon)}", "-DASTCENC_SVE=0", "-DASTCENC_SSE=0", "-DASTCENC_AVX=0",
        "-DASTCENC_POPCNT=0", "-DASTCENC_F16C=0", "-I" + str(source), "-static-libstdc++",
        str(ORACLE), *(str(source / f"astcenc_{name}.cpp") for name in ASTC_SOURCES), "-o", str(out),
    ], check=True)
    return out


def stage_tap(tap: Path, work: Path, limit: int | None) -> Path:
    """The tap's ``encode_astc`` calls and their blobs only, plus the oracle's manifest."""
    staged = work / "tap"
    if staged.exists():
        shutil.rmtree(staged)
    (staged / "blobs").mkdir(parents=True)
    calls, manifest = [], []
    with (tap / "calls.jsonl").open(encoding="utf-8") as records:
        for line in records:
            call = json.loads(line)
            if call["fn"] != "encode_astc":
                continue
            if limit is not None and len(calls) >= limit:
                break
            calls.append(line.rstrip("\n"))
            for blob in (call["input"], call["output"]):
                shutil.copyfile(tap / "blobs" / blob, staged / "blobs" / blob)
            width, height, bx, by = call["args"]
            manifest.append(f"{width} {height} {bx} {by} {REMOTE}/tap/blobs/{call['input']} "
                            f"{REMOTE}/out/{len(calls)}.astc")
    (staged / "calls.jsonl").write_text("\n".join(calls) + "\n", encoding="utf-8")
    (staged / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return staged


def adb(*args: str, serial: str | None, capture: bool = False) -> str:
    command = ["adb", *(["-s", serial] if serial else []), *args]
    result = subprocess.run(command, check=True, capture_output=capture, text=True)
    return result.stdout if capture else ""


def fast_core_mask(serial: str | None) -> str:
    """The phone's highest-clocked cores as a ``taskset`` mask: a one-thread run left to the
    scheduler can land on a slower cluster and take three times as long (measured 2026-11-27)."""
    freqs = [int(f) for f in adb("shell", "cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq",
                                 serial=serial, capture=True).split()]
    return format(sum(1 << cpu for cpu, f in enumerate(freqs) if f == max(freqs)), "x")


def timed(command: str, serial: str | None) -> tuple[float, str]:
    start = time.perf_counter()
    output = adb("shell", command, serial=serial, capture=True)
    return time.perf_counter() - start, output.strip().splitlines()[-1] if output.strip() else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tap", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--ndk", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--serial")
    parser.add_argument("--threads", default="1,8")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-push", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    programs = {"replay": args.work / "replay", "oracle-neon": args.work / "oracle-neon",
                "oracle-none": args.work / "oracle-none"}
    if not args.skip_build:
        shutil.copyfile(build_replay(args.ndk), programs["replay"])
        build_oracle(args.ndk, args.sdist, args.work, neon=True)
        build_oracle(args.ndk, args.sdist, args.work, neon=False)
    if not args.skip_push:
        staged = stage_tap(args.tap, args.work, args.limit)
        adb("shell", f"rm -rf {REMOTE} && mkdir -p {REMOTE}/out", serial=args.serial)
        adb("push", str(staged), f"{REMOTE}/", serial=args.serial)
        for name, path in programs.items():
            adb("push", str(path), f"{REMOTE}/{name}", serial=args.serial)
        adb("shell", f"chmod 755 {REMOTE}/replay {REMOTE}/oracle-neon {REMOTE}/oracle-none", serial=args.serial)
    model = adb("shell", "getprop ro.product.model", serial=args.serial, capture=True).strip()
    mask = fast_core_mask(args.serial)
    print(f"phone: {model}; one-thread runs pinned to cores {mask} (taskset mask)")
    rows = []
    for threads in (int(t) for t in args.threads.split(",")):
        pin = f"taskset {mask} " if threads == 1 else ""
        seconds, last = timed(f"cd {REMOTE} && {pin}./replay tap --threads {threads}", args.serial)
        rows.append((f"Rust port, {threads} thread(s)", seconds, last))
    for name in ("oracle-neon", "oracle-none"):
        seconds, last = timed(f"cd {REMOTE} && taskset {mask} ./{name} tap/manifest.txt", args.serial)
        rows.append((f"Arm astcenc {name.removeprefix('oracle-')}, 1 thread", seconds, last))
    for label, seconds, last in rows:
        print(f"{label:<32} {seconds:8.1f} s   {last}")
    if args.clean:
        adb("shell", f"rm -rf {REMOTE}", serial=args.serial)


if __name__ == "__main__":
    main()
