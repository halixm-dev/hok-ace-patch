from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import sys


def synthetic_metadata_builder(source_package, game_dir, assets, build_root):
    """Return QtsVFS lookup keys for an offline Android package rebuild.

    Existing chunk keys are structural lookup keys and must stay unchanged.
    Newly allocated chunks only need unique keys in the package position index;
    derive them deterministically from the asset identity and chunk number.
    """
    slot_map = source_package.build_slot_map()
    used = {slot.hash1 for chunks in slot_map.values() for slot in chunks.values()}
    reports = {}
    for asset in assets:
        file_hash = int(asset["file_hash"])
        fit = asset["fit"]
        entry = source_package.entries[file_hash]
        with source_package.index_path.open("rb") as stream:
            stream.seek(entry.entry_offset + 28)
            descriptor = bytearray(stream.read(32))
        if len(descriptor) != 32:
            raise RuntimeError(f"truncated descriptor for {file_hash:016X}")
        # Preserve the opaque integrity token produced by QtsVFS and update the
        # explicit raw-length field required for extraction.
        struct.pack_into("<I", descriptor, 16, len(asset["raw"]))
        original = slot_map[file_hash]
        chunks = []
        for chunk_id in range(len(fit["chunks"])):
            if chunk_id in original:
                hash1 = original[chunk_id].hash1
                flags = original[chunk_id].header_flags
            else:
                nonce = 0
                while True:
                    material = f"hok-ace-mobile:{file_hash:016X}:{chunk_id}:{nonce}".encode()
                    hash1 = int.from_bytes(hashlib.sha256(material).digest()[:8], "little")
                    if hash1 and hash1 not in used:
                        break
                    nonce += 1
                used.add(hash1)
                flags = 16
            chunks.append({"id": chunk_id, "hash1": f"{hash1:016X}", "header_flags": flags})
        reports[file_hash] = {
            "descriptor": bytes(descriptor),
            "official_chunks": chunks,
        }
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=pathlib.Path, required=True)
    parser.add_argument("--game", type=pathlib.Path, required=True)
    parser.add_argument("--catalog", type=pathlib.Path, required=True)
    parser.add_argument("--work", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--fit-only", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.runtime.resolve()))
    from wxq_patch import adaptive
    from wxq_patch.unity_package_installer import capacity_report, stage_unity_package

    args.work.mkdir(parents=True, exist_ok=True)
    plans, fingerprints, counts, skipped = adaptive.scan(
        args.game, args.catalog, args.work / "scan", materialize=True
    )
    if len(plans) != 1:
        raise RuntimeError(f"expected one changed package, found {len(plans)}")
    package, replacements, _per_asset = plans[0]

    fit_summary = None
    if args.fit_only:
        fit_summary = capacity_report(package.package_dir, replacements)
        allowed = {
            item["hash"]
            for item in fit_summary["assets"]
            if item["status"] != "blocked"
        }
        fit_replacements = args.work / "fit-replacements" / package.package_id
        if fit_replacements.exists():
            shutil.rmtree(fit_replacements)
        fit_replacements.mkdir(parents=True)
        for path in replacements.glob("*.assets"):
            if path.stem.upper() in allowed:
                shutil.copy2(path, fit_replacements / path.name)
        replacements = fit_replacements

    source_hashes = {
        path.name: fingerprints[str(path.relative_to(args.game))]
        for path in [package.index_path, *package.shard_paths]
    }

    def builder(game_dir, assets, build_root):
        return synthetic_metadata_builder(package, game_dir, assets, build_root)

    report = stage_unity_package(
        args.game,
        replacements,
        args.output,
        source_package_dir=package.package_dir,
        metadata_builder=builder,
        verify_all_unrelated=False,
        global_donations=not args.fit_only,
        source_hashes=source_hashes,
    )
    summary = {
        "counts": dict(counts),
        "skipped_count": len(skipped),
        "package_id": package.package_id,
        "source_package": str(package.package_dir),
        "fit_only": args.fit_only,
        "fit_summary": fit_summary,
        "stage_report": report,
    }
    (args.output / "mobile_patch_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps({"counts": summary["counts"], "stage": report}, indent=2))


if __name__ == "__main__":
    main()
