//! The library entry points (`astcenc_entry.cpp`): config init, context alloc, single-thread compress.

use crate::block_sizes::{init_block_size_descriptor, is_legal_2d_block_size};
use crate::internal::*;
use crate::vecmath::{VFloat4, astc};

struct Preset {
    quality: f32,
    tune_partition_count_limit: u32,
    tune_2partition_index_limit: u32,
    tune_3partition_index_limit: u32,
    tune_4partition_index_limit: u32,
    tune_block_mode_limit: u32,
    tune_refinement_limit: u32,
    tune_candidate_limit: u32,
    tune_2partitioning_candidate_limit: u32,
    tune_3partitioning_candidate_limit: u32,
    tune_4partitioning_candidate_limit: u32,
    tune_db_limit_a_base: f32,
    tune_db_limit_b_base: f32,
    tune_mse_overshoot: f32,
    tune_2partition_early_out_limit_factor: f32,
    tune_3partition_early_out_limit_factor: f32,
    tune_2plane_early_out_limit_correlation: f32,
    tune_search_mode0_enable: f32,
}

macro_rules! p {
    ($q:expr, $a:expr, $b:expr, $c:expr, $d:expr, $e:expr, $f:expr, $g:expr, $h:expr, $i:expr, $j:expr,
     $k:expr, $l:expr, $m:expr, $n:expr, $o:expr, $pp:expr, $r:expr) => {
        Preset {
            quality: $q,
            tune_partition_count_limit: $a,
            tune_2partition_index_limit: $b,
            tune_3partition_index_limit: $c,
            tune_4partition_index_limit: $d,
            tune_block_mode_limit: $e,
            tune_refinement_limit: $f,
            tune_candidate_limit: $g,
            tune_2partitioning_candidate_limit: $h,
            tune_3partitioning_candidate_limit: $i,
            tune_4partitioning_candidate_limit: $j,
            tune_db_limit_a_base: $k,
            tune_db_limit_b_base: $l,
            tune_mse_overshoot: $m,
            tune_2partition_early_out_limit_factor: $n,
            tune_3partition_early_out_limit_factor: $o,
            tune_2plane_early_out_limit_correlation: $pp,
            tune_search_mode0_enable: $r,
        }
    };
}

pub const PRE_FASTEST: f32 = 0.0;
pub const PRE_FAST: f32 = 10.0;
pub const PRE_MEDIUM: f32 = 60.0;
pub const PRE_THOROUGH: f32 = 98.0;
pub const PRE_VERYTHOROUGH: f32 = 99.0;
pub const PRE_EXHAUSTIVE: f32 = 100.0;

static PRESET_HIGH: [Preset; 6] = [
    p!(
        PRE_FASTEST,
        2,
        10,
        6,
        4,
        43,
        2,
        2,
        2,
        2,
        2,
        85.2,
        63.2,
        3.5,
        1.0,
        1.0,
        0.85,
        0.0
    ),
    p!(
        PRE_FAST, 3, 18, 10, 8, 55, 3, 3, 2, 2, 2, 85.2, 63.2, 3.5, 1.0, 1.0, 0.90, 0.0
    ),
    p!(
        PRE_MEDIUM, 4, 34, 28, 16, 77, 3, 3, 2, 2, 2, 95.0, 70.0, 2.5, 1.1, 1.05, 0.95, 0.0
    ),
    p!(
        PRE_THOROUGH,
        4,
        82,
        60,
        30,
        94,
        4,
        4,
        3,
        2,
        2,
        105.0,
        77.0,
        10.0,
        1.35,
        1.15,
        0.97,
        0.0
    ),
    p!(
        PRE_VERYTHOROUGH,
        4,
        256,
        128,
        64,
        98,
        4,
        6,
        8,
        6,
        4,
        200.0,
        200.0,
        10.0,
        1.6,
        1.4,
        0.98,
        0.0
    ),
    p!(
        PRE_EXHAUSTIVE,
        4,
        512,
        512,
        512,
        100,
        4,
        8,
        8,
        8,
        8,
        200.0,
        200.0,
        10.0,
        2.0,
        2.0,
        0.99,
        0.0
    ),
];
static PRESET_MID: [Preset; 6] = [
    p!(
        PRE_FASTEST,
        2,
        10,
        6,
        4,
        43,
        2,
        2,
        2,
        2,
        2,
        85.2,
        63.2,
        3.5,
        1.0,
        1.0,
        0.80,
        1.0
    ),
    p!(
        PRE_FAST, 3, 18, 12, 10, 55, 3, 3, 2, 2, 2, 85.2, 63.2, 3.5, 1.0, 1.0, 0.85, 1.0
    ),
    p!(
        PRE_MEDIUM, 3, 34, 28, 16, 77, 3, 3, 2, 2, 2, 95.0, 70.0, 3.0, 1.1, 1.05, 0.90, 1.0
    ),
    p!(
        PRE_THOROUGH,
        4,
        82,
        60,
        30,
        94,
        4,
        4,
        3,
        2,
        2,
        105.0,
        77.0,
        10.0,
        1.4,
        1.2,
        0.95,
        0.0
    ),
    p!(
        PRE_VERYTHOROUGH,
        4,
        256,
        128,
        64,
        98,
        4,
        6,
        8,
        6,
        3,
        200.0,
        200.0,
        10.0,
        1.6,
        1.4,
        0.98,
        0.0
    ),
    p!(
        PRE_EXHAUSTIVE,
        4,
        256,
        256,
        256,
        100,
        4,
        8,
        8,
        8,
        8,
        200.0,
        200.0,
        10.0,
        2.0,
        2.0,
        0.99,
        0.0
    ),
];
static PRESET_LOW: [Preset; 6] = [
    p!(
        PRE_FASTEST,
        2,
        10,
        6,
        4,
        40,
        2,
        2,
        2,
        2,
        2,
        85.0,
        63.0,
        3.5,
        1.0,
        1.0,
        0.80,
        1.0
    ),
    p!(
        PRE_FAST, 2, 18, 12, 10, 55, 3, 3, 2, 2, 2, 85.0, 63.0, 3.5, 1.0, 1.0, 0.85, 1.0
    ),
    p!(
        PRE_MEDIUM, 3, 34, 28, 16, 77, 3, 3, 2, 2, 2, 95.0, 70.0, 3.5, 1.1, 1.05, 0.90, 1.0
    ),
    p!(
        PRE_THOROUGH,
        4,
        82,
        60,
        30,
        93,
        4,
        4,
        3,
        2,
        2,
        105.0,
        77.0,
        10.0,
        1.3,
        1.2,
        0.97,
        1.0
    ),
    p!(
        PRE_VERYTHOROUGH,
        4,
        256,
        128,
        64,
        98,
        4,
        6,
        8,
        5,
        2,
        200.0,
        200.0,
        10.0,
        1.6,
        1.4,
        0.98,
        1.0
    ),
    p!(
        PRE_EXHAUSTIVE,
        4,
        256,
        256,
        256,
        100,
        4,
        8,
        8,
        8,
        8,
        200.0,
        200.0,
        10.0,
        2.0,
        2.0,
        0.99,
        1.0
    ),
];

/// `logf(x)` as the correctly rounded value, which the C runtime's `logf` gives for these inputs
/// (checked against the oracle's config for every legal 2D footprint).
fn logf(x: f32) -> f32 {
    (x as f64).ln() as f32
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error {
    BadBlockSize,
    BadQuality,
    BadProfile,
    BadFlags,
    BadParam,
    NotImplemented,
    BadSwizzle,
    OutOfMem,
}

/// `astcenc_config_init` for a 2D footprint.
pub fn config_init(
    profile: u32,
    block_x: u32,
    block_y: u32,
    quality: f32,
    flags: u32,
) -> Result<Config, Error> {
    let mut config = Config::default();
    if !is_legal_2d_block_size(block_x, block_y) {
        return Err(Error::BadBlockSize);
    }
    let block_z = 1;
    config.block_x = block_x;
    config.block_y = block_y;
    config.block_z = block_z;
    let texels = (block_x * block_y * block_z) as f32;
    let ltexels = logf(texels) / logf(10.0);
    if !(PRE_FASTEST..=PRE_EXHAUSTIVE).contains(&quality) {
        return Err(Error::BadQuality);
    }
    let texels_int = block_x * block_y * block_z;
    let presets = if texels_int < 25 {
        &PRESET_HIGH
    } else if texels_int < 64 {
        &PRESET_MID
    } else {
        &PRESET_LOW
    };
    let mut end = 0;
    while end < presets.len() {
        if presets[end].quality >= quality {
            break;
        }
        end += 1;
    }
    let start = if end == 0 { 0 } else { end - 1 };
    if start == end {
        let s = &presets[start];
        config.tune_partition_count_limit = s.tune_partition_count_limit;
        config.tune_2partition_index_limit = s.tune_2partition_index_limit;
        config.tune_3partition_index_limit = s.tune_3partition_index_limit;
        config.tune_4partition_index_limit = s.tune_4partition_index_limit;
        config.tune_block_mode_limit = s.tune_block_mode_limit;
        config.tune_refinement_limit = s.tune_refinement_limit;
        config.tune_candidate_limit = s.tune_candidate_limit;
        config.tune_2partitioning_candidate_limit = s.tune_2partitioning_candidate_limit;
        config.tune_3partitioning_candidate_limit = s.tune_3partitioning_candidate_limit;
        config.tune_4partitioning_candidate_limit = s.tune_4partitioning_candidate_limit;
        config.tune_db_limit = astc::max(
            s.tune_db_limit_a_base - 35.0 * ltexels,
            s.tune_db_limit_b_base - 19.0 * ltexels,
        );
        config.tune_mse_overshoot = s.tune_mse_overshoot;
        config.tune_2partition_early_out_limit_factor = s.tune_2partition_early_out_limit_factor;
        config.tune_3partition_early_out_limit_factor = s.tune_3partition_early_out_limit_factor;
        config.tune_2plane_early_out_limit_correlation = s.tune_2plane_early_out_limit_correlation;
        config.tune_search_mode0_enable = s.tune_search_mode0_enable;
    } else {
        // `end` can reach 6 only for a quality above EXHAUSTIVE, refused above.
        let a = &presets[start];
        let b = &presets[end];
        let wt_range = b.quality - a.quality;
        let wa = (b.quality - quality) / wt_range;
        let wb = (quality - a.quality) / wt_range;
        let lerp = |x: f32, y: f32| (x * wa) + (y * wb);
        let lerpi = |x: u32, y: u32| astc::flt2int_rtn((x as f32 * wa) + (y as f32 * wb)) as u32;
        config.tune_partition_count_limit =
            lerpi(a.tune_partition_count_limit, b.tune_partition_count_limit);
        config.tune_2partition_index_limit =
            lerpi(a.tune_2partition_index_limit, b.tune_2partition_index_limit);
        config.tune_3partition_index_limit =
            lerpi(a.tune_3partition_index_limit, b.tune_3partition_index_limit);
        config.tune_4partition_index_limit =
            lerpi(a.tune_4partition_index_limit, b.tune_4partition_index_limit);
        config.tune_block_mode_limit = lerpi(a.tune_block_mode_limit, b.tune_block_mode_limit);
        config.tune_refinement_limit = lerpi(a.tune_refinement_limit, b.tune_refinement_limit);
        config.tune_candidate_limit = lerpi(a.tune_candidate_limit, b.tune_candidate_limit);
        config.tune_2partitioning_candidate_limit = lerpi(
            a.tune_2partitioning_candidate_limit,
            b.tune_2partitioning_candidate_limit,
        );
        config.tune_3partitioning_candidate_limit = lerpi(
            a.tune_3partitioning_candidate_limit,
            b.tune_3partitioning_candidate_limit,
        );
        config.tune_4partitioning_candidate_limit = lerpi(
            a.tune_4partitioning_candidate_limit,
            b.tune_4partitioning_candidate_limit,
        );
        config.tune_db_limit = astc::max(
            lerp(a.tune_db_limit_a_base, b.tune_db_limit_a_base) - 35.0 * ltexels,
            lerp(a.tune_db_limit_b_base, b.tune_db_limit_b_base) - 19.0 * ltexels,
        );
        config.tune_mse_overshoot = lerp(a.tune_mse_overshoot, b.tune_mse_overshoot);
        config.tune_2partition_early_out_limit_factor = lerp(
            a.tune_2partition_early_out_limit_factor,
            b.tune_2partition_early_out_limit_factor,
        );
        config.tune_3partition_early_out_limit_factor = lerp(
            a.tune_3partition_early_out_limit_factor,
            b.tune_3partition_early_out_limit_factor,
        );
        config.tune_2plane_early_out_limit_correlation = lerp(
            a.tune_2plane_early_out_limit_correlation,
            b.tune_2plane_early_out_limit_correlation,
        );
        config.tune_search_mode0_enable =
            lerp(a.tune_search_mode0_enable, b.tune_search_mode0_enable);
    }
    config.cw_r_weight = 1.0;
    config.cw_g_weight = 1.0;
    config.cw_b_weight = 1.0;
    config.cw_a_weight = 1.0;
    config.a_scale_radius = 0;
    config.rgbm_m_scale = 0.0;
    config.profile = profile;
    match profile {
        PRF_LDR | PRF_LDR_SRGB => {}
        PRF_HDR_RGB_LDR_A | PRF_HDR => return Err(Error::NotImplemented),
        _ => return Err(Error::BadProfile),
    }
    if flags != 0 {
        // Only the flag-free LDR path is ported.
        return Err(Error::NotImplemented);
    }
    config.flags = flags;
    Ok(config)
}

fn validate_config(config: &mut Config) -> Result<(), Error> {
    config.rgbm_m_scale = astc::max(config.rgbm_m_scale, 1.0);
    config.tune_partition_count_limit = astc::clamp(config.tune_partition_count_limit, 1, 4);
    let bmp = BLOCK_MAX_PARTITIONINGS as u32;
    config.tune_2partition_index_limit = astc::clamp(config.tune_2partition_index_limit, 1, bmp);
    config.tune_3partition_index_limit = astc::clamp(config.tune_3partition_index_limit, 1, bmp);
    config.tune_4partition_index_limit = astc::clamp(config.tune_4partition_index_limit, 1, bmp);
    config.tune_block_mode_limit = astc::clamp(config.tune_block_mode_limit, 1, 100);
    config.tune_refinement_limit = astc::max(config.tune_refinement_limit, 1);
    let tc = TUNE_MAX_TRIAL_CANDIDATES as u32;
    let pc = TUNE_MAX_PARTITIONING_CANDIDATES as u32;
    config.tune_candidate_limit = astc::clamp(config.tune_candidate_limit, 1, tc);
    config.tune_2partitioning_candidate_limit =
        astc::clamp(config.tune_2partitioning_candidate_limit, 1, pc);
    config.tune_3partitioning_candidate_limit =
        astc::clamp(config.tune_3partitioning_candidate_limit, 1, pc);
    config.tune_4partitioning_candidate_limit =
        astc::clamp(config.tune_4partitioning_candidate_limit, 1, pc);
    config.tune_db_limit = astc::max(config.tune_db_limit, 0.0);
    config.tune_mse_overshoot = astc::max(config.tune_mse_overshoot, 1.0);
    config.tune_2partition_early_out_limit_factor =
        astc::max(config.tune_2partition_early_out_limit_factor, 0.0);
    config.tune_3partition_early_out_limit_factor =
        astc::max(config.tune_3partition_early_out_limit_factor, 0.0);
    config.tune_2plane_early_out_limit_correlation =
        astc::max(config.tune_2plane_early_out_limit_correlation, 0.0);
    let mut max_weight = astc::max(
        astc::max(config.cw_r_weight, config.cw_g_weight),
        astc::max(config.cw_b_weight, config.cw_a_weight),
    );
    if max_weight > 0.0 {
        max_weight /= 1000.0;
        config.cw_r_weight = astc::max(config.cw_r_weight, max_weight);
        config.cw_g_weight = astc::max(config.cw_g_weight, max_weight);
        config.cw_b_weight = astc::max(config.cw_b_weight, max_weight);
        config.cw_a_weight = astc::max(config.cw_a_weight, max_weight);
        Ok(())
    } else {
        Err(Error::BadParam)
    }
}

/// A compression context: the validated config, its block-size descriptor and one set of working
/// buffers per thread, which persist from block to block and image to image as in the C++.
pub struct Context {
    pub config: Config,
    pub bsd: Box<BlockSizeDescriptor>,
    pub(crate) working_buffers: Vec<Box<CompressionWorkingBuffers>>,
}

/// Blocks per task, as `compress_image` asks `get_task_assignment(16, ...)` for.
const TASK_BLOCKS: usize = 16;

impl Context {
    /// `astcenc_context_alloc` with one thread.
    pub fn new(config: &Config) -> Result<Self, Error> {
        Self::with_threads(config, 1)
    }

    /// `astcenc_context_alloc` with `threads` workers (at least one).
    pub fn with_threads(config: &Config, threads: usize) -> Result<Self, Error> {
        let mut config = *config;
        validate_config(&mut config)?;
        let can_omit_modes = config.flags & FLG_SELF_DECOMPRESS_ONLY != 0;
        let bsd = init_block_size_descriptor(
            config.block_x,
            config.block_y,
            can_omit_modes,
            config.tune_partition_count_limit,
            config.tune_block_mode_limit as f32 / 100.0,
        );
        config.tune_db_limit = astc::pow(0.1, config.tune_db_limit * 0.1) * 65535.0 * 65535.0;
        let working_buffers = (0..threads.max(1))
            .map(|_| CompressionWorkingBuffers::zeroed())
            .collect();
        Ok(Self {
            config,
            bsd,
            working_buffers,
        })
    }

    /// `astcenc_compress_image` for a 2D RGBA8 image with the identity swizzle: each 16 bytes at
    /// `(y * xblocks + x) * 16`. Workers take 16-block tasks in turn, as upstream's do; which worker
    /// compresses a block does not change its bytes (measured at 1 to 12 threads, both taps).
    pub fn compress_image(&mut self, image: &crate::image::Image<'_>) -> Result<Vec<u8>, Error> {
        let bsd = &*self.bsd;
        let (bx, by) = (bsd.xdim as u32, bsd.ydim as u32);
        if image.dim_x == 0
            || image.dim_y == 0
            || image.data.len() < (image.dim_x as usize * image.dim_y as usize * 4)
        {
            return Err(Error::BadParam);
        }
        let xblocks = image.dim_x.div_ceil(bx) as usize;
        let yblocks = image.dim_y.div_ceil(by) as usize;
        let mut out = vec![0u8; xblocks * yblocks * 16];
        let config = &self.config;
        let tasks = std::sync::Mutex::new(out.chunks_mut(TASK_BLOCKS * 16).enumerate());
        let worker = |tmpbuf: &mut CompressionWorkingBuffers| {
            let mut blk = ImageBlock::zeroed();
            blk.texel_count = bsd.texel_count;
            blk.decode_unorm8 = config.flags & FLG_USE_DECODE_UNORM8 != 0;
            blk.channel_weight = VFloat4::new(
                config.cw_r_weight,
                config.cw_g_weight,
                config.cw_b_weight,
                config.cw_a_weight,
            );
            loop {
                let next = tasks.lock().map(|mut t| t.next()).unwrap_or(None);
                let Some((task, chunk)) = next else { break };
                for (k, pcb) in chunk.as_chunks_mut::<16>().0.iter_mut().enumerate() {
                    let i = task * TASK_BLOCKS + k;
                    let (x, y) = ((i % xblocks) as u32, (i / xblocks) as u32);
                    crate::image::load_image_block_fast_ldr(
                        image,
                        &mut blk,
                        bsd,
                        x * bx,
                        y * by,
                        0,
                    );
                    crate::compress_symbolic::compress_block(config, bsd, &blk, pcb, tmpbuf);
                }
            }
        };
        let (first, rest) = self
            .working_buffers
            .split_first_mut()
            .ok_or(Error::BadParam)?;
        std::thread::scope(|s| {
            for tmpbuf in rest.iter_mut() {
                s.spawn(|| worker(tmpbuf));
            }
            worker(first);
        });
        Ok(out)
    }
}
