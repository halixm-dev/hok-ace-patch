//! Constants and data structures (`astcenc_internal.h`), for the LDR 2D compressor at SIMD width 4.

use crate::vecmath::{VFloat4, VInt4, VMask4, any, vfloat3};

pub const BLOCK_MAX_TEXELS: usize = 216;
pub const BLOCK_MAX_COMPONENTS: usize = 4;
pub const BLOCK_MAX_PARTITIONS: usize = 4;
pub const BLOCK_MAX_PARTITIONINGS: usize = 1024;
pub const BLOCK_MAX_KMEANS_TEXELS: usize = 64;
pub const BLOCK_MAX_WEIGHTS: usize = 64;
pub const BLOCK_MAX_WEIGHTS_2PLANE: usize = BLOCK_MAX_WEIGHTS / 2;
pub const BLOCK_MIN_WEIGHT_BITS: u32 = 24;
pub const BLOCK_MAX_WEIGHT_BITS: u32 = 96;
pub const BLOCK_BAD_BLOCK_MODE: u16 = 0xFFFF;
pub const BLOCK_BAD_PARTITIONING: u16 = 0xFFFF;
pub const PARTITION_INDEX_BITS: u32 = 10;
pub const WEIGHTS_PLANE2_OFFSET: usize = BLOCK_MAX_WEIGHTS_2PLANE;
pub const WEIGHTS_TEXEL_SUM: f32 = 16.0;
pub const WEIGHTS_MAX_BLOCK_MODES: usize = 2048;
pub const WEIGHTS_MAX_DECIMATION_MODES: usize = 87;
pub const ERROR_CALC_DEFAULT: f32 = 1e30;
pub const TUNE_MIN_SEARCH_MODE0: f32 = 0.85;
pub const TUNE_MAX_TRIAL_CANDIDATES: usize = 8;
pub const TUNE_MAX_PARTITIONING_CANDIDATES: usize = 8;
pub const TUNE_MAX_ANGULAR_QUANT: usize = 7;
pub const SIMD_WIDTH: usize = 4;

pub const FMT_LUMINANCE: u8 = 0;
pub const FMT_LUMINANCE_DELTA: u8 = 1;
pub const FMT_HDR_LUMINANCE_LARGE_RANGE: u8 = 2;
pub const FMT_HDR_LUMINANCE_SMALL_RANGE: u8 = 3;
pub const FMT_LUMINANCE_ALPHA: u8 = 4;
pub const FMT_LUMINANCE_ALPHA_DELTA: u8 = 5;
pub const FMT_RGB_SCALE: u8 = 6;
pub const FMT_HDR_RGB_SCALE: u8 = 7;
pub const FMT_RGB: u8 = 8;
pub const FMT_RGB_DELTA: u8 = 9;
pub const FMT_RGB_SCALE_ALPHA: u8 = 10;
pub const FMT_HDR_RGB: u8 = 11;
pub const FMT_RGBA: u8 = 12;
pub const FMT_RGBA_DELTA: u8 = 13;
pub const FMT_HDR_RGB_LDR_ALPHA: u8 = 14;
pub const FMT_HDR_RGBA: u8 = 15;

pub const QUANT_2: usize = 0;
pub const QUANT_3: usize = 1;
pub const QUANT_4: usize = 2;
pub const QUANT_5: usize = 3;
pub const QUANT_6: usize = 4;
pub const QUANT_8: usize = 5;
pub const QUANT_10: usize = 6;
pub const QUANT_12: usize = 7;
pub const QUANT_16: usize = 8;
pub const QUANT_20: usize = 9;
pub const QUANT_24: usize = 10;
pub const QUANT_32: usize = 11;
pub const QUANT_40: usize = 12;
pub const QUANT_48: usize = 13;
pub const QUANT_64: usize = 14;
pub const QUANT_80: usize = 15;
pub const QUANT_96: usize = 16;
pub const QUANT_128: usize = 17;
pub const QUANT_160: usize = 18;
pub const QUANT_192: usize = 19;
pub const QUANT_256: usize = 20;

pub const QUANT_LEVELS: [u32; 21] = [
    2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 256,
];

#[inline]
pub fn get_quant_level(method: usize) -> u32 {
    QUANT_LEVELS.get(method).copied().unwrap_or(0)
}

pub const PRF_LDR_SRGB: u32 = 0;
pub const PRF_LDR: u32 = 1;
pub const PRF_HDR_RGB_LDR_A: u32 = 2;
pub const PRF_HDR: u32 = 3;

pub const FLG_MAP_NORMAL: u32 = 1 << 0;
pub const FLG_USE_DECODE_UNORM8: u32 = 1 << 1;
pub const FLG_USE_ALPHA_WEIGHT: u32 = 1 << 2;
pub const FLG_USE_PERCEPTUAL: u32 = 1 << 3;
pub const FLG_DECOMPRESS_ONLY: u32 = 1 << 4;
pub const FLG_SELF_DECOMPRESS_ONLY: u32 = 1 << 5;
pub const FLG_MAP_RGBM: u32 = 1 << 6;

#[derive(Clone, Copy, Debug, Default)]
pub struct PartitionMetrics {
    pub avg: VFloat4,
    pub dir: VFloat4,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Line {
    pub a: VFloat4,
    pub b: VFloat4,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ProcessedLine {
    pub amod: VFloat4,
    pub bs: VFloat4,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct PartitionLines3 {
    pub uncor_line: Line,
    pub samec_line: Line,
    pub uncor_pline: ProcessedLine,
    pub samec_pline: ProcessedLine,
    pub line_length: f32,
}

#[derive(Clone)]
pub struct PartitionInfo {
    pub partition_count: u16,
    pub partition_index: u16,
    pub partition_texel_count: [u8; BLOCK_MAX_PARTITIONS],
    pub partition_of_texel: [u8; BLOCK_MAX_TEXELS],
    pub texels_of_partition: [[u8; BLOCK_MAX_TEXELS]; BLOCK_MAX_PARTITIONS],
}

impl PartitionInfo {
    pub const ZERO: Self = Self {
        partition_count: 0,
        partition_index: 0,
        partition_texel_count: [0; 4],
        partition_of_texel: [0; BLOCK_MAX_TEXELS],
        texels_of_partition: [[0; BLOCK_MAX_TEXELS]; 4],
    };
}

#[derive(Clone)]
pub struct DecimationInfo {
    pub texel_count: u8,
    pub max_texel_weight_count: u8,
    pub weight_count: u8,
    pub weight_x: u8,
    pub weight_y: u8,
    pub weight_z: u8,
    pub texel_weight_count: [u8; BLOCK_MAX_TEXELS],
    pub texel_weights_tr: [[u8; BLOCK_MAX_TEXELS]; 4],
    pub texel_weight_contribs_int_tr: [[u8; BLOCK_MAX_TEXELS]; 4],
    pub texel_weight_contribs_float_tr: [[f32; BLOCK_MAX_TEXELS]; 4],
    pub weight_texel_count: [u8; BLOCK_MAX_WEIGHTS],
    pub weight_texels_tr: [[u8; BLOCK_MAX_WEIGHTS]; BLOCK_MAX_TEXELS],
    pub weights_texel_contribs_tr: [[f32; BLOCK_MAX_WEIGHTS]; BLOCK_MAX_TEXELS],
    pub texel_contrib_for_weight: [[f32; BLOCK_MAX_WEIGHTS]; BLOCK_MAX_TEXELS],
}

impl DecimationInfo {
    pub fn zeroed() -> Box<Self> {
        Box::new(Self {
            texel_count: 0,
            max_texel_weight_count: 0,
            weight_count: 0,
            weight_x: 0,
            weight_y: 0,
            weight_z: 0,
            texel_weight_count: [0; BLOCK_MAX_TEXELS],
            texel_weights_tr: [[0; BLOCK_MAX_TEXELS]; 4],
            texel_weight_contribs_int_tr: [[0; BLOCK_MAX_TEXELS]; 4],
            texel_weight_contribs_float_tr: [[0.0; BLOCK_MAX_TEXELS]; 4],
            weight_texel_count: [0; BLOCK_MAX_WEIGHTS],
            weight_texels_tr: [[0; BLOCK_MAX_WEIGHTS]; BLOCK_MAX_TEXELS],
            weights_texel_contribs_tr: [[0.0; BLOCK_MAX_WEIGHTS]; BLOCK_MAX_TEXELS],
            texel_contrib_for_weight: [[0.0; BLOCK_MAX_WEIGHTS]; BLOCK_MAX_TEXELS],
        })
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct BlockMode {
    pub mode_index: u16,
    pub decimation_mode: u8,
    pub quant_mode: u8,
    pub weight_bits: u8,
    pub is_dual_plane: bool,
}

impl BlockMode {
    #[inline]
    pub fn get_weight_quant_mode(&self) -> usize {
        self.quant_mode as usize
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct DecimationMode {
    pub maxprec_1plane: i8,
    pub maxprec_2planes: i8,
    pub refprec_1plane: u16,
    pub refprec_2planes: u16,
}

impl DecimationMode {
    pub fn set_ref_1plane(&mut self, q: usize) {
        self.refprec_1plane |= 1 << q;
    }
    pub fn is_ref_1plane(&self, max_weight_quant: usize) -> bool {
        let mask = ((1u32 << (max_weight_quant + 1)) - 1) as u16;
        (self.refprec_1plane & mask) != 0
    }
    pub fn set_ref_2plane(&mut self, q: usize) {
        self.refprec_2planes |= 1 << q;
    }
    pub fn is_ref_2plane(&self, max_weight_quant: usize) -> bool {
        let mask = ((1u32 << (max_weight_quant + 1)) - 1) as u16;
        (self.refprec_2planes & mask) != 0
    }
}

pub struct BlockSizeDescriptor {
    pub xdim: u8,
    pub ydim: u8,
    pub zdim: u8,
    pub texel_count: u8,
    pub decimation_mode_count_always: u32,
    pub decimation_mode_count_selected: u32,
    pub decimation_mode_count_all: u32,
    pub block_mode_count_1plane_always: u32,
    pub block_mode_count_1plane_selected: u32,
    pub block_mode_count_1plane_2plane_selected: u32,
    pub block_mode_count_all: u32,
    pub partitioning_count_selected: [u32; BLOCK_MAX_PARTITIONS],
    pub partitioning_count_all: [u32; BLOCK_MAX_PARTITIONS],
    pub decimation_modes: [DecimationMode; WEIGHTS_MAX_DECIMATION_MODES],
    pub decimation_tables: Vec<Box<DecimationInfo>>,
    pub block_mode_packed_index: [u16; WEIGHTS_MAX_BLOCK_MODES],
    pub block_modes: Vec<BlockMode>,
    /// Two-, three- and four-partition tables (1024 each), then the one-partition entry.
    pub partitionings: Vec<PartitionInfo>,
    pub partitioning_packed_index: [[u16; BLOCK_MAX_PARTITIONINGS]; 3],
    pub kmeans_texels: [u8; BLOCK_MAX_KMEANS_TEXELS],
    pub coverage_bitmaps_2: Vec<[u64; 2]>,
    pub coverage_bitmaps_3: Vec<[u64; 3]>,
    pub coverage_bitmaps_4: Vec<[u64; 4]>,
}

impl BlockSizeDescriptor {
    pub fn zeroed() -> Self {
        Self {
            xdim: 0,
            ydim: 0,
            zdim: 0,
            texel_count: 0,
            decimation_mode_count_always: 0,
            decimation_mode_count_selected: 0,
            decimation_mode_count_all: 0,
            block_mode_count_1plane_always: 0,
            block_mode_count_1plane_selected: 0,
            block_mode_count_1plane_2plane_selected: 0,
            block_mode_count_all: 0,
            partitioning_count_selected: [0; 4],
            partitioning_count_all: [0; 4],
            decimation_modes: [DecimationMode::default(); WEIGHTS_MAX_DECIMATION_MODES],
            decimation_tables: (0..WEIGHTS_MAX_DECIMATION_MODES)
                .map(|_| DecimationInfo::zeroed())
                .collect(),
            block_mode_packed_index: [0; WEIGHTS_MAX_BLOCK_MODES],
            block_modes: vec![BlockMode::default(); WEIGHTS_MAX_BLOCK_MODES],
            partitionings: vec![PartitionInfo::ZERO; 3 * BLOCK_MAX_PARTITIONINGS + 1],
            partitioning_packed_index: [[0; BLOCK_MAX_PARTITIONINGS]; 3],
            kmeans_texels: [0; BLOCK_MAX_KMEANS_TEXELS],
            coverage_bitmaps_2: vec![[0; 2]; BLOCK_MAX_PARTITIONINGS],
            coverage_bitmaps_3: vec![[0; 3]; BLOCK_MAX_PARTITIONINGS],
            coverage_bitmaps_4: vec![[0; 4]; BLOCK_MAX_PARTITIONINGS],
        }
    }

    #[inline]
    pub fn get_block_mode(&self, block_mode: u32) -> &BlockMode {
        &self.block_modes[self.block_mode_packed_index[block_mode as usize] as usize]
    }
    #[inline]
    pub fn get_decimation_mode(&self, decimation_mode: u32) -> &DecimationMode {
        &self.decimation_modes[decimation_mode as usize]
    }
    #[inline]
    pub fn get_decimation_info(&self, decimation_mode: u32) -> &DecimationInfo {
        &self.decimation_tables[decimation_mode as usize]
    }
    /// The start of a partition count's table in `partitionings`.
    #[inline]
    pub fn partition_table_base(partition_count: u32) -> usize {
        let pc = if partition_count == 1 {
            5
        } else {
            partition_count
        };
        (pc as usize - 2) * BLOCK_MAX_PARTITIONINGS
    }
    #[inline]
    pub fn get_partition_table(&self, partition_count: u32) -> &[PartitionInfo] {
        &self.partitionings[Self::partition_table_base(partition_count)..]
    }
    #[inline]
    pub fn get_partition_info(&self, partition_count: u32, index: u32) -> &PartitionInfo {
        let packed = if partition_count >= 2 {
            self.partitioning_packed_index[partition_count as usize - 2][index as usize] as usize
        } else {
            0
        };
        &self.get_partition_table(partition_count)[packed]
    }
    #[inline]
    pub fn get_raw_partition_info(
        &self,
        partition_count: u32,
        packed_index: u32,
    ) -> &PartitionInfo {
        &self.get_partition_table(partition_count)[packed_index as usize]
    }
}

pub const BLOCK_DATA_LEN: usize = BLOCK_MAX_TEXELS + SIMD_WIDTH - 1;

#[derive(Clone)]
pub struct ImageBlock {
    pub data_r: [f32; BLOCK_DATA_LEN],
    pub data_g: [f32; BLOCK_DATA_LEN],
    pub data_b: [f32; BLOCK_DATA_LEN],
    pub data_a: [f32; BLOCK_DATA_LEN],
    pub texel_count: u8,
    pub origin_texel: VFloat4,
    pub data_min: VFloat4,
    pub data_mean: VFloat4,
    pub data_max: VFloat4,
    pub channel_weight: VFloat4,
    pub grayscale: bool,
    pub decode_unorm8: bool,
    pub rgb_lns: [u8; BLOCK_MAX_TEXELS],
    pub alpha_lns: [u8; BLOCK_MAX_TEXELS],
    pub xpos: u32,
    pub ypos: u32,
    pub zpos: u32,
}

impl ImageBlock {
    pub fn zeroed() -> Box<Self> {
        Box::new(Self {
            data_r: [0.0; BLOCK_DATA_LEN],
            data_g: [0.0; BLOCK_DATA_LEN],
            data_b: [0.0; BLOCK_DATA_LEN],
            data_a: [0.0; BLOCK_DATA_LEN],
            texel_count: 0,
            origin_texel: VFloat4::zero(),
            data_min: VFloat4::zero(),
            data_mean: VFloat4::zero(),
            data_max: VFloat4::zero(),
            channel_weight: VFloat4::zero(),
            grayscale: false,
            decode_unorm8: false,
            rgb_lns: [0; BLOCK_MAX_TEXELS],
            alpha_lns: [0; BLOCK_MAX_TEXELS],
            xpos: 0,
            ypos: 0,
            zpos: 0,
        })
    }
    #[inline]
    pub fn texel(&self, i: usize) -> VFloat4 {
        VFloat4::new(
            self.data_r[i],
            self.data_g[i],
            self.data_b[i],
            self.data_a[i],
        )
    }
    #[inline]
    pub fn texel3(&self, i: usize) -> VFloat4 {
        vfloat3(self.data_r[i], self.data_g[i], self.data_b[i])
    }
    #[inline]
    pub fn channel(&self, c: usize) -> &[f32; BLOCK_DATA_LEN] {
        match c {
            0 => &self.data_r,
            1 => &self.data_g,
            2 => &self.data_b,
            _ => &self.data_a,
        }
    }
    #[inline]
    pub fn get_default_alpha(&self) -> f32 {
        if self.alpha_lns[0] != 0 {
            0x7800 as f32
        } else {
            0xFFFF as f32
        }
    }
    #[inline]
    pub fn is_constant_channel(&self, channel: i32) -> bool {
        let lane_mask = VInt4::lane_id().eq(VInt4::splat(channel));
        let color_mask = self.data_min.eq(self.data_max);
        any(lane_mask & color_mask)
    }
    #[inline]
    pub fn is_luminance(&self) -> bool {
        let a = self.get_default_alpha();
        let alpha1 = self.data_min.lane(3) == a && self.data_max.lane(3) == a;
        self.grayscale && alpha1
    }
    #[inline]
    pub fn is_luminancealpha(&self) -> bool {
        let a = self.get_default_alpha();
        let alpha1 = self.data_min.lane(3) == a && self.data_max.lane(3) == a;
        self.grayscale && !alpha1
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Endpoints {
    pub partition_count: u32,
    pub endpt0: [VFloat4; BLOCK_MAX_PARTITIONS],
    pub endpt1: [VFloat4; BLOCK_MAX_PARTITIONS],
}

#[derive(Clone)]
pub struct EndpointsAndWeights {
    pub is_constant_weight_error_scale: bool,
    pub ep: Endpoints,
    pub weights: [f32; BLOCK_MAX_TEXELS],
    pub weight_error_scale: [f32; BLOCK_MAX_TEXELS],
}

impl EndpointsAndWeights {
    pub const ZERO: Self = Self {
        is_constant_weight_error_scale: false,
        ep: Endpoints {
            partition_count: 0,
            endpt0: [VFloat4::zero(); 4],
            endpt1: [VFloat4::zero(); 4],
        },
        weights: [0.0; BLOCK_MAX_TEXELS],
        weight_error_scale: [0.0; BLOCK_MAX_TEXELS],
    };
}

#[derive(Clone, Copy, Debug, Default)]
pub struct EncodingChoiceErrors {
    pub rgb_scale_error: f32,
    pub rgb_luma_error: f32,
    pub luminance_error: f32,
    pub alpha_drop_error: f32,
    pub can_offset_encode: bool,
    pub can_blue_contract: bool,
}

pub struct CompressionWorkingBuffers {
    pub ei1: EndpointsAndWeights,
    pub ei2: EndpointsAndWeights,
    pub dec_weights_ideal: Vec<f32>,
    pub dec_weights_uquant: Vec<u8>,
    pub errors_of_best_combination: Vec<f32>,
    pub best_quant_levels: Vec<u8>,
    pub best_quant_levels_mod: Vec<u8>,
    pub best_ep_formats: Vec<[u8; BLOCK_MAX_PARTITIONS]>,
    pub qwt_bitcounts: Vec<i8>,
    pub qwt_errors: Vec<f32>,
    pub weight_low_value1: Vec<f32>,
    pub weight_high_value1: Vec<f32>,
    pub weight_low_values1: Vec<[f32; TUNE_MAX_ANGULAR_QUANT + 1]>,
    pub weight_high_values1: Vec<[f32; TUNE_MAX_ANGULAR_QUANT + 1]>,
    pub weight_low_value2: Vec<f32>,
    pub weight_high_value2: Vec<f32>,
    pub weight_low_values2: Vec<[f32; TUNE_MAX_ANGULAR_QUANT + 1]>,
    pub weight_high_values2: Vec<[f32; TUNE_MAX_ANGULAR_QUANT + 1]>,
}

impl CompressionWorkingBuffers {
    pub fn zeroed() -> Box<Self> {
        let bm = WEIGHTS_MAX_BLOCK_MODES;
        let dm = WEIGHTS_MAX_DECIMATION_MODES;
        Box::new(Self {
            ei1: EndpointsAndWeights::ZERO,
            ei2: EndpointsAndWeights::ZERO,
            dec_weights_ideal: vec![0.0; dm * BLOCK_MAX_WEIGHTS],
            dec_weights_uquant: vec![0; bm * BLOCK_MAX_WEIGHTS],
            errors_of_best_combination: vec![0.0; bm],
            best_quant_levels: vec![0; bm],
            best_quant_levels_mod: vec![0; bm],
            best_ep_formats: vec![[0; 4]; bm],
            qwt_bitcounts: vec![0; bm],
            qwt_errors: vec![0.0; bm],
            weight_low_value1: vec![0.0; bm],
            weight_high_value1: vec![0.0; bm],
            weight_low_values1: vec![[0.0; TUNE_MAX_ANGULAR_QUANT + 1]; dm],
            weight_high_values1: vec![[0.0; TUNE_MAX_ANGULAR_QUANT + 1]; dm],
            weight_low_value2: vec![0.0; bm],
            weight_high_value2: vec![0.0; bm],
            weight_low_values2: vec![[0.0; TUNE_MAX_ANGULAR_QUANT + 1]; dm],
            weight_high_values2: vec![[0.0; TUNE_MAX_ANGULAR_QUANT + 1]; dm],
        })
    }
}

pub const SYM_BTYPE_ERROR: u8 = 0;
pub const SYM_BTYPE_CONST_F16: u8 = 1;
pub const SYM_BTYPE_CONST_U16: u8 = 2;
pub const SYM_BTYPE_NONCONST: u8 = 3;

/// `symbolic_compressed_block`. The C++ union of `constant_color` and `color_values` is kept as
/// the raw 16 bytes, read through the two accessors.
#[derive(Clone, Copy, Debug)]
pub struct SymbolicCompressedBlock {
    pub block_type: u8,
    pub partition_count: u8,
    pub color_formats_matched: u8,
    pub plane2_component: i8,
    pub block_mode: u16,
    pub partition_index: u16,
    pub color_formats: [u8; BLOCK_MAX_PARTITIONS],
    pub quant_mode: usize,
    pub errorval: f32,
    pub color_values: [[u8; 8]; BLOCK_MAX_PARTITIONS],
    pub weights: [u8; BLOCK_MAX_WEIGHTS],
}

impl Default for SymbolicCompressedBlock {
    fn default() -> Self {
        Self {
            block_type: 0,
            partition_count: 0,
            color_formats_matched: 0,
            plane2_component: 0,
            block_mode: 0,
            partition_index: 0,
            color_formats: [0; 4],
            quant_mode: 0,
            errorval: 0.0,
            color_values: [[0; 8]; 4],
            weights: [0; BLOCK_MAX_WEIGHTS],
        }
    }
}

impl SymbolicCompressedBlock {
    /// `constant_color[i]`: the union's first 16 bytes as four `int`s.
    #[inline]
    pub fn constant_color(&self, i: usize) -> i32 {
        let row = &self.color_values[i / 2];
        let o = (i % 2) * 4;
        i32::from_le_bytes([row[o], row[o + 1], row[o + 2], row[o + 3]])
    }
    #[inline]
    pub fn set_constant_color(&mut self, i: usize, v: i32) {
        let o = (i % 2) * 4;
        self.color_values[i / 2][o..o + 4].copy_from_slice(&v.to_le_bytes());
    }
}

/// `astcenc_config`, without the callback and trace path.
#[derive(Clone, Copy, Debug, Default)]
pub struct Config {
    pub profile: u32,
    pub flags: u32,
    pub block_x: u32,
    pub block_y: u32,
    pub block_z: u32,
    pub cw_r_weight: f32,
    pub cw_g_weight: f32,
    pub cw_b_weight: f32,
    pub cw_a_weight: f32,
    pub a_scale_radius: u32,
    pub rgbm_m_scale: f32,
    pub tune_partition_count_limit: u32,
    pub tune_2partition_index_limit: u32,
    pub tune_3partition_index_limit: u32,
    pub tune_4partition_index_limit: u32,
    pub tune_block_mode_limit: u32,
    pub tune_refinement_limit: u32,
    pub tune_candidate_limit: u32,
    pub tune_2partitioning_candidate_limit: u32,
    pub tune_3partitioning_candidate_limit: u32,
    pub tune_4partitioning_candidate_limit: u32,
    pub tune_db_limit: f32,
    pub tune_mse_overshoot: f32,
    pub tune_2partition_early_out_limit_factor: f32,
    pub tune_3partition_early_out_limit_factor: f32,
    pub tune_2plane_early_out_limit_correlation: f32,
    pub tune_search_mode0_enable: f32,
}

/// `get_u8_component_mask`.
#[inline]
pub fn get_u8_component_mask(decode_mode: u32, blk: &ImageBlock) -> VMask4 {
    if blk.decode_unorm8 {
        VMask4::splat(true)
    } else if decode_mode == PRF_LDR_SRGB {
        VMask4::new(true, true, true, false)
    } else {
        VMask4::splat(false)
    }
}
