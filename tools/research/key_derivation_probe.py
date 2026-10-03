"""Measure what a QtsVFS package's two lookup keys depend on.

A package orders two B-trees: its index by each entry's key (record +12), and its shard by each chunk's
``hash1`` (slot +12). This compares two packages for the same id — a source copy and one Tencent's
builder re-laid-out from the same assets — and classifies every asset they share by what changed and
whether its keys moved. Content is compared after decompression through ``qts_relocate.read_raw``, so a
re-compression is not mistaken for an edit.

Measured on the ``3914DBBFECD1E54D`` cycle, ``work/prime/1`` against ``work/rebuild-1/out/1``, over the
679 assets both hold:

===========================  ======  ===============
what changed                  assets  keys identical
===========================  ======  ===============
content bytes                     677              664
byte length                       653              640
chunk count                        13               13
===========================  ======  ===============

The entry key moved for none of the 679, including ``C779022CBA18BDBE`` re-chunked from 146 chunks to
153, and ``0058049528CF2027``, whose content grew 47,973 -> 52,795 bytes, kept every ``hash1``. So an
entry key varies only with the asset it names and a chunk's ``hash1`` only with the asset and the chunk
index; neither depends on the content, the stored framing, the byte length, the chunk size or the chunk
count. ``--survey`` measures the same independence across every package of a dump.

Neither function is named, and neither needs to be: being identity functions, both are recoverable from
data rather than computed.

The keys are not all a record carries. ``--record`` byte-diffs the record two packages hold for one
asset. On the append pass's own asset, ``7B4CC5DF48336D2D`` — the one catalog edit living only in the
APK's package ``21`` — the builder's minted record and the prime package's shipped record agree on
everything except the record's own offset, which is positional, and the 16 bytes at ``+52..+67``: same
entry key, same chunk ``0`` ``hash1``, one chunk, the same declared size, chunk size and flag, while the
content is entirely different. Those 16 bytes are the one content-derived field, and no stdlib digest
(MD5, SHA-1 and SHA-256 truncated to 16, BLAKE2b-16, BLAKE2s-16) named them.

``--stager`` settles whether that costs a harvest anything, by measuring what the shipped in-place stager
changes in a record. On session ``20260929-191327`` — a real run, ``mode: full``, status ``verified``,
whose staged package went to a phone — package ``1``'s source and staged indexes over their 381 shared
entries differ in exactly two fields: the raw length at ``+44``, 99 records, and the chunk size at
``+80``, 11 of those. The token at ``+52..+67`` moved in none of the 99, including the 70 whose content
was replaced outright. So the game loads an entry whose token does not describe its content, and a
harvested record matches a builder-minted one in every field the stager itself writes.

usage:
  python tools/research/key_derivation_probe.py <source-package-dir> <built-package-dir>
  python tools/research/key_derivation_probe.py <source-package-dir> <built-package-dir> --record <hash>
  python tools/research/key_derivation_probe.py <source-package-dir> <staged-package-dir> --stager
  python tools/research/key_derivation_probe.py --survey <root-holding-package-dirs>
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "resources" / "runtime"), str(ROOT / "tools")]

from wxq_patch.qtsvfs import QtsPackage  # noqa: E402

from qts_relocate import Shard, install_btree_slot_map, read_raw  # noqa: E402

RECORD_SIZE = 92
PAGE = 0x1000


def _index_key(index: bytes, entry) -> int:
    return struct.unpack_from("<I", index, entry.entry_offset + 12)[0]


def load(package_dir: Path):
    """(package, slot map, {file_hash: entry key}) for a package holding <id>.db beside its shard."""
    package = QtsPackage(package_dir)
    slots = package.build_slot_map()
    index = (package_dir / f"{package_dir.name}.db").read_bytes()
    keys = {file_hash: _index_key(index, entry) for file_hash, entry in package.entries.items()
            if entry.entry_size == RECORD_SIZE}
    return package, slots, keys


def compare(source_dir: Path, built_dir: Path) -> None:
    source, source_slots, source_keys = load(source_dir)
    built, built_slots, built_keys = load(built_dir)
    common = sorted(set(source_keys) & set(built_keys))
    print(f"source: {source_dir}")
    print(f"built:  {built_dir}")
    print(f"assets in both: {len(common)}  (source {len(source_keys)}, built {len(built_keys)})\n")

    content_changed = 0
    content_changed_keys_same = 0
    length_changed = 0
    length_changed_keys_same = 0
    rechunked = 0
    rechunked_shared_ids_all_match = 0
    entry_key_moved = 0
    unreadable = 0
    examples: list[str] = []

    for file_hash in common:
        raw_source = read_raw(source, source_slots, file_hash)
        raw_built = read_raw(built, built_slots, file_hash)
        if raw_source is None or raw_built is None:
            unreadable += 1
            continue
        chunks_source = source_slots.get(file_hash, {})
        chunks_built = built_slots.get(file_hash, {})
        shared = set(chunks_source) & set(chunks_built)
        ids_and_keys_match = (set(chunks_source) == set(chunks_built)
                              and all(chunks_source[c].hash1 == chunks_built[c].hash1 for c in shared))
        if source_keys[file_hash] != built_keys[file_hash]:
            entry_key_moved += 1

        if raw_source != raw_built:
            content_changed += 1
            if ids_and_keys_match:
                content_changed_keys_same += 1
            if len(raw_source) != len(raw_built):
                length_changed += 1
                if ids_and_keys_match:
                    length_changed_keys_same += 1
                if len(examples) < 5:
                    examples.append(f"    {file_hash:016X}  {len(raw_source)} -> {len(raw_built)} bytes, "
                                    f"entry key {'moved' if source_keys[file_hash] != built_keys[file_hash] else 'same'}")
        if set(chunks_source) != set(chunks_built):
            rechunked += 1
            if shared and all(chunks_source[c].hash1 == chunks_built[c].hash1 for c in shared):
                rechunked_shared_ids_all_match += 1

    print("content differs after decompression:      ", content_changed)
    print("  ...of which every key is identical:     ", content_changed_keys_same)
    print("byte length differs:                      ", length_changed)
    print("  ...of which every key is identical:     ", length_changed_keys_same)
    print("chunk count differs (re-chunked):         ", rechunked)
    print("  ...of which every shared id kept hash1: ", rechunked_shared_ids_all_match)
    print("entry key moved:                          ", entry_key_moved)
    if unreadable:
        print("unreadable on one side:                   ", unreadable)
    for line in examples:
        print(line)
    print("\nA key that never moves as the content and the chunking change does not depend on either.")


def survey(root: Path) -> None:
    """The same independence across every package under <root>, plus the shard's own key mapping."""
    assets = chunks = multi = hash1_varies = entry_key_not_a_half = 0
    leaf_keys = leaf_keys_matching = slot_lows = no_shard = 0
    histogram: Counter[int] = Counter()
    for package_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (package_dir / f"{package_dir.name}.db").is_file():
            continue
        try:
            package, slots, keys = load(package_dir)
        except Exception as error:  # noqa: BLE001 - a package this probe cannot read is not a finding
            print(f"{package_dir.name}: index unreadable ({type(error).__name__}: {error})")
            continue
        shard = None
        if package.shard_paths:
            try:
                shard = Shard(package.shard_paths[0])
            except Exception as error:  # noqa: BLE001
                print(f"{package_dir.name}: shard unreadable ({type(error).__name__}: {error})")
        else:
            no_shard += 1
        if shard is not None:
            live = set()
            for page in shard.leaves:
                count = shard._u32(page + PAGE - 4) & 0xFFFF
                live.update(struct.unpack_from(f"<{count}I", shard.data, page))
            lows = {slot.hash1 & 0xFFFFFFFF for chunks_ in slots.values() for slot in chunks_.values()}
            leaf_keys += len(live)
            leaf_keys_matching += len(live & lows)
            slot_lows += len(lows)

        for file_hash, entry_key in keys.items():
            chunks_ = slots.get(file_hash)
            if not chunks_:
                continue
            assets += 1
            chunks += len(chunks_)
            histogram[len(chunks_)] += 1
            halves = {slot.hash1 & 0xFFFFFFFF for slot in chunks_.values()} | {slot.hash1 >> 32 for slot in chunks_.values()}
            if entry_key not in halves:
                entry_key_not_a_half += 1
            if len(chunks_) > 1:
                multi += 1
                if len({slot.hash1 for slot in chunks_.values()}) > 1:
                    hash1_varies += 1

    print(f"packages surveyed: {len(list(root.iterdir()))}, assets {assets}, chunks {chunks}")
    if no_shard:
        print(f"packages with an index but no shard: {no_shard}")
    print(f"multi-chunk assets: {multi}")
    print(f"  ...whose hash1 differs per chunk:     {hash1_varies}")
    print(f"assets whose entry key is no hash1 half: {entry_key_not_a_half}  (of {assets})")
    print(f"shard leaf keys: {leaf_keys}, of which a slot's hash1 low word: {leaf_keys_matching}")
    print(f"distinct slot hash1 low words: {slot_lows}")
    print("\nchunks-per-asset histogram (top 10):")
    for count, times in histogram.most_common(10):
        print(f"  {count:4d}: {times}")


def record_diff(source_dir: Path, built_dir: Path, file_hash: int) -> None:
    """Every field the two packages' records for <file_hash> disagree on."""
    source, built = QtsPackage(source_dir), QtsPackage(built_dir)
    source_slots, built_slots = source.build_slot_map(), built.build_slot_map()
    for label, package, package_dir in (("source", source, source_dir), ("built ", built, built_dir)):
        if file_hash not in package.entries:
            print(f"{label} {package_dir.name}: {file_hash:016X} is absent")
            return
    source_record = (source_dir / f"{source_dir.name}.db").read_bytes()
    built_record = (built_dir / f"{built_dir.name}.db").read_bytes()
    source_entry = source.entries[file_hash].entry_offset
    built_entry = built.entries[file_hash].entry_offset

    print(f"record for {file_hash:016X}, {RECORD_SIZE} bytes")
    print("  offset   source      built       note")
    differing = []
    for offset in range(0, RECORD_SIZE, 4):
        left = struct.unpack_from("<I", source_record, source_entry + offset)[0]
        right = struct.unpack_from("<I", built_record, built_entry + offset)[0]
        if left != right:
            differing.append(offset)
            print(f"    +{offset:02d}    {left:08X}    {right:08X}    <-- differs")
    print(f"  differing u32 offsets: {differing}")

    for label, slots in (("source", source_slots), ("built ", built_slots)):
        chunks = sorted(slots.get(file_hash, {}).items())
        print(f"  {label} chunks: {len(chunks)}  " +
              "  ".join(f"id {cid} hash1={slot.hash1:016X} raw={slot.uncompressed_size}"
                        for cid, slot in chunks[:4]))
    raw_source = read_raw(source, source_slots, file_hash)
    raw_built = read_raw(built, built_slots, file_hash)
    same = raw_source == raw_built
    print(f"  content: source {len(raw_source)} bytes, built {len(raw_built)} bytes, "
          f"{'identical' if same else 'DIFFERENT'}")
    print("\nA record that agrees on every key while its content differs leaves only the listed fields"
          "\nto be supplied by something other than a harvest.")


def stager_changes(source_dir: Path, staged_dir: Path) -> None:
    """Which record fields the shipped in-place stager changes, and whether the token moves.

    <source-dir> is a package as pulled from the device and <staged-dir> the copy the same run staged
    and pushed. Answers what nothing else here can: the device-observed extra-text assets all live in
    package ``1``, which is rebuilt, so those cycles ran the builder, which recomputes the token.
    """
    source, staged = QtsPackage(source_dir), QtsPackage(staged_dir)
    source_slots, staged_slots = source.build_slot_map(), staged.build_slot_map()
    source_index = (source_dir / f"{source_dir.name}.db").read_bytes()
    staged_index = (staged_dir / f"{staged_dir.name}.db").read_bytes()

    names = {0: "record's own offset", 8: "record size", 12: "ENTRY KEY", 28: "flag A", 32: "flag B",
             36: "file hash", 44: "raw length", 52: "TOKEN bytes 1-4", 56: "TOKEN bytes 5-8",
             60: "TOKEN bytes 9-12", 64: "TOKEN bytes 13-16", 68: "?", 76: "compression",
             80: "chunk size", 84: "file hash again"}
    common = sorted(set(source.entries) & set(staged.entries))
    identical = changed = token_moved = token_kept = content_changed = content_changed_token_kept = 0
    counter: Counter[int] = Counter()
    for file_hash in common:
        source_entry, staged_entry = source.entries[file_hash], staged.entries[file_hash]
        if source_entry.entry_size != RECORD_SIZE or staged_entry.entry_size != RECORD_SIZE:
            continue
        left = source_index[source_entry.entry_offset:source_entry.entry_offset + RECORD_SIZE]
        right = staged_index[staged_entry.entry_offset:staged_entry.entry_offset + RECORD_SIZE]
        if left == right:
            identical += 1
            continue
        changed += 1
        for offset in range(0, RECORD_SIZE, 4):
            if left[offset:offset + 4] != right[offset:offset + 4]:
                counter[offset] += 1
        kept = left[52:68] == right[52:68]
        token_kept += kept
        token_moved += not kept
        if read_raw(source, source_slots, file_hash) != read_raw(staged, staged_slots, file_hash):
            content_changed += 1
            content_changed_token_kept += kept

    print(f"source {source_dir.name}: {len(source.entries)} entries")
    print(f"staged {staged_dir.name}: {len(staged.entries)} entries")
    print(f"in both: {len(common)}  identical records: {identical}  changed: {changed}\n")
    print("field                 records changed")
    for offset, count in sorted(counter.items()):
        print(f"  +{offset:02d} {names.get(offset, '?'):<18} {count}")
    print(f"\n  token at +52..+67 moved: {token_moved}   kept: {token_kept}")
    print(f"  content differs: {content_changed}, of which the token was kept: {content_changed_token_kept}")
    print("\nA token the stager never updates is a token the game does not check against the content,\n"
          "so a record harvested from another package is a whole record.")


def main() -> None:
    install_btree_slot_map()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", nargs="?", type=Path, help="source package directory")
    parser.add_argument("built", nargs="?", type=Path, help="package directory built from it")
    parser.add_argument("--survey", type=Path, help="survey every package under this root instead")
    parser.add_argument("--record", help="byte-diff the record both hold for this asset hash")
    parser.add_argument("--stager", action="store_true",
                        help="report which record fields the in-place stager changed")
    args = parser.parse_args()
    if args.survey:
        survey(args.survey)
    elif args.source and args.built and args.stager:
        stager_changes(args.source, args.built)
    elif args.source and args.built and args.record:
        record_diff(args.source, args.built, int(args.record, 16))
    elif args.source and args.built:
        compare(args.source, args.built)
    else:
        parser.error("give <source-package-dir> <built-package-dir> [--record <hash> | --stager], "
                     "or --survey <root>")


if __name__ == "__main__":
    main()
