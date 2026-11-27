//! Trial-block error measures (`astcenc_decompress_symbolic.cpp`): `unpack_weights` and the
//! `compute_symbolic_block_difference_*` functions, without the RGBM mapping (flags stay 0).

use crate::color_unquantize::unpack_color_endpoints;
use crate::internal::*;
use crate::vecmath::*;

#[inline]
fn lerp_color_int(u8_mask: VMask4, color0: VInt4, color1: VInt4, weights: VInt4) -> VInt4 {
    let weight1 = weights;
    let weight0 = VInt4::splat(64) - weight1;
    let color = ((color0 * weight0) + (color1 * weight1) + VInt4::splat(32)).asr(6);
    let color_u8 = color.asr(8) * VInt4::splat(257);
    select_i(color, color_u8, u8_mask)
}

#[inline]
fn lookup(table: &[u8], idx: VInt4) -> VInt4 {
    VInt4::new(
        table[idx.lane(0) as usize] as i32,
        table[idx.lane(1) as usize] as i32,
        table[idx.lane(2) as usize] as i32,
        table[idx.lane(3) as usize] as i32,
    )
}

pub fn unpack_weights(
    bsd: &BlockSizeDescriptor,
    scb: &SymbolicCompressedBlock,
    di: &DecimationInfo,
    is_dual_plane: bool,
    weights_plane1: &mut [i32; BLOCK_MAX_TEXELS],
    weights_plane2: &mut [i32; BLOCK_MAX_TEXELS],
) {
    let texel_count = bsd.texel_count as usize;
    let mut i = 0;
    while i < texel_count {
        let mut sum_plane1 = VInt4::splat(8);
        let mut sum_plane2 = VInt4::splat(8);
        let max_weight_count = hmax_s_i(VInt4::from_u8(&di.texel_weight_count[i..])) as usize;
        for j in 0..max_weight_count {
            let texel_weights = VInt4::from_u8(&di.texel_weights_tr[j][i..]);
            let texel_weights_int = VInt4::from_u8(&di.texel_weight_contribs_int_tr[j][i..]);
            if is_dual_plane {
                sum_plane1 += lookup(&scb.weights[..32], texel_weights) * texel_weights_int;
                sum_plane2 += lookup(&scb.weights[32..], texel_weights) * texel_weights_int;
            } else {
                sum_plane1 += lookup(&scb.weights, texel_weights) * texel_weights_int;
            }
        }
        sum_plane1.lsr(4).store(&mut weights_plane1[i..]);
        if is_dual_plane {
            sum_plane2.lsr(4).store(&mut weights_plane2[i..]);
        }
        i += SIMD_WIDTH;
    }
}

#[inline]
fn texel_error(blk: &ImageBlock, i: usize, colori: VInt4) -> VFloat4 {
    let error = blk.texel(i) - int_to_float(colori);
    let error = min_s(abs(error), 1e15);
    let error = error * error;
    min_s(dot(error, blk.channel_weight), ERROR_CALC_DEFAULT)
}

pub fn compute_symbolic_block_difference_2plane(
    config: &Config,
    bsd: &BlockSizeDescriptor,
    scb: &SymbolicCompressedBlock,
    blk: &ImageBlock,
) -> f32 {
    let _prof = crate::prof::span(8);
    if scb.block_type == SYM_BTYPE_ERROR {
        return ERROR_CALC_DEFAULT;
    }
    let bm = bsd.get_block_mode(scb.block_mode as u32);
    let di = bsd.get_decimation_info(bm.decimation_mode as u32);
    let mut plane1_weights = [0i32; BLOCK_MAX_TEXELS];
    let mut plane2_weights = [0i32; BLOCK_MAX_TEXELS];
    unpack_weights(bsd, scb, di, true, &mut plane1_weights, &mut plane2_weights);
    let plane2_mask = VInt4::lane_id().eq(VInt4::splat(scb.plane2_component as i32));
    let mut summa = VFloat4::zero();
    let (ep0, ep1) =
        unpack_color_endpoints(config.profile, scb.color_formats[0], &scb.color_values[0]);
    let u8_mask = get_u8_component_mask(config.profile, blk);
    for i in 0..bsd.texel_count as usize {
        let weight = select_i(
            VInt4::splat(plane1_weights[i]),
            VInt4::splat(plane2_weights[i]),
            plane2_mask,
        );
        summa += texel_error(blk, i, lerp_color_int(u8_mask, ep0, ep1, weight));
    }
    summa.lane(0)
}

pub fn compute_symbolic_block_difference_1plane(
    config: &Config,
    bsd: &BlockSizeDescriptor,
    scb: &SymbolicCompressedBlock,
    blk: &ImageBlock,
) -> f32 {
    let _prof = crate::prof::span(8);
    if scb.block_type == SYM_BTYPE_ERROR {
        return ERROR_CALC_DEFAULT;
    }
    let partition_count = scb.partition_count as u32;
    let pi = bsd.get_partition_info(partition_count, scb.partition_index as u32);
    let bm = bsd.get_block_mode(scb.block_mode as u32);
    let di = bsd.get_decimation_info(bm.decimation_mode as u32);
    let mut plane1_weights = [0i32; BLOCK_MAX_TEXELS];
    let mut unused = [0i32; BLOCK_MAX_TEXELS];
    unpack_weights(bsd, scb, di, false, &mut plane1_weights, &mut unused);
    let u8_mask = get_u8_component_mask(config.profile, blk);
    let mut summa = VFloat4::zero();
    for i in 0..partition_count as usize {
        let (ep0, ep1) =
            unpack_color_endpoints(config.profile, scb.color_formats[i], &scb.color_values[i]);
        for &t in &pi.texels_of_partition[i][..pi.partition_texel_count[i] as usize] {
            let tix = t as usize;
            summa += texel_error(
                blk,
                tix,
                lerp_color_int(u8_mask, ep0, ep1, VInt4::splat(plane1_weights[tix])),
            );
        }
    }
    summa.lane(0)
}

pub fn compute_symbolic_block_difference_1plane_1partition(
    config: &Config,
    bsd: &BlockSizeDescriptor,
    scb: &SymbolicCompressedBlock,
    blk: &ImageBlock,
) -> f32 {
    let _prof = crate::prof::span(8);
    if scb.block_type == SYM_BTYPE_ERROR {
        return ERROR_CALC_DEFAULT;
    }
    let bm = bsd.get_block_mode(scb.block_mode as u32);
    let di = bsd.get_decimation_info(bm.decimation_mode as u32);
    let mut plane1_weights = [0i32; BLOCK_MAX_TEXELS];
    let mut unused = [0i32; BLOCK_MAX_TEXELS];
    unpack_weights(bsd, scb, di, false, &mut plane1_weights, &mut unused);
    let (ep0, ep1) =
        unpack_color_endpoints(config.profile, scb.color_formats[0], &scb.color_values[0]);
    let u8_mask = get_u8_component_mask(config.profile, blk);
    let mut summav = VFloat4::zero();
    let mut lane_id = VInt4::lane_id();
    let texel_count = bsd.texel_count as usize;
    let cw = blk.channel_weight;
    let mut i = 0;
    while i < texel_count {
        let weight1 = VInt4::load(&plane1_weights[i..]);
        let weight0 = VInt4::splat(64) - weight1;
        let mut metric = VFloat4::zero();
        for c in 0..4 {
            let e1 = VInt4::splat(ep1.lane(c)) * weight1;
            let e0 = VInt4::splat(ep0.lane(c)) * weight0;
            let mut colori = (e0 + e1 + VInt4::splat(32)).asr(6);
            let colori8 = colori.asr(8) * VInt4::splat(257);
            colori = select_i(colori, colori8, VMask4::splat(u8_mask.lane(c)));
            let color = int_to_float(colori);
            let orig = VFloat4::load(&blk.channel(c)[i..]);
            let err = min(abs(orig - color), VFloat4::splat(1e15));
            let term = err * err * cw.lane(c);
            metric = if c == 0 { term } else { metric + term };
        }
        let mask = lane_id.lt(VInt4::splat(texel_count as i32));
        lane_id += VInt4::splat(SIMD_WIDTH as i32);
        haccumulate_m(&mut summav, metric, mask);
        i += SIMD_WIDTH;
    }
    hadd_s(summav)
}
