"""Copy small, read-only phone benchmark receipts; never copy game payloads."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PACKAGE = "dev.halixm.hokacepatcher"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def read(*command: str, optional: bool = False) -> bytes | None:
        result = subprocess.run([args.adb, "-s", args.serial, *command],
                                capture_output=True, timeout=45)
        # exec-out's legacy shell protocol may merge stderr and return zero for cat failures.
        if optional and b"No such file" in result.stdout + result.stderr and (
            result.returncode or result.stdout.startswith(b"cat:")
        ):
            return None
        if result.returncode:
            if optional and b"No such file" in result.stderr:
                return None
            raise RuntimeError(result.stderr.decode(errors="replace"))
        return result.stdout

    def private(path: str, optional: bool = False) -> bytes | None:
        return read("exec-out", "run-as", PACKAGE, "cat", path, optional=optional)

    state_bytes = private("files/worker-state.json")
    state = json.loads(state_bytes)
    (args.output / "worker-state.json").write_bytes(state_bytes)
    with (args.output / "observed-states.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(state, ensure_ascii=False) + "\n")
    paths = read("shell", "run-as", PACKAGE, "find", "files/sessions", "-name", "journal.json")
    journals = [json.loads(private(path)) for path in paths.decode().splitlines()]
    journal = max(journals, key=lambda item: item["created_ms"])
    session = journal["id"]
    destination = args.output / session
    destination.mkdir(exist_ok=True)
    (destination / "journal.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
    metrics = None
    for name in ("resource-metrics.json", "metrics.json", "build.log", "staged-hashes.json",
                 "out/device_patch_summary.json", "snapshot/manifest.json"):
        data = private(f"files/sessions/{session}/{name}", optional=True)
        if data is not None:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if name == "resource-metrics.json":
                metrics = json.loads(data)
    trace = private("files/trace.log", optional=True)
    if trace is not None:
        (args.output / "trace.log").write_bytes(trace)
    print(json.dumps({"status": state.get("status"), "action": state.get("action"),
                      "progress": state.get("progress"), "session": session,
                      "phase": journal["phase"], "engine_id": journal.get("engine_id"),
                      "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
