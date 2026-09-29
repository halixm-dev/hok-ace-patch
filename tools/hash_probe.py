from __future__ import annotations


MASK = (1 << 64) - 1
P1 = 11400714785074694791
P2 = 14029467366897019727
P3 = 1609587929392839161
P4 = 9650029242287828579
P5 = 2870177450012600261


def rol(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (64 - bits))) & MASK


def round64(acc: int, lane: int) -> int:
    acc = (acc + lane * P2) & MASK
    acc = rol(acc, 31)
    return (acc * P1) & MASK


def merge(acc: int, value: int) -> int:
    acc ^= round64(0, value)
    return (acc * P1 + P4) & MASK


def xxh64(data: bytes, seed: int = 0) -> int:
    import struct

    n = len(data)
    pos = 0
    if n >= 32:
        v1 = (seed + P1 + P2) & MASK
        v2 = (seed + P2) & MASK
        v3 = seed & MASK
        v4 = (seed - P1) & MASK
        while pos <= n - 32:
            v1 = round64(v1, struct.unpack_from("<Q", data, pos)[0])
            v2 = round64(v2, struct.unpack_from("<Q", data, pos + 8)[0])
            v3 = round64(v3, struct.unpack_from("<Q", data, pos + 16)[0])
            v4 = round64(v4, struct.unpack_from("<Q", data, pos + 24)[0])
            pos += 32
        value = (rol(v1, 1) + rol(v2, 7) + rol(v3, 12) + rol(v4, 18)) & MASK
        value = merge(value, v1)
        value = merge(value, v2)
        value = merge(value, v3)
        value = merge(value, v4)
    else:
        value = (seed + P5) & MASK
    value = (value + n) & MASK
    while pos <= n - 8:
        lane = round64(0, struct.unpack_from("<Q", data, pos)[0])
        value ^= lane
        value = (rol(value, 27) * P1 + P4) & MASK
        pos += 8
    if pos <= n - 4:
        value ^= struct.unpack_from("<I", data, pos)[0] * P1
        value = (rol(value, 23) * P2 + P3) & MASK
        pos += 4
    while pos < n:
        value ^= data[pos] * P5
        value = rol(value, 11) * P1 & MASK
        pos += 1
    value ^= value >> 33
    value = value * P2 & MASK
    value ^= value >> 29
    value = value * P3 & MASK
    value ^= value >> 32
    return value
