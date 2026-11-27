//! Symbolic to physical block packing (`astcenc_symbolic_physical.cpp`), the compressor's half.

use crate::integer_sequence::{encode_ise, get_ise_sequence_bitcount};
use crate::internal::*;
use crate::tables::{COLOR_UQUANT_TO_SCRAMBLED_PQUANT, QUANT_AND_XFER_TABLES};
use crate::vecmath::f2i;

#[inline]
fn bitrev8(mut p: i32) -> i32 {
    p = ((p & 0x0F) << 4) | ((p >> 4) & 0x0F);
    p = ((p & 0x33) << 2) | ((p >> 2) & 0x33);
    ((p & 0x55) << 1) | ((p >> 1) & 0x55)
}

/// `write_bits` on a buffer with one byte of slack past the block (the C++ touches it with a
/// no-op mask when a field ends on the last byte).
fn write_bits(value: i32, bitcount: i32, bitoffset: i32, ptr: &mut [u8; 17]) {
    let mut mask = (1i32 << bitcount) - 1;
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

fn quantize_weight(uqw: u8, levels: f32) -> usize {
    let qw = (uqw as f32 / 64.0) * (levels - 1.0);
    f2i(qw + 0.5) as usize
}

pub fn symbolic_to_physical(
    bsd: &BlockSizeDescriptor,
    scb: &SymbolicCompressedBlock,
    out: &mut [u8; 16],
) {
    let _prof = crate::prof::span(13);
    if scb.block_type == SYM_BTYPE_CONST_U16 || scb.block_type == SYM_BTYPE_CONST_F16 {
        let second = if scb.block_type == SYM_BTYPE_CONST_U16 {
            0xFD
        } else {
            0xFF
        };
        out[..8].copy_from_slice(&[0xFC, second, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]);
        for i in 0..BLOCK_MAX_COMPONENTS {
            let c = scb.constant_color(i);
            out[2 * i + 8] = (c & 0xFF) as u8;
            out[2 * i + 9] = ((c >> 8) & 0xFF) as u8;
        }
        return;
    }
    let partition_count = scb.partition_count as i32;
    let mut weightbuf = [0u8; 20];
    let bm = bsd.get_block_mode(scb.block_mode as u32);
    let di = bsd.get_decimation_info(bm.decimation_mode as u32);
    let weight_count = di.weight_count as usize;
    let wq = bm.get_weight_quant_mode();
    let levels = get_quant_level(wq) as f32;
    let qat = &QUANT_AND_XFER_TABLES[wq];
    let real_weight_count = if bm.is_dual_plane {
        2 * weight_count
    } else {
        weight_count
    };
    let bits_for_weights = get_ise_sequence_bitcount(real_weight_count as u32, wq) as i32;
    let mut weights = [0u8; 64];
    for i in 0..weight_count {
        if bm.is_dual_plane {
            weights[2 * i] = qat.scramble_map[quantize_weight(scb.weights[i], levels)];
            weights[2 * i + 1] =
                qat.scramble_map[quantize_weight(scb.weights[i + WEIGHTS_PLANE2_OFFSET], levels)];
        } else {
            weights[i] = qat.scramble_map[quantize_weight(scb.weights[i], levels)];
        }
    }
    encode_ise(wq, real_weight_count as u32, &weights, &mut weightbuf, 0);
    let mut pcb = [0u8; 17];
    for i in 0..16 {
        pcb[i] = bitrev8(weightbuf[15 - i] as i32) as u8;
    }
    write_bits(scb.block_mode as i32, 11, 0, &mut pcb);
    write_bits(partition_count - 1, 2, 11, &mut pcb);
    let mut below_weights_pos = 128 - bits_for_weights;
    let pib = PARTITION_INDEX_BITS as i32;
    if partition_count > 1 {
        write_bits(scb.partition_index as i32, 6, 13, &mut pcb);
        write_bits((scb.partition_index >> 6) as i32, pib - 6, 19, &mut pcb);
        if scb.color_formats_matched != 0 {
            write_bits((scb.color_formats[0] as i32) << 2, 6, 13 + pib, &mut pcb);
        } else {
            let fmts = &scb.color_formats[..partition_count as usize];
            let mut low_class = fmts.iter().fold(4, |m, &f| m.min((f >> 2) as i32));
            if low_class == 3 {
                low_class = 2;
            }
            let mut encoded_type = low_class + 1;
            let mut bitpos = 2;
            for &f in fmts {
                encoded_type |= (((f >> 2) as i32) - low_class) << bitpos;
                bitpos += 1;
            }
            for &f in fmts {
                encoded_type |= ((f & 3) as i32) << bitpos;
                bitpos += 2;
            }
            let high_size = 3 * partition_count - 4;
            let high_pos = 128 - bits_for_weights - high_size;
            write_bits(encoded_type & 0x3F, 6, 13 + pib, &mut pcb);
            write_bits(encoded_type >> 6, high_size, high_pos, &mut pcb);
            below_weights_pos -= high_size;
        }
    } else {
        write_bits(scb.color_formats[0] as i32, 4, 13, &mut pcb);
    }
    if bm.is_dual_plane {
        write_bits(
            scb.plane2_component as i32,
            2,
            below_weights_pos - 2,
            &mut pcb,
        );
    }
    let mut values = [0u8; 32];
    let mut count = 0;
    let pack_table = &COLOR_UQUANT_TO_SCRAMBLED_PQUANT[scb.quant_mode - QUANT_6];
    for i in 0..partition_count as usize {
        let vals = 2 * (scb.color_formats[i] >> 2) as usize + 2;
        for j in 0..vals {
            values[count + j] = pack_table[scb.color_values[i][j] as usize];
        }
        count += vals;
    }
    let offset = if partition_count == 1 {
        17
    } else {
        19 + PARTITION_INDEX_BITS
    };
    encode_ise(scb.quant_mode, count as u32, &values, &mut pcb, offset);
    out.copy_from_slice(&pcb[..16]);
}
