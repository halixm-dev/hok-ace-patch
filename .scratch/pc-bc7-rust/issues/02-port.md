# Implement and compare native mode 7

Status: resolved

Depends on ticket 01 for reference outputs.

1. Implement mode 7 in a small Rust crate with fixed-size arrays for the 16 pixels, subsets, endpoints and indices. Validate the Python input length. Keep per-call work local. Convert input to packed bytes only when the existing encoder reaches mode 7.
2. Match the reference's partition and anchor tables, stable ranking of 64 partitions, first four fits, alpha weighting, endpoint refinement and strict first-winner ties. Follow Python 3.12 floating-point summation and quantization behavior. Pack exactly 128 bits, least significant bit first, including both shortened anchor indices. [Reference implementation](../../../tools/bc7_mode6.py)
3. Compare native and Python mode 7 bytes on every ticket 01 input plus deterministic randomized blocks. Decode with `texture2ddecoder` through the existing RGBA conversion. Compare the final `encode_block` output too. Exercise both backends and invalid lengths. On a mismatch, report the input, partition and first differing byte before optimizing further.
4. Run the unprofiled corpus with the release extension, including Python call, packing and decode overhead. Report actual speedup. Fivefold is the working hypothesis. Use a fresh full-build measurement to decide whether the benefit warrants shipping.

Deliver the crate, Python adapter, parity check and exact reproduction commands. Keep the Python path usable when the optional extension is absent. Surface errors from a loaded encoder.
