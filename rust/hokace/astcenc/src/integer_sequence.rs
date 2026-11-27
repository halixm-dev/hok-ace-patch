//! Bounded integer sequence encoding (`astcenc_integer_sequence.cpp`).

use crate::tables::{INTEGER_OF_QUINTS, INTEGER_OF_TRITS, QUINTS_OF_INTEGER, TRITS_OF_INTEGER};

/// Bits, trits and quints per quant level.
const BTQ_COUNTS: [(u32, bool, bool); 21] = [
    (1, false, false),
    (0, true, false),
    (2, false, false),
    (0, false, true),
    (1, true, false),
    (3, false, false),
    (1, false, true),
    (2, true, false),
    (4, false, false),
    (2, false, true),
    (3, true, false),
    (5, false, false),
    (3, false, true),
    (4, true, false),
    (6, false, false),
    (4, false, true),
    (5, true, false),
    (7, false, false),
    (5, false, true),
    (6, true, false),
    (8, false, false),
];

/// Scale and divisor per quant level.
const ISE_SIZES: [(u32, u32); 21] = [
    (1, 0),
    (8, 2),
    (2, 0),
    (7, 1),
    (13, 2),
    (3, 0),
    (10, 1),
    (18, 2),
    (4, 0),
    (13, 1),
    (23, 2),
    (5, 0),
    (16, 1),
    (28, 2),
    (6, 0),
    (19, 1),
    (33, 2),
    (7, 0),
    (22, 1),
    (38, 2),
    (8, 0),
];

pub fn get_ise_sequence_bitcount(character_count: u32, quant_level: usize) -> u32 {
    if quant_level >= ISE_SIZES.len() {
        return 1024;
    }
    let (scale, divisor) = ISE_SIZES[quant_level];
    let divisor = (divisor << 1) + 1;
    (scale * character_count).div_ceil(divisor)
}

/// Writes into `ptr[off/8]` and the byte after it; `ptr` must reach one byte past the last bit.
#[inline]
fn write_bits(value: u32, bitcount: u32, bitoffset: u32, ptr: &mut [u8]) {
    let mut mask = (1u32 << bitcount) - 1;
    let mut value = value & mask;
    let p = (bitoffset >> 3) as usize;
    let bitoffset = bitoffset & 7;
    value <<= bitoffset;
    mask <<= bitoffset;
    mask = !mask;
    ptr[p] &= mask as u8;
    ptr[p] |= value as u8;
    ptr[p + 1] &= (mask >> 8) as u8;
    ptr[p + 1] |= (value >> 8) as u8;
}

#[inline]
fn read_bits(bitcount: u32, bitoffset: u32, ptr: &[u8]) -> u32 {
    let mask = (1u32 << bitcount) - 1;
    let p = (bitoffset >> 3) as usize;
    let bitoffset = bitoffset & 7;
    let value = ptr[p] as u32 | ((*ptr.get(p + 1).unwrap_or(&0) as u32) << 8);
    (value >> bitoffset) & mask
}

#[inline]
fn trit_index(i4: u32, i3: u32, i2: u32, i1: u32, i0: u32) -> usize {
    ((((i4 * 3 + i3) * 3 + i2) * 3 + i1) * 3 + i0) as usize
}

pub fn encode_ise(
    quant_level: usize,
    character_count: u32,
    input: &[u8],
    output: &mut [u8],
    mut bit_offset: u32,
) {
    let (bits, trits, quints) = BTQ_COUNTS[quant_level];
    let mask = (1u32 << bits) - 1;
    let n = character_count as usize;
    let inp = |i: usize| input[i] as u32;
    if trits {
        let mut i = 0usize;
        for _ in 0..n / 5 {
            let t = INTEGER_OF_TRITS[trit_index(
                inp(i + 4) >> bits,
                inp(i + 3) >> bits,
                inp(i + 2) >> bits,
                inp(i + 1) >> bits,
                inp(i) >> bits,
            )] as u32;
            for (shift, tb) in [(0u32, 2u32), (2, 2), (4, 1), (5, 2), (7, 1)] {
                let pack = (inp(i) & mask) | (((t >> shift) & ((1 << tb) - 1)) << bits);
                write_bits(pack & 0xFF, bits + tb, bit_offset, output);
                bit_offset += bits + tb;
                i += 1;
            }
        }
        if i != n {
            let i3 = if i + 3 >= n { 0 } else { inp(i + 3) >> bits };
            let i2 = if i + 2 >= n { 0 } else { inp(i + 2) >> bits };
            let i1 = if i + 1 >= n { 0 } else { inp(i + 1) >> bits };
            let i0 = inp(i) >> bits;
            let t = INTEGER_OF_TRITS[trit_index(0, i3, i2, i1, i0)] as u32;
            const TBITS: [u32; 4] = [2, 2, 1, 2];
            const TSHIFT: [u32; 4] = [0, 2, 4, 5];
            let mut j = 0;
            while i < n {
                let pack = (inp(i) & mask) | (((t >> TSHIFT[j]) & ((1 << TBITS[j]) - 1)) << bits);
                write_bits(pack & 0xFF, bits + TBITS[j], bit_offset, output);
                bit_offset += bits + TBITS[j];
                i += 1;
                j += 1;
            }
        }
    } else if quints {
        let mut i = 0usize;
        for _ in 0..n / 3 {
            let t = INTEGER_OF_QUINTS[(((inp(i + 2) >> bits) * 5 + (inp(i + 1) >> bits)) * 5
                + (inp(i) >> bits)) as usize] as u32;
            for (shift, tb) in [(0u32, 3u32), (3, 2), (5, 2)] {
                let pack = (inp(i) & mask) | (((t >> shift) & ((1 << tb) - 1)) << bits);
                write_bits(pack & 0xFF, bits + tb, bit_offset, output);
                bit_offset += bits + tb;
                i += 1;
            }
        }
        if i != n {
            let i1 = if i + 1 >= n { 0 } else { inp(i + 1) >> bits };
            let i0 = inp(i) >> bits;
            let t = INTEGER_OF_QUINTS[(i1 * 5 + i0) as usize] as u32;
            const TBITS: [u32; 2] = [3, 2];
            const TSHIFT: [u32; 2] = [0, 3];
            let mut j = 0;
            while i < n {
                let pack = (inp(i) & mask) | (((t >> TSHIFT[j]) & ((1 << TBITS[j]) - 1)) << bits);
                write_bits(pack & 0xFF, bits + TBITS[j], bit_offset, output);
                bit_offset += bits + TBITS[j];
                i += 1;
                j += 1;
            }
        }
    } else {
        for &v in &input[..n] {
            write_bits(v as u32, bits, bit_offset, output);
            bit_offset += bits;
        }
    }
}

pub fn decode_ise(
    quant_level: usize,
    character_count: u32,
    input: &[u8],
    output: &mut [u8],
    mut bit_offset: u32,
) {
    let mut results = [0u8; 68];
    let mut tq_blocks = [0u8; 22];
    let (bits, trits, quints) = BTQ_COUNTS[quant_level];
    let mut lcounter = 0usize;
    let mut hcounter = 0usize;
    let n = character_count as usize;
    for r in results.iter_mut().take(n) {
        *r = read_bits(bits, bit_offset, input) as u8;
        bit_offset += bits;
        if trits {
            const BITS_TO_READ: [u32; 5] = [2, 2, 1, 2, 1];
            const BLOCK_SHIFT: [u32; 5] = [0, 2, 4, 5, 7];
            let tdata = read_bits(BITS_TO_READ[lcounter], bit_offset, input);
            bit_offset += BITS_TO_READ[lcounter];
            tq_blocks[hcounter] |= (tdata << BLOCK_SHIFT[lcounter]) as u8;
            if lcounter == 4 {
                hcounter += 1;
            }
            lcounter = (lcounter + 1) % 5;
        }
        if quints {
            const BITS_TO_READ: [u32; 3] = [3, 2, 2];
            const BLOCK_SHIFT: [u32; 3] = [0, 3, 5];
            let tdata = read_bits(BITS_TO_READ[lcounter], bit_offset, input);
            bit_offset += BITS_TO_READ[lcounter];
            tq_blocks[hcounter] |= (tdata << BLOCK_SHIFT[lcounter]) as u8;
            if lcounter == 2 {
                hcounter += 1;
            }
            lcounter = (lcounter + 1) % 3;
        }
    }
    if trits {
        for i in 0..n.div_ceil(5) {
            let t = TRITS_OF_INTEGER[tq_blocks[i] as usize];
            for k in 0..5 {
                results[5 * i + k] |= t[k] << bits;
            }
        }
    }
    if quints {
        for i in 0..n.div_ceil(3) {
            let q = QUINTS_OF_INTEGER[tq_blocks[i] as usize];
            for k in 0..3 {
                results[3 * i + k] |= q[k] << bits;
            }
        }
    }
    output[..n].copy_from_slice(&results[..n]);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_every_level() {
        for q in 0..21 {
            let levels = [
                2u32, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 256,
            ][q];
            for count in [1u32, 2, 3, 4, 5, 6, 7, 11, 16] {
                let values: Vec<u8> = (0..count).map(|i| ((i * 37 + 5) % levels) as u8).collect();
                let mut out = [0u8; 40];
                encode_ise(q, count, &values, &mut out, 3);
                let mut back = [0u8; 16];
                decode_ise(q, count, &out, &mut back, 3);
                assert_eq!(
                    &back[..count as usize],
                    &values[..],
                    "quant {q} count {count}"
                );
            }
        }
    }
}
