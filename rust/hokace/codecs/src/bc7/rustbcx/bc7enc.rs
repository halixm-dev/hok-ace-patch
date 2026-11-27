//! BC7 block encoding: the port of `bc7enc.cpp` and `bc7enc.h` (Richard Geldreich, Jr.).
//!
//! Adapted from rustbcx 0.8.0 for HOK ACE. Retains only the single-block API.
//!
//! Supports modes 1 and 6 for RGB blocks, and modes 5, 6 and 7 for RGBA blocks.
//!
//! The C++ keeps the tables it makes at start-up in globals, filled by
//! `bc7enc_compress_block_init`. Here they are a [`Bc7Enc`], made by [`Bc7Enc::new`], and
//! `bc7enc_compress_block` is its method [`Bc7Enc::compress_block`]. The settings,
//! `bc7enc_compress_block_params`, are [`CompressBlockParams`].
//!
//! (The C++ file ends with a few helpers nothing in it uses: two tables of deflate's distance
//! costs, `compute_match_cost_estimate`, `tracked_stat`, `compute_block_max_std_dev` and
//! `bc7_block`. They are not here.)

// (Its colours are passed by reference, as the original passes them: by value, the encoder runs
// about 0.1% more instructions.)
#![allow(clippy::trivially_copy_pass_by_ref)]
// (As in the original, loops index several arrays in step.)
#![allow(clippy::needless_range_loop)]

use super::bc7decomp::{
    ANCHOR_INDEX_SECOND_SUBSET, ANCHOR_INDEX_THIRD_SUBSET_1, ANCHOR_INDEX_THIRD_SUBSET_2,
    ColorRgba, PARTITION2, PARTITION3,
};
use super::fmath;
use std::fmt;

const BLOCK_SIZE: usize = 16;
/// The most partitions modes 1 and 7 can try.
pub const MAX_PARTITIONS: u32 = 64;
/// The highest uber level.
pub const MAX_UBER_LEVEL: u32 = 4;

/// Why a single BC7 block could not be packed with these settings.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub enum CompressBlockError {
    /// The mode mask has none of the modes the block needs: 1 or 6 for an opaque block, 5, 6
    /// or 7 for one with alpha.
    NoModeAllowed,
    /// None of the modes allowed could pack the block: mode 1 is the only one and
    /// `max_partitions` is 0, or the error weights are out of range.
    NoModeFits,
    /// `force_selectors` is set and a selector does not fit any allowed mode for the block
    /// (16 or more, 8 or more without mode 6, or 4 or more in modes 5 and 7 only).
    SelectorOutOfRange,
}

impl fmt::Display for CompressBlockError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CompressBlockError::NoModeAllowed => {
                f.write_str("the mode mask has none of the modes the block needs")
            }
            CompressBlockError::NoModeFits => {
                f.write_str("none of the modes allowed could pack the block")
            }
            CompressBlockError::SelectorOutOfRange => {
                f.write_str("a forced selector does not fit any allowed mode")
            }
        }
    }
}

impl std::error::Error for CompressBlockError {}

/// The settings of [`Bc7Enc::compress_block`]: `bc7enc_compress_block_params`.
// (The original's switches, each independent of the others.)
#[allow(clippy::struct_excessive_bools)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CompressBlockParams {
    /// The modes the encoder may use, a bit for each (bit 1: mode 1, and so on). Opaque blocks
    /// need mode 1 or 6, blocks with alpha need mode 5, 6 or 7.
    pub mode_mask: u32,
    /// `max_partitions` may range from 0 (disables mode 1) to [`MAX_PARTITIONS`]. The higher this
    /// value, the slower the compressor, but the higher the quality.
    pub max_partitions: u32,
    /// Relative RGBA or YCbCrA weights.
    pub weights: [u32; 4],
    /// `uber_level` may range from 0 to [`MAX_UBER_LEVEL`]. The higher this value, the slower the
    /// compressor, but the higher the quality.
    pub uber_level: u32,
    /// If perceptual is true, colorspace error is computed in YCbCr space, otherwise RGB.
    pub perceptual: bool,
    /// Set `try_least_squares` to false for slightly faster/lower quality compression.
    pub try_least_squares: bool,
    /// When `mode17_partition_estimation_filterbank`, the mode1 partition estimator skips lesser
    /// used partition patterns unless they are strongly predicted to be potentially useful.
    /// There's a slight loss in quality with this enabled (around .08 dB RGB PSNR or .05 dB Y
    /// PSNR), but up to a 11% gain in speed depending on the other settings.
    pub mode17_partition_estimation_filterbank: bool,
    /// Pack every block as one with alpha, whatever its pixels' alpha.
    pub force_alpha: bool,
    /// Use `selectors` for the colour selectors and only look for the endpoints. A subset's
    /// pixels take them in order from the first, and they must fit the mode: below 16 for mode
    /// 6, below 8 for mode 1, below 4 for modes 5 and 7.
    pub force_selectors: bool,
    /// The selectors `force_selectors` uses.
    pub selectors: [u8; 16],
    /// Give mode 6's endpoints fewer steps, with the low endpoint's p-bit 0 and the high one's
    /// 1 (for the rate-distortion pass that follows).
    pub quant_mode6_endpoints: bool,
    /// Choose mode 1's p-bit from how bright the endpoints are, not by trying both.
    pub bias_mode1_pbits: bool,
    /// Scales the error of the endpoints tried with p-bit 1.
    pub pbit1_weight: f32,
    /// Scales mode 1's error when modes are compared. (The error weights must not be
    /// negative.)
    pub mode1_error_weight: f32,
    /// Scales mode 5's error when modes are compared.
    pub mode5_error_weight: f32,
    /// Scales mode 6's error when modes are compared.
    pub mode6_error_weight: f32,
    /// Scales mode 7's error when modes are compared.
    pub mode7_error_weight: f32,
    /// Scales the estimated error of the first sixteen partitions when one is chosen.
    pub low_frequency_partition_weight: f32,
}

impl Default for CompressBlockParams {
    fn default() -> Self {
        Self::new()
    }
}

impl CompressBlockParams {
    /// The usual settings: `bc7enc_compress_block_params_init`.
    #[must_use]
    pub fn new() -> Self {
        let mut params = CompressBlockParams {
            mode_mask: u32::MAX,
            max_partitions: MAX_PARTITIONS,
            weights: [0; 4],
            uber_level: 0,
            perceptual: false,
            try_least_squares: true,
            mode17_partition_estimation_filterbank: true,
            force_alpha: false,
            force_selectors: false,
            selectors: [0; 16],
            quant_mode6_endpoints: false,
            bias_mode1_pbits: false,
            pbit1_weight: 1.0,
            mode1_error_weight: 1.0,
            mode5_error_weight: 1.0,
            mode6_error_weight: 1.0,
            mode7_error_weight: 1.0,
            low_frequency_partition_weight: 1.0,
        };
        params.init_perceptual_weights();
        params
    }

    /// Error in YCbCr, brightness counting most:
    /// `bc7enc_compress_block_params_init_perceptual_weights`.
    pub fn init_perceptual_weights(&mut self) {
        self.perceptual = true;
        self.weights = [128, 64, 16, 32];
    }
}

/// The settings as the C++'s `print` writes them.
impl fmt::Display for CompressBlockParams {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        writeln!(f, "Mode mask: 0x{:X}", self.mode_mask)?;
        writeln!(f, "Max partitions: {}", self.max_partitions)?;
        writeln!(
            f,
            "Weights: {} {} {} {}",
            self.weights[0], self.weights[1], self.weights[2], self.weights[3]
        )?;
        writeln!(f, "Uber level: {}", self.uber_level)?;
        writeln!(f, "Perceptual: {}", u32::from(self.perceptual))?;
        writeln!(
            f,
            "Try least squares: {}",
            u32::from(self.try_least_squares)
        )?;
        writeln!(
            f,
            "Mode 1/7 partition estimation filterbank: {}",
            u32::from(self.mode17_partition_estimation_filterbank)
        )?;
        writeln!(f, "Force alpha: {}", u32::from(self.force_alpha))?;
        writeln!(
            f,
            "Quant mode 6 endpoints: {}",
            u32::from(self.quant_mode6_endpoints)
        )?;
        writeln!(
            f,
            "Bias mode 1 p-bits: {}",
            u32::from(self.bias_mode1_pbits)
        )?;
        writeln!(f, "p-bit 1 weight: {:.6}", self.pbit1_weight)?;
        writeln!(
            f,
            "Mode error weights: {:.6} {:.6} {:.6} {:.6}",
            self.mode1_error_weight,
            self.mode5_error_weight,
            self.mode6_error_weight,
            self.mode7_error_weight
        )?;
        writeln!(
            f,
            "Low frequency partition weight: {:.6}",
            self.low_frequency_partition_weight
        )
    }
}

// Helpers

/// A float to an int as C does it on x86 (the instruction the C++ compiles to): toward zero,
/// and the lowest int for what doesn't fit or is not a number.
#[inline]
fn f2i(value: f32) -> i32 {
    if (-2_147_483_648.0..2_147_483_648.0).contains(&value) {
        value as i32
    } else {
        i32::MIN
    }
}

#[inline]
fn clampi(value: i32, low: i32, high: i32) -> i32 {
    if value < low {
        low
    } else if value > high {
        high
    } else {
        value
    }
}

#[inline]
fn clampf(value: f32, low: f32, high: f32) -> f32 {
    if value < low {
        low
    } else if value > high {
        high
    } else {
        value
    }
}

#[inline]
fn saturate(value: f32) -> f32 {
    clampf(value, 0.0, 1.0)
}

#[inline]
fn minimumf(a: f32, b: f32) -> f32 {
    if a < b { a } else { b }
}

#[inline]
fn maximumf(a: f32, b: f32) -> f32 {
    if a > b { a } else { b }
}

/// `std::max` of two floats.
#[inline]
fn std_max(a: f32, b: f32) -> f32 {
    if a < b { b } else { a }
}

#[inline]
fn squarei(i: i32) -> i32 {
    i * i
}

#[inline]
fn squaref(i: f32) -> f32 {
    i * i
}

#[inline]
fn iabs32(v: i32) -> i32 {
    let msk = (v >> 31) as u32;
    ((v as u32) ^ msk).wrapping_sub(msk) as i32
}

type Vec4F = [f32; 4];

#[inline]
fn color_quad_u8_set_clamped(r: i32, g: i32, b: i32, a: i32) -> ColorRgba {
    [
        clampi(r, 0, 255) as u8,
        clampi(g, 0, 255) as u8,
        clampi(b, 0, 255) as u8,
        clampi(a, 0, 255) as u8,
    ]
}

#[inline]
fn color_quad_u8_set(r: u32, g: u32, b: u32, a: u32) -> ColorRgba {
    debug_assert!((r | g | b | a) <= 255);
    [r as u8, g as u8, b as u8, a as u8]
}

#[inline]
fn vec4f_saturate(v: &Vec4F) -> Vec4F {
    [
        saturate(v[0]),
        saturate(v[1]),
        saturate(v[2]),
        saturate(v[3]),
    ]
}

#[inline]
fn vec4f_from_color(c: &ColorRgba) -> Vec4F {
    [
        f32::from(c[0]),
        f32::from(c[1]),
        f32::from(c[2]),
        f32::from(c[3]),
    ]
}

#[inline]
fn vec4f_add(lhs: &Vec4F, rhs: &Vec4F) -> Vec4F {
    [
        lhs[0] + rhs[0],
        lhs[1] + rhs[1],
        lhs[2] + rhs[2],
        lhs[3] + rhs[3],
    ]
}

#[inline]
fn vec4f_sub(lhs: &Vec4F, rhs: &Vec4F) -> Vec4F {
    [
        lhs[0] - rhs[0],
        lhs[1] - rhs[1],
        lhs[2] - rhs[2],
        lhs[3] - rhs[3],
    ]
}

#[inline]
fn vec4f_dot(lhs: &Vec4F, rhs: &Vec4F) -> f32 {
    lhs[0] * rhs[0] + lhs[1] * rhs[1] + lhs[2] * rhs[2] + lhs[3] * rhs[3]
}

#[inline]
fn vec4f_mul(lhs: &Vec4F, s: f32) -> Vec4F {
    [lhs[0] * s, lhs[1] * s, lhs[2] * s, lhs[3] * s]
}

#[inline]
fn vec4f_normalize_in_place(v: &mut Vec4F) {
    let mut s = v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3];
    if s != 0.0 {
        s = 1.0 / s.sqrt();
        v[0] *= s;
        v[1] *= s;
        v[2] *= s;
        v[3] *= s;
    }
}

// Various BC7 tables
const WEIGHTS2: [u32; 4] = [0, 21, 43, 64];
const WEIGHTS3: [u32; 8] = [0, 9, 18, 27, 37, 46, 55, 64];
const WEIGHTS4: [u32; 16] = [0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64];
// Precomputed weight constants used during least fit determination. For each entry in the
// weights: w * w, (1.0f - w) * w, (1.0f - w) * (1.0f - w), w
#[rustfmt::skip]
const WEIGHTS2X: [f32; 4 * 4] = [0.000_000, 0.000_000, 1.000_000, 0.000_000, 0.107_666, 0.220_459, 0.451_416, 0.328_125, 0.451_416, 0.220_459, 0.107_666, 0.671_875, 1.000_000, 0.000_000, 0.000_000, 1.000_000];
#[rustfmt::skip]
const WEIGHTS3X: [f32; 8 * 4] = [0.000_000, 0.000_000, 1.000_000, 0.000_000, 0.019_775, 0.120_850, 0.738_525, 0.140_625, 0.079_102, 0.202_148, 0.516_602, 0.281_250, 0.177_979, 0.243_896, 0.334_229, 0.421_875, 0.334_229, 0.243_896, 0.177_979, 0.578_125, 0.516_602, 0.202_148,
    0.079_102, 0.718_750, 0.738_525, 0.120_850, 0.019_775, 0.859_375, 1.000_000, 0.000_000, 0.000_000, 1.000_000];
#[rustfmt::skip]
const WEIGHTS4X: [f32; 16 * 4] = [0.000_000, 0.000_000, 1.000_000, 0.000_000, 0.003_906, 0.058_594, 0.878_906, 0.062_500, 0.019_775, 0.120_850, 0.738_525, 0.140_625, 0.041_260, 0.161_865, 0.635_010, 0.203_125, 0.070_557, 0.195_068, 0.539_307, 0.265_625, 0.107_666, 0.220_459,
    0.451_416, 0.328_125, 0.165_039, 0.241_211, 0.352_539, 0.406_250, 0.219_727, 0.249_023, 0.282_227, 0.468_750, 0.282_227, 0.249_023, 0.219_727, 0.531_250, 0.352_539, 0.241_211, 0.165_039, 0.593_750, 0.451_416, 0.220_459, 0.107_666, 0.671_875, 0.539_307, 0.195_068, 0.070_557, 0.734_375,
    0.635_010, 0.161_865, 0.041_260, 0.796_875, 0.738_525, 0.120_850, 0.019_775, 0.859_375, 0.878_906, 0.058_594, 0.003_906, 0.937_500, 1.000_000, 0.000_000, 0.000_000, 1.000_000];

const PARTITION1: [u8; 16] = [0; 16];

const NUM_SUBSETS: [u8; 8] = [3, 2, 3, 2, 1, 1, 1, 2];
const PARTITION_BITS: [u8; 8] = [4, 6, 6, 6, 0, 0, 0, 6];
const COLOR_INDEX_BITCOUNT: [u8; 8] = [3, 3, 2, 2, 2, 2, 4, 2];

fn get_bc7_color_index_size(mode: u32, index_selection_bit: u32) -> u32 {
    u32::from(COLOR_INDEX_BITCOUNT[mode as usize]) + index_selection_bit
}

const ALPHA_INDEX_BITCOUNT: [u8; 8] = [0, 0, 0, 0, 3, 2, 4, 2];

fn get_bc7_alpha_index_size(mode: u32, index_selection_bit: u32) -> u32 {
    u32::from(ALPHA_INDEX_BITCOUNT[mode as usize]) - index_selection_bit
}

const MODE_HAS_P_BITS: [u8; 8] = [1, 1, 0, 1, 0, 0, 1, 1];
const MODE_HAS_SHARED_P_BITS: [u8; 8] = [0, 1, 0, 0, 0, 0, 0, 0];
const COLOR_PRECISION_TABLE: [u8; 8] = [4, 6, 5, 7, 5, 7, 7, 5];
const ALPHA_PRECISION_TABLE: [u8; 8] = [0, 0, 0, 0, 6, 8, 7, 5];

fn get_bc7_mode_has_seperate_alpha_selectors(mode: u32) -> bool {
    mode == 4 || mode == 5
}

#[derive(Clone, Copy, Default)]
struct EndpointErr {
    error: u16,
    lo: u8,
    hi: u8,
}

const MODE_1_OPTIMAL_INDEX: u32 = 2;
const MODE_7_OPTIMAL_INDEX: u32 = 1;

struct Bc7EncTables {
    /// By component value and p-bit.
    mode_1_optimal_endpoints: [[EndpointErr; 2]; 256],
    /// By component value, the high endpoint's p-bit and the low endpoint's p-bit.
    mode_7_optimal_endpoints: [[[EndpointErr; 2]; 2]; 256],
    mode1_rgba_midpoints: [[f32; 2]; 64],
    mode5_rgba_midpoints: [f32; 128],
    mode7_rgba_midpoints: [[f32; 2]; 32],
    mode6_reduced_quant: [[u8; 2]; 2048],
}

/// The BC7 encoder with the tables it makes at start-up.
#[derive(Clone, Copy)]
pub struct Bc7Enc {
    tables: &'static Bc7EncTables,
}

impl fmt::Debug for Bc7Enc {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Bc7Enc").finish_non_exhaustive()
    }
}

impl Default for Bc7Enc {
    fn default() -> Self {
        Self::new()
    }
}

fn compute_least_squares_endpoints_rgba(
    selectors: &[u8],
    selector_weights: &[f32],
    xl: &mut Vec4F,
    xh: &mut Vec4F,
    colors: &[ColorRgba],
) {
    // Least squares using normal equations:
    // http://www.cs.cornell.edu/~bindel/class/cs3220-s12/notes/lec10.pdf
    // I did this in matrix form first, expanded out all the ops, then optimized it a bit.
    let (mut z00, mut z10, mut z11) = (0.0f32, 0.0f32, 0.0f32);
    let (mut q00_r, mut t_r) = (0.0f32, 0.0f32);
    let (mut q00_g, mut t_g) = (0.0f32, 0.0f32);
    let (mut q00_b, mut t_b) = (0.0f32, 0.0f32);
    let (mut q00_a, mut t_a) = (0.0f32, 0.0f32);
    for (i, color) in colors.iter().enumerate() {
        let sel = selectors[i] as usize;
        z00 += selector_weights[sel * 4];
        z10 += selector_weights[sel * 4 + 1];
        z11 += selector_weights[sel * 4 + 2];
        let w = selector_weights[sel * 4 + 3];
        q00_r += w * f32::from(color[0]);
        t_r += f32::from(color[0]);
        q00_g += w * f32::from(color[1]);
        t_g += f32::from(color[1]);
        q00_b += w * f32::from(color[2]);
        t_b += f32::from(color[2]);
        q00_a += w * f32::from(color[3]);
        t_a += f32::from(color[3]);
    }

    let q10_r = t_r - q00_r;
    let q10_g = t_g - q00_g;
    let q10_b = t_b - q00_b;
    let q10_a = t_a - q00_a;

    let z01 = z10;

    let mut det = z00 * z11 - z01 * z10;
    if det != 0.0 {
        det = 1.0 / det;
    }

    let iz00 = z11 * det;
    let iz01 = -z01 * det;
    let iz10 = -z10 * det;
    let iz11 = z00 * det;

    xl[0] = iz00 * q00_r + iz01 * q10_r;
    xh[0] = iz10 * q00_r + iz11 * q10_r;
    xl[1] = iz00 * q00_g + iz01 * q10_g;
    xh[1] = iz10 * q00_g + iz11 * q10_g;
    xl[2] = iz00 * q00_b + iz01 * q10_b;
    xh[2] = iz10 * q00_b + iz11 * q10_b;
    xl[3] = iz00 * q00_a + iz01 * q10_a;
    xh[3] = iz10 * q00_a + iz11 * q10_a;

    for c in 0..4 {
        if xl[c] < 0.0 || xh[c] > 255.0 {
            let (mut lo_v, mut hi_v) = (u32::MAX, 0u32);
            for color in colors {
                lo_v = lo_v.min(u32::from(color[c]));
                hi_v = hi_v.max(u32::from(color[c]));
            }
            if lo_v == hi_v {
                xl[c] = lo_v as f32;
                xh[c] = hi_v as f32;
            }
        }
    }
}

fn compute_least_squares_endpoints_rgb(
    selectors: &[u8],
    selector_weights: &[f32],
    xl: &mut Vec4F,
    xh: &mut Vec4F,
    colors: &[ColorRgba],
) {
    let (mut z00, mut z10, mut z11) = (0.0f32, 0.0f32, 0.0f32);
    let (mut q00_r, mut t_r) = (0.0f32, 0.0f32);
    let (mut q00_g, mut t_g) = (0.0f32, 0.0f32);
    let (mut q00_b, mut t_b) = (0.0f32, 0.0f32);
    for (i, color) in colors.iter().enumerate() {
        let sel = selectors[i] as usize;
        z00 += selector_weights[sel * 4];
        z10 += selector_weights[sel * 4 + 1];
        z11 += selector_weights[sel * 4 + 2];
        let w = selector_weights[sel * 4 + 3];
        q00_r += w * f32::from(color[0]);
        t_r += f32::from(color[0]);
        q00_g += w * f32::from(color[1]);
        t_g += f32::from(color[1]);
        q00_b += w * f32::from(color[2]);
        t_b += f32::from(color[2]);
    }

    let q10_r = t_r - q00_r;
    let q10_g = t_g - q00_g;
    let q10_b = t_b - q00_b;

    let z01 = z10;

    let mut det = z00 * z11 - z01 * z10;
    if det != 0.0 {
        det = 1.0 / det;
    }

    let iz00 = z11 * det;
    let iz01 = -z01 * det;
    let iz10 = -z10 * det;
    let iz11 = z00 * det;

    xl[0] = iz00 * q00_r + iz01 * q10_r;
    xh[0] = iz10 * q00_r + iz11 * q10_r;
    xl[1] = iz00 * q00_g + iz01 * q10_g;
    xh[1] = iz10 * q00_g + iz11 * q10_g;
    xl[2] = iz00 * q00_b + iz01 * q10_b;
    xh[2] = iz10 * q00_b + iz11 * q10_b;
    xl[3] = 255.0;
    xh[3] = 255.0;

    for c in 0..3 {
        if xl[c] < 0.0 || xh[c] > 255.0 {
            let (mut lo_v, mut hi_v) = (u32::MAX, 0u32);
            for color in colors {
                lo_v = lo_v.min(u32::from(color[c]));
                hi_v = hi_v.max(u32::from(color[c]));
            }
            if lo_v == hi_v {
                xl[c] = lo_v as f32;
                xh[c] = hi_v as f32;
            }
        }
    }
}

/// The low and the high alpha.
fn compute_least_squares_endpoints_a(
    selectors: &[u8],
    selector_weights: &[f32],
    colors: &[ColorRgba],
) -> (f32, f32) {
    // Least squares using normal equations:
    // http://www.cs.cornell.edu/~bindel/class/cs3220-s12/notes/lec10.pdf
    // I did this in matrix form first, expanded out all the ops, then optimized it a bit.
    let (mut z00, mut z10, mut z11) = (0.0f32, 0.0f32, 0.0f32);
    let (mut q00_a, mut t_a) = (0.0f32, 0.0f32);
    for (i, color) in colors.iter().enumerate() {
        let sel = selectors[i] as usize;
        z00 += selector_weights[sel * 4];
        z10 += selector_weights[sel * 4 + 1];
        z11 += selector_weights[sel * 4 + 2];
        let w = selector_weights[sel * 4 + 3];
        q00_a += w * f32::from(color[3]);
        t_a += f32::from(color[3]);
    }

    let q10_a = t_a - q00_a;

    let z01 = z10;

    let mut det = z00 * z11 - z01 * z10;
    if det != 0.0 {
        det = 1.0 / det;
    }

    let iz00 = z11 * det;
    let iz01 = -z01 * det;
    let iz10 = -z10 * det;
    let iz11 = z00 * det;

    let mut xl = iz00 * q00_a + iz01 * q10_a;
    let mut xh = iz10 * q00_a + iz11 * q10_a;

    if xl < 0.0 || xh > 255.0 {
        let (mut lo_v, mut hi_v) = (u32::MAX, 0u32);
        for color in colors {
            lo_v = lo_v.min(u32::from(color[3]));
            hi_v = hi_v.max(u32::from(color[3]));
        }
        if lo_v == hi_v {
            xl = lo_v as f32;
            xh = hi_v as f32;
        }
    }
    (xl, xh)
}

/// What a subset is packed with. (The C++'s also holds the subset's pixels; here they are
/// passed beside it.)
// (The original's switches, each independent of the others.)
#[allow(clippy::struct_excessive_bools)]
#[derive(Clone, Copy)]
struct ColorCellCompressorParams {
    num_selector_weights: u32,
    selector_weights: &'static [u32],
    selector_weightsx: &'static [f32],
    comp_bits: u32,
    weights: [u32; 4],
    has_alpha: bool,
    has_pbits: bool,
    endpoints_share_pbit: bool,
    perceptual: bool,
}

/// The best way found to pack a subset. (The C++'s points at its selectors and at a scratch
/// copy of them; here it holds the selectors, and the scratch copy is where it is used.)
#[derive(Clone, Copy)]
struct ColorCellCompressorResults {
    best_overall_err: u64,
    low_endpoint: ColorRgba,
    high_endpoint: ColorRgba,
    pbits: [u32; 2],
    selectors: [u8; 16],
}

impl ColorCellCompressorResults {
    fn new() -> Self {
        ColorCellCompressorResults {
            best_overall_err: 0,
            low_endpoint: [0; 4],
            high_endpoint: [0; 4],
            pbits: [0; 2],
            selectors: [0; 16],
        }
    }
}

/// A subset packed as one colour: what the two `pack_mode*_to_one_color` leave in the
/// results. Each of the subset's selectors is then the mode's optimal index.
struct OneColor {
    low_endpoint: ColorRgba,
    high_endpoint: ColorRgba,
    pbits: [u32; 2],
    total_err: u64,
}

#[inline]
fn scale_color(c: &ColorRgba, params: &ColorCellCompressorParams) -> ColorRgba {
    let mut results = [0u8; 4];

    let n = params.comp_bits + u32::from(params.has_pbits);
    debug_assert!((4..=8).contains(&n));

    for i in 0..4 {
        let mut v = u32::from(c[i]) << (8 - n);
        v |= v >> n;
        debug_assert!(v <= 255);
        results[i] = v as u8;
    }

    results
}

#[inline]
fn compute_color_distance_rgb(
    e1: &ColorRgba,
    e2: &ColorRgba,
    perceptual: bool,
    weights: &[u32; 4],
) -> u64 {
    let (dr, dg, db);

    if perceptual {
        let l1 = i32::from(e1[0]) * 109 + i32::from(e1[1]) * 366 + i32::from(e1[2]) * 37;
        let cr1 = (i32::from(e1[0]) << 9) - l1;
        let cb1 = (i32::from(e1[2]) << 9) - l1;
        let l2 = i32::from(e2[0]) * 109 + i32::from(e2[1]) * 366 + i32::from(e2[2]) * 37;
        let cr2 = (i32::from(e2[0]) << 9) - l2;
        let cb2 = (i32::from(e2[2]) << 9) - l2;
        dr = (l1 - l2) >> 8;
        dg = (cr1 - cr2) >> 8;
        db = (cb1 - cb2) >> 8;
    } else {
        dr = i32::from(e1[0]) - i32::from(e2[0]);
        dg = i32::from(e1[1]) - i32::from(e2[1]);
        db = i32::from(e1[2]) - i32::from(e2[2]);
    }

    // (The sum is of 32 bits in the C++.)
    u64::from(
        weights[0]
            .wrapping_mul((dr * dr) as u32)
            .wrapping_add(weights[1].wrapping_mul((dg * dg) as u32))
            .wrapping_add(weights[2].wrapping_mul((db * db) as u32)),
    )
}

#[inline]
fn compute_color_distance_rgba(
    e1: &ColorRgba,
    e2: &ColorRgba,
    perceptual: bool,
    weights: &[u32; 4],
) -> u64 {
    let da = i32::from(e1[3]) - i32::from(e2[3]);
    compute_color_distance_rgb(e1, e2, perceptual, weights)
        + u64::from(weights[3].wrapping_mul((da * da) as u32))
}

// (One pass, step for step as the original's, its state shared throughout; the names are the
// original's, so that the code reads against the original.)
#[allow(clippy::too_many_lines, clippy::many_single_char_names)]
fn evaluate_solution(
    low: &ColorRgba,
    high: &ColorRgba,
    pbits: &[u32; 2],
    params: &ColorCellCompressorParams,
    pixels: &[ColorRgba],
    results: &mut ColorCellCompressorResults,
    comp_params: &CompressBlockParams,
) -> u64 {
    let mut quant_min_color = *low;
    let mut quant_max_color = *high;

    if params.has_pbits {
        let (min_pbit, max_pbit);

        if params.endpoints_share_pbit {
            min_pbit = pbits[0];
            max_pbit = pbits[0];
        } else {
            min_pbit = pbits[0];
            max_pbit = pbits[1];
        }

        for c in 0..4 {
            quant_min_color[c] = ((u32::from(low[c]) << 1) | min_pbit) as u8;
            quant_max_color[c] = ((u32::from(high[c]) << 1) | max_pbit) as u8;
        }
    }

    let actual_min_color = scale_color(&quant_min_color, params);
    let actual_max_color = scale_color(&quant_max_color, params);

    let n = params.num_selector_weights as usize;

    let mut weighted_colors = [[0u8; 4]; 16];
    weighted_colors[0] = actual_min_color;
    weighted_colors[n - 1] = actual_max_color;

    let nc = if params.has_alpha { 4 } else { 3 };
    for i in 1..(n - 1) {
        for j in 0..nc {
            weighted_colors[i][j] = ((u32::from(actual_min_color[j])
                * (64 - params.selector_weights[i])
                + u32::from(actual_max_color[j]) * params.selector_weights[i]
                + 32)
                >> 6) as u8;
        }
    }

    let lr = i32::from(actual_min_color[0]);
    let lg = i32::from(actual_min_color[1]);
    let lb = i32::from(actual_min_color[2]);
    let dr = i32::from(actual_max_color[0]) - lr;
    let dg = i32::from(actual_max_color[1]) - lg;
    let db = i32::from(actual_max_color[2]) - lb;

    let mut selectors_temp = [0u8; 16];

    let mut total_err = 0u64;

    if comp_params.force_selectors {
        for (i, pixel) in pixels.iter().enumerate() {
            let best_sel = (comp_params.selectors[i] as usize) & (n - 1);

            let best_err = if params.has_alpha {
                compute_color_distance_rgba(
                    &weighted_colors[best_sel],
                    pixel,
                    params.perceptual,
                    &params.weights,
                )
            } else {
                compute_color_distance_rgb(
                    &weighted_colors[best_sel],
                    pixel,
                    params.perceptual,
                    &params.weights,
                )
            };

            total_err += best_err;

            selectors_temp[i] = best_sel as u8;
        }
    } else if !params.perceptual {
        if params.has_alpha {
            let la = i32::from(actual_min_color[3]);
            let da = i32::from(actual_max_color[3]) - la;

            let f = n as f32
                / ((squarei(dr) + squarei(dg) + squarei(db) + squarei(da)) as f32
                    + 0.000_001_25_f32);

            for (i, c) in pixels.iter().enumerate() {
                let r = i32::from(c[0]);
                let g = i32::from(c[1]);
                let b = i32::from(c[2]);
                let a = i32::from(c[3]);

                let mut best_sel =
                    f2i(
                        ((r - lr) * dr + (g - lg) * dg + (b - lb) * db + (a - la) * da) as f32 * f
                            + 0.5,
                    );
                best_sel = clampi(best_sel, 1, n as i32 - 1);

                let err0 = compute_color_distance_rgba(
                    &weighted_colors[best_sel as usize - 1],
                    c,
                    false,
                    &params.weights,
                );
                let mut err1 = compute_color_distance_rgba(
                    &weighted_colors[best_sel as usize],
                    c,
                    false,
                    &params.weights,
                );

                if err1 > err0 {
                    err1 = err0;
                    best_sel -= 1;
                }
                total_err += err1;

                selectors_temp[i] = best_sel as u8;
            }
        } else {
            let f =
                n as f32 / ((squarei(dr) + squarei(dg) + squarei(db)) as f32 + 0.000_001_25_f32);

            for (i, c) in pixels.iter().enumerate() {
                let r = i32::from(c[0]);
                let g = i32::from(c[1]);
                let b = i32::from(c[2]);

                let mut sel = f2i(((r - lr) * dr + (g - lg) * dg + (b - lb) * db) as f32 * f + 0.5);
                sel = clampi(sel, 1, n as i32 - 1);

                let err0 = compute_color_distance_rgb(
                    &weighted_colors[sel as usize - 1],
                    c,
                    false,
                    &params.weights,
                );
                let err1 = compute_color_distance_rgb(
                    &weighted_colors[sel as usize],
                    c,
                    false,
                    &params.weights,
                );

                let mut best_sel = sel;
                let mut best_err = err1;
                if err0 < best_err {
                    best_err = err0;
                    best_sel = sel - 1;
                }

                total_err += best_err;

                selectors_temp[i] = best_sel as u8;
            }
        }
    } else {
        // TODO: This could be improved.
        for (i, pixel) in pixels.iter().enumerate() {
            let mut best_err = u64::MAX;
            let mut best_sel = 0usize;

            if params.has_alpha {
                for j in 0..n {
                    let err = compute_color_distance_rgba(
                        &weighted_colors[j],
                        pixel,
                        true,
                        &params.weights,
                    );
                    if err < best_err {
                        best_err = err;
                        best_sel = j;
                    }
                }
            } else {
                for j in 0..n {
                    let err = compute_color_distance_rgb(
                        &weighted_colors[j],
                        pixel,
                        true,
                        &params.weights,
                    );
                    if err < best_err {
                        best_err = err;
                        best_sel = j;
                    }
                }
            }

            total_err += best_err;

            selectors_temp[i] = best_sel as u8;
        }
    }

    if total_err < results.best_overall_err {
        results.best_overall_err = total_err;

        results.low_endpoint = *low;
        results.high_endpoint = *high;

        results.pbits[0] = pbits[0];
        results.pbits[1] = pbits[1];

        results.selectors[..pixels.len()].copy_from_slice(&selectors_temp[..pixels.len()]);
    }

    total_err
}

fn fix_degenerate_endpoints(
    mode: u32,
    trial_min_color: &mut ColorRgba,
    trial_max_color: &mut ColorRgba,
    xl: &Vec4F,
    xh: &Vec4F,
    iscale: u32,
    comp_params: &CompressBlockParams,
) {
    if mode == 1 || (mode == 6 && comp_params.quant_mode6_endpoints) {
        // fix degenerate case where the input collapses to a single colorspace voxel, and we
        // loose all freedom (test with grayscale ramps)
        for i in 0..3 {
            if trial_min_color[i] == trial_max_color[i] && (xl[i] - xh[i]).abs() > 0.0 {
                if u32::from(trial_min_color[i]) > (iscale >> 1) {
                    if trial_min_color[i] > 0 {
                        trial_min_color[i] -= 1;
                    } else if u32::from(trial_max_color[i]) < iscale {
                        trial_max_color[i] += 1;
                    }
                } else if u32::from(trial_max_color[i]) < iscale {
                    trial_max_color[i] += 1;
                } else if trial_min_color[i] > 0 {
                    trial_min_color[i] -= 1;
                }
            }
        }
    }
}

impl Bc7Enc {
    /// The encoder with the lookup tables used for optimal single color compression in mode
    /// 1/7 and the rest: `bc7enc_compress_block_init`. The tables are made the first time and
    /// shared from then on.
    #[must_use]
    pub fn new() -> Self {
        static TABLES: std::sync::OnceLock<Bc7EncTables> = std::sync::OnceLock::new();
        Bc7Enc {
            tables: TABLES.get_or_init(Bc7Enc::make_tables),
        }
    }

    /// Makes the tables.
    // (One pass, step for step as the original's, its state shared throughout.)
    #[allow(clippy::too_many_lines)]
    fn make_tables() -> Bc7EncTables {
        let mut tables = Bc7EncTables {
            mode_1_optimal_endpoints: [[EndpointErr::default(); 2]; 256],
            mode_7_optimal_endpoints: [[[EndpointErr::default(); 2]; 2]; 256],
            mode1_rgba_midpoints: [[0.0; 2]; 64],
            mode5_rgba_midpoints: [0.0; 128],
            mode7_rgba_midpoints: [[0.0; 2]; 32],
            mode6_reduced_quant: [[0; 2]; 2048],
        };

        // Mode 7 endpoint midpoints
        for p in 0..2u32 {
            for i in 0..32u32 {
                let mut vl = ((i << 1) | p) << 2;
                vl |= vl >> 6;
                let lo = vl as f32 / 255.0;

                let mut vh = (((i + 1).min(31) << 1) | p) << 2;
                vh |= vh >> 6;
                let hi = vh as f32 / 255.0;

                tables.mode7_rgba_midpoints[i as usize][p as usize] =
                    if i == 31 { 1.0 } else { (lo + hi) / 2.0 };
            }
        }

        // Mode 1 endpoint midpoints
        for p in 0..2u32 {
            for i in 0..64u32 {
                let mut vl = ((i << 1) | p) << 1;
                vl |= vl >> 7;
                let lo = vl as f32 / 255.0;

                let mut vh = (((i + 1).min(63) << 1) | p) << 1;
                vh |= vh >> 7;
                let hi = vh as f32 / 255.0;

                tables.mode1_rgba_midpoints[i as usize][p as usize] =
                    if i == 63 { 1.0 } else { (lo + hi) / 2.0 };
            }
        }

        // Mode 5 endpoint midpoints
        for i in 0..128u32 {
            let mut vl = i << 1;
            vl |= vl >> 7;
            let lo = vl as f32 / 255.0;

            let mut vh = (i + 1).min(127) << 1;
            vh |= vh >> 7;
            let hi = vh as f32 / 255.0;

            tables.mode5_rgba_midpoints[i as usize] = if i == 127 { 1.0 } else { (lo + hi) / 2.0 };
        }

        for p in 0..2u32 {
            for i in 0..2048u32 {
                let f = i as f32 / 2047.0;

                let mut best_err = 1e+9f32;
                let mut best_index = 0i32;
                for j in 0..64i32 {
                    let ik = (j * 127 + 31) / 63;
                    let k = ((ik << 1) as u32 + p) as f32 / 255.0;

                    let e = (k - f).abs();
                    if e < best_err {
                        best_err = e;
                        best_index = ik;
                    }
                }

                tables.mode6_reduced_quant[i as usize][p as usize] = best_index as u8;
            }
        }

        // Mode 1
        for c in 0..256i32 {
            for lp in 0..2u32 {
                let mut best = EndpointErr {
                    error: u16::MAX,
                    lo: 0,
                    hi: 0,
                };

                for l in 0..64u32 {
                    let mut low = ((l << 1) | lp) << 1;
                    low |= low >> 7;

                    for h in 0..64u32 {
                        let mut high = ((h << 1) | lp) << 1;
                        high |= high >> 7;

                        let k = ((low * (64 - WEIGHTS3[MODE_1_OPTIMAL_INDEX as usize])
                            + high * WEIGHTS3[MODE_1_OPTIMAL_INDEX as usize]
                            + 32)
                            >> 6) as i32;

                        let err = (k - c) * (k - c);
                        if err < i32::from(best.error) {
                            best.error = err as u16;
                            best.lo = l as u8;
                            best.hi = h as u8;
                        }
                    }
                }

                tables.mode_1_optimal_endpoints[c as usize][lp as usize] = best;
            }
        }

        // Mode 7: 555.1 2-bit indices
        for c in 0..256i32 {
            for hp in 0..2u32 {
                for lp in 0..2u32 {
                    let mut best = EndpointErr {
                        error: u16::MAX,
                        lo: 0,
                        hi: 0,
                    };

                    for l in 0..32u32 {
                        let mut low = ((l << 1) | lp) << 2;
                        low |= low >> 6;

                        for h in 0..32u32 {
                            let mut high = ((h << 1) | hp) << 2;
                            high |= high >> 6;

                            let k = ((low * (64 - WEIGHTS2[MODE_7_OPTIMAL_INDEX as usize])
                                + high * WEIGHTS2[MODE_7_OPTIMAL_INDEX as usize]
                                + 32)
                                >> 6) as i32;

                            let err = (k - c) * (k - c);
                            if err < i32::from(best.error) {
                                best.error = err as u16;
                                best.lo = l as u8;
                                best.hi = h as u8;
                            }
                        }
                    }

                    tables.mode_7_optimal_endpoints[c as usize][hp as usize][lp as usize] = best;
                }
            }
        }

        tables
    }

    fn pack_mode1_to_one_color(
        &self,
        params: &ColorCellCompressorParams,
        pixels: &[ColorRgba],
        r: u32,
        g: u32,
        b: u32,
    ) -> OneColor {
        let table = &self.tables.mode_1_optimal_endpoints;
        let (r, g, b) = (r as usize, g as usize, b as usize);

        let mut best_err = u32::MAX;
        let mut best_p = 0usize;

        for p in 0..2 {
            let err = u32::from(table[r][p].error)
                + u32::from(table[g][p].error)
                + u32::from(table[b][p].error);
            if err < best_err {
                best_err = err;
                best_p = p;
                if best_err == 0 {
                    break;
                }
            }
        }

        let er = &table[r][best_p];
        let eg = &table[g][best_p];
        let eb = &table[b][best_p];

        let low_endpoint =
            color_quad_u8_set(u32::from(er.lo), u32::from(eg.lo), u32::from(eb.lo), 0);
        let high_endpoint =
            color_quad_u8_set(u32::from(er.hi), u32::from(eg.hi), u32::from(eb.hi), 0);

        let pbits = [best_p as u32, 0];

        let mut p = [0u8; 4];

        for i in 0..3 {
            let mut low = ((u32::from(low_endpoint[i]) << 1) | pbits[0]) << 1;
            low |= low >> 7;

            let mut high = ((u32::from(high_endpoint[i]) << 1) | pbits[0]) << 1;
            high |= high >> 7;

            p[i] = ((low * (64 - WEIGHTS3[MODE_1_OPTIMAL_INDEX as usize])
                + high * WEIGHTS3[MODE_1_OPTIMAL_INDEX as usize]
                + 32)
                >> 6) as u8;
        }

        p[3] = 255;

        let mut total_err = 0u64;
        for pixel in pixels {
            total_err += compute_color_distance_rgb(&p, pixel, params.perceptual, &params.weights);
        }

        OneColor {
            low_endpoint,
            high_endpoint,
            pbits,
            total_err,
        }
    }

    // (The names are the original's, so that the code reads against the original.)
    #[allow(clippy::many_single_char_names)]
    fn pack_mode7_to_one_color(
        &self,
        params: &ColorCellCompressorParams,
        pixels: &[ColorRgba],
        r: u32,
        g: u32,
        b: u32,
        a: u32,
    ) -> OneColor {
        let table = &self.tables.mode_7_optimal_endpoints;
        let (r, g, b, a) = (r as usize, g as usize, b as usize, a as usize);

        let mut best_err = u32::MAX;
        let mut best_p = 0usize;

        for p in 0..4usize {
            let hi_p = p >> 1;
            let lo_p = p & 1;
            let err = u32::from(table[r][hi_p][lo_p].error)
                + u32::from(table[g][hi_p][lo_p].error)
                + u32::from(table[b][hi_p][lo_p].error)
                + u32::from(table[a][hi_p][lo_p].error);
            if err < best_err {
                best_err = err;
                best_p = p;
                if best_err == 0 {
                    break;
                }
            }
        }

        let best_hi_p = best_p >> 1;
        let best_lo_p = best_p & 1;

        let er = &table[r][best_hi_p][best_lo_p];
        let eg = &table[g][best_hi_p][best_lo_p];
        let eb = &table[b][best_hi_p][best_lo_p];
        let ea = &table[a][best_hi_p][best_lo_p];

        let low_endpoint = color_quad_u8_set(
            u32::from(er.lo),
            u32::from(eg.lo),
            u32::from(eb.lo),
            u32::from(ea.lo),
        );
        let high_endpoint = color_quad_u8_set(
            u32::from(er.hi),
            u32::from(eg.hi),
            u32::from(eb.hi),
            u32::from(ea.hi),
        );

        let pbits = [best_lo_p as u32, best_hi_p as u32];

        let mut p = [0u8; 4];

        for i in 0..4 {
            let mut low = (u32::from(low_endpoint[i]) << 1) | pbits[0];
            let mut high = (u32::from(high_endpoint[i]) << 1) | pbits[1];

            low = (low << 2) | (low >> 6);
            high = (high << 2) | (high >> 6);

            p[i] = ((low * (64 - WEIGHTS2[MODE_7_OPTIMAL_INDEX as usize])
                + high * WEIGHTS2[MODE_7_OPTIMAL_INDEX as usize]
                + 32)
                >> 6) as u8;
        }

        let mut total_err = 0u64;
        for pixel in pixels {
            total_err += compute_color_distance_rgba(&p, pixel, params.perceptual, &params.weights);
        }

        OneColor {
            low_endpoint,
            high_endpoint,
            pbits,
            total_err,
        }
    }

    // (Its parameters are the original's, each a separate part of the state; one pass, step for
    // step as the original's, its state shared throughout.)
    #[allow(clippy::too_many_arguments, clippy::too_many_lines)]
    fn find_optimal_solution(
        &self,
        mode: u32,
        xl: Vec4F,
        xh: Vec4F,
        params: &ColorCellCompressorParams,
        pixels: &[ColorRgba],
        results: &mut ColorCellCompressorResults,
        comp_params: &CompressBlockParams,
    ) -> u64 {
        let xl = vec4f_saturate(&xl);
        let xh = vec4f_saturate(&xh);

        if params.has_pbits {
            let iscalep = (1i32 << (params.comp_bits + 1)) - 1;
            let scalep = iscalep as f32;

            let total_comps = if params.has_alpha { 4 } else { 3 };

            let mut best_pbits = [0u32; 2];
            let mut best_min_color = [0u8; 4];
            let mut best_max_color = [0u8; 4];

            if !params.endpoints_share_pbit {
                if params.comp_bits == 7 && comp_params.quant_mode6_endpoints {
                    best_pbits[0] = 0;
                    for c in 0..4 {
                        best_min_color[c] = self.tables.mode6_reduced_quant
                            [f2i((xl[c] * 2047.0) + 0.5) as usize][0];
                    }

                    best_pbits[1] = 1;
                    for c in 0..4 {
                        best_max_color[c] = self.tables.mode6_reduced_quant
                            [f2i((xh[c] * 2047.0) + 0.5) as usize][1];
                    }
                } else {
                    let mut best_err0 = 1e+9f32;
                    let mut best_err1 = 1e+9f32;

                    for p in 0..2i32 {
                        let mut x_min_color = [0u8; 4];
                        let mut x_max_color = [0u8; 4];

                        // Notes: The pbit controls which quantization intervals are selected.
                        // total_levels=2^(comp_bits+1), where comp_bits=4 for mode 0, etc.
                        // pbit 0: v=(b*2)/(total_levels-1), pbit 1:
                        // v=(b*2+1)/(total_levels-1) where b is the component bin from
                        // [0,total_levels/2-1] and v is the [0,1] component value
                        // rearranging you get for pbit 0: b=floor(v*(total_levels-1)/2+.5)
                        // rearranging you get for pbit 1: b=floor((v*(total_levels-1)-1)/2+.5)
                        if params.comp_bits == 5 {
                            for c in 0..4 {
                                let mut vl = f2i(xl[c] * 31.0);
                                vl += i32::from(
                                    xl[c]
                                        > self.tables.mode7_rgba_midpoints[vl as usize][p as usize],
                                );
                                x_min_color[c] = clampi(vl * 2 + p, p, 63 - 1 + p) as u8;

                                let mut vh = f2i(xh[c] * 31.0);
                                vh += i32::from(
                                    xh[c]
                                        > self.tables.mode7_rgba_midpoints[vh as usize][p as usize],
                                );
                                x_max_color[c] = clampi(vh * 2 + p, p, 63 - 1 + p) as u8;
                            }
                        } else {
                            for c in 0..4 {
                                x_min_color[c] = clampi(
                                    f2i((xl[c] * scalep - p as f32) / 2.0 + 0.5) * 2 + p,
                                    p,
                                    iscalep - 1 + p,
                                ) as u8;
                                x_max_color[c] = clampi(
                                    f2i((xh[c] * scalep - p as f32) / 2.0 + 0.5) * 2 + p,
                                    p,
                                    iscalep - 1 + p,
                                ) as u8;
                            }
                        }

                        let scaled_low = scale_color(&x_min_color, params);
                        let scaled_high = scale_color(&x_max_color, params);

                        let (mut err0, mut err1) = (0.0f32, 0.0f32);
                        for i in 0..total_comps {
                            err0 += squaref(f32::from(scaled_low[i]) - xl[i] * 255.0);
                            err1 += squaref(f32::from(scaled_high[i]) - xh[i] * 255.0);
                        }

                        if p == 1 {
                            err0 *= comp_params.pbit1_weight;
                            err1 *= comp_params.pbit1_weight;
                        }

                        if err0 < best_err0 {
                            best_err0 = err0;
                            best_pbits[0] = p as u32;

                            for c in 0..4 {
                                best_min_color[c] = x_min_color[c] >> 1;
                            }
                        }

                        if err1 < best_err1 {
                            best_err1 = err1;
                            best_pbits[1] = p as u32;

                            for c in 0..4 {
                                best_max_color[c] = x_max_color[c] >> 1;
                            }
                        }
                    }
                }
            } else if mode == 1 && comp_params.bias_mode1_pbits {
                let mut x = 0.0f32;
                for c in 0..3 {
                    x = std_max(std_max(x, xl[c]), xh[c]);
                }

                let mut p = 0i32;
                if x > (253.0f32 / 255.0f32) {
                    p = 1;
                }

                let mut x_min_color = [0u8; 4];
                let mut x_max_color = [0u8; 4];
                for c in 0..4 {
                    let mut vl = f2i(xl[c] * 63.0);
                    vl += i32::from(
                        xl[c] > self.tables.mode1_rgba_midpoints[vl as usize][p as usize],
                    );
                    x_min_color[c] = clampi(vl * 2 + p, p, 127 - 1 + p) as u8;

                    let mut vh = f2i(xh[c] * 63.0);
                    vh += i32::from(
                        xh[c] > self.tables.mode1_rgba_midpoints[vh as usize][p as usize],
                    );
                    x_max_color[c] = clampi(vh * 2 + p, p, 127 - 1 + p) as u8;
                }

                best_pbits[0] = p as u32;
                best_pbits[1] = p as u32;
                for j in 0..4 {
                    best_min_color[j] = x_min_color[j] >> 1;
                    best_max_color[j] = x_max_color[j] >> 1;
                }
            } else {
                // Endpoints share pbits
                let mut best_err = 1e+9f32;

                for p in 0..2i32 {
                    let mut x_min_color = [0u8; 4];
                    let mut x_max_color = [0u8; 4];

                    if params.comp_bits == 6 {
                        for c in 0..4 {
                            let mut vl = f2i(xl[c] * 63.0);
                            vl += i32::from(
                                xl[c] > self.tables.mode1_rgba_midpoints[vl as usize][p as usize],
                            );
                            x_min_color[c] = clampi(vl * 2 + p, p, 127 - 1 + p) as u8;

                            let mut vh = f2i(xh[c] * 63.0);
                            vh += i32::from(
                                xh[c] > self.tables.mode1_rgba_midpoints[vh as usize][p as usize],
                            );
                            x_max_color[c] = clampi(vh * 2 + p, p, 127 - 1 + p) as u8;
                        }
                    } else {
                        for c in 0..4 {
                            x_min_color[c] = clampi(
                                f2i((xl[c] * scalep - p as f32) / 2.0 + 0.5) * 2 + p,
                                p,
                                iscalep - 1 + p,
                            ) as u8;
                            x_max_color[c] = clampi(
                                f2i((xh[c] * scalep - p as f32) / 2.0 + 0.5) * 2 + p,
                                p,
                                iscalep - 1 + p,
                            ) as u8;
                        }
                    }

                    let scaled_low = scale_color(&x_min_color, params);
                    let scaled_high = scale_color(&x_max_color, params);

                    let mut err = 0.0f32;
                    for i in 0..total_comps {
                        err += squaref((f32::from(scaled_low[i]) / 255.0) - xl[i])
                            + squaref((f32::from(scaled_high[i]) / 255.0) - xh[i]);
                    }

                    if p == 1 {
                        err *= comp_params.pbit1_weight;
                    }

                    if err < best_err {
                        best_err = err;
                        best_pbits[0] = p as u32;
                        best_pbits[1] = p as u32;
                        for j in 0..4 {
                            best_min_color[j] = x_min_color[j] >> 1;
                            best_max_color[j] = x_max_color[j] >> 1;
                        }
                    }
                }
            }

            fix_degenerate_endpoints(
                mode,
                &mut best_min_color,
                &mut best_max_color,
                &xl,
                &xh,
                (iscalep >> 1) as u32,
                comp_params,
            );

            if results.best_overall_err == u64::MAX
                || best_min_color != results.low_endpoint
                || best_max_color != results.high_endpoint
                || best_pbits[0] != results.pbits[0]
                || best_pbits[1] != results.pbits[1]
            {
                evaluate_solution(
                    &best_min_color,
                    &best_max_color,
                    &best_pbits,
                    params,
                    pixels,
                    results,
                    comp_params,
                );
            }
        } else {
            let iscale = (1i32 << params.comp_bits) - 1;
            let scale = iscale as f32;

            let mut trial_min_color = [0u8; 4];
            let mut trial_max_color = [0u8; 4];
            if params.comp_bits == 7 {
                for c in 0..4 {
                    let mut vl = f2i(xl[c] * 127.0);
                    vl += i32::from(xl[c] > self.tables.mode5_rgba_midpoints[vl as usize]);
                    trial_min_color[c] = clampi(vl, 0, 127) as u8;

                    let mut vh = f2i(xh[c] * 127.0);
                    vh += i32::from(xh[c] > self.tables.mode5_rgba_midpoints[vh as usize]);
                    trial_max_color[c] = clampi(vh, 0, 127) as u8;
                }
            } else {
                trial_min_color = color_quad_u8_set_clamped(
                    f2i(xl[0] * scale + 0.5),
                    f2i(xl[1] * scale + 0.5),
                    f2i(xl[2] * scale + 0.5),
                    f2i(xl[3] * scale + 0.5),
                );
                trial_max_color = color_quad_u8_set_clamped(
                    f2i(xh[0] * scale + 0.5),
                    f2i(xh[1] * scale + 0.5),
                    f2i(xh[2] * scale + 0.5),
                    f2i(xh[3] * scale + 0.5),
                );
            }

            fix_degenerate_endpoints(
                mode,
                &mut trial_min_color,
                &mut trial_max_color,
                &xl,
                &xh,
                iscale as u32,
                comp_params,
            );

            if results.best_overall_err == u64::MAX
                || trial_min_color != results.low_endpoint
                || trial_max_color != results.high_endpoint
            {
                let pbits = results.pbits;
                evaluate_solution(
                    &trial_min_color,
                    &trial_max_color,
                    &pbits,
                    params,
                    pixels,
                    results,
                    comp_params,
                );
            }
        }

        results.best_overall_err
    }

    // (One pass, step for step as the original's, its state shared throughout; the names are the
    // original's, so that the code reads against the original.)
    #[allow(clippy::too_many_lines, clippy::many_single_char_names)]
    fn color_cell_compression(
        &self,
        mode: u32,
        params: &ColorCellCompressorParams,
        pixels: &[ColorRgba],
        results: &mut ColorCellCompressorResults,
        comp_params: &CompressBlockParams,
    ) -> u64 {
        debug_assert!(mode == 6 || mode == 7 || !params.has_alpha);

        let num_pixels = pixels.len();

        results.best_overall_err = u64::MAX;

        // If the partition's colors are all the same in
        // mode 1, then just pack them as a single color.
        if mode == 1 {
            let (cr, cg, cb) = (pixels[0][0], pixels[0][1], pixels[0][2]);

            let all_same = pixels[1..]
                .iter()
                .all(|pixel| cr == pixel[0] && cg == pixel[1] && cb == pixel[2]);

            if all_same {
                let one = self.pack_mode1_to_one_color(
                    params,
                    pixels,
                    u32::from(cr),
                    u32::from(cg),
                    u32::from(cb),
                );
                results.low_endpoint = one.low_endpoint;
                results.high_endpoint = one.high_endpoint;
                results.pbits = one.pbits;
                results.selectors[..num_pixels].fill(MODE_1_OPTIMAL_INDEX as u8);
                results.best_overall_err = one.total_err;
                return one.total_err;
            }
        } else if mode == 7 {
            let first = pixels[0];

            let all_same = pixels[1..].iter().all(|pixel| *pixel == first);

            if all_same {
                let one = self.pack_mode7_to_one_color(
                    params,
                    pixels,
                    u32::from(first[0]),
                    u32::from(first[1]),
                    u32::from(first[2]),
                    u32::from(first[3]),
                );
                results.low_endpoint = one.low_endpoint;
                results.high_endpoint = one.high_endpoint;
                results.pbits = one.pbits;
                results.selectors[..num_pixels].fill(MODE_7_OPTIMAL_INDEX as u8);
                results.best_overall_err = one.total_err;
                return one.total_err;
            }
        }

        // Compute partition's mean color and principle axis.
        let mut mean_color = [0.0f32; 4];
        let mut axis = [0.0f32; 4];

        for pixel in pixels {
            let color = vec4f_from_color(pixel);
            mean_color = vec4f_add(&mean_color, &color);
        }

        let mean_color_scaled = vec4f_mul(&mean_color, 1.0 / (num_pixels as f32));

        mean_color = vec4f_mul(&mean_color, 1.0 / (num_pixels as f32 * 255.0));
        mean_color = vec4f_saturate(&mean_color);

        if params.has_alpha {
            // Use incremental PCA for RGBA PCA, because it's simple.
            for (i, pixel) in pixels.iter().enumerate() {
                let mut color = vec4f_from_color(pixel);
                color = vec4f_sub(&color, &mean_color_scaled);

                let a = vec4f_mul(&color, color[0]);
                let b = vec4f_mul(&color, color[1]);
                let c = vec4f_mul(&color, color[2]);
                let d = vec4f_mul(&color, color[3]);

                let mut n = if i != 0 { axis } else { color };
                vec4f_normalize_in_place(&mut n);

                axis[0] += vec4f_dot(&a, &n);
                axis[1] += vec4f_dot(&b, &n);
                axis[2] += vec4f_dot(&c, &n);
                axis[3] += vec4f_dot(&d, &n);
            }
            vec4f_normalize_in_place(&mut axis);
        } else {
            // Use covar technique for RGB PCA, because it doesn't require per-pixel normalization.
            let mut cov = [0.0f32; 6];

            for pixel in pixels {
                let r = f32::from(pixel[0]) - mean_color_scaled[0];
                let g = f32::from(pixel[1]) - mean_color_scaled[1];
                let b = f32::from(pixel[2]) - mean_color_scaled[2];
                cov[0] += r * r;
                cov[1] += r * g;
                cov[2] += r * b;
                cov[3] += g * g;
                cov[4] += g * b;
                cov[5] += b * b;
            }

            let (mut vfr, mut vfg, mut vfb) = (0.9f32, 1.0f32, 0.7f32);
            for _ in 0..3 {
                let mut r = vfr * cov[0] + vfg * cov[1] + vfb * cov[2];
                let mut g = vfr * cov[1] + vfg * cov[3] + vfb * cov[4];
                let mut b = vfr * cov[2] + vfg * cov[4] + vfb * cov[5];

                let mut m = maximumf(maximumf(r.abs(), g.abs()), b.abs());
                if m > 1e-10f32 {
                    m = 1.0 / m;
                    r *= m;
                    g *= m;
                    b *= m;
                }

                vfr = r;
                vfg = g;
                vfb = b;
            }

            let mut len = vfr * vfr + vfg * vfg + vfb * vfb;

            if len < 1e-10f32 {
                axis = [0.0; 4];
            } else {
                len = 1.0 / len.sqrt();
                vfr *= len;
                vfg *= len;
                vfb *= len;
                axis = [vfr, vfg, vfb, 0.0];
            }
        }

        // TODO: Try picking the 2 colors with the largest projection
        // onto the axis, instead of computing new colors along the axis.

        if vec4f_dot(&axis, &axis) < 0.5 {
            if params.perceptual {
                axis = [
                    0.213,
                    0.715,
                    0.072,
                    if params.has_alpha { 0.715 } else { 0.0 },
                ];
            } else {
                axis = [1.0, 1.0, 1.0, if params.has_alpha { 1.0 } else { 0.0 }];
            }
            vec4f_normalize_in_place(&mut axis);
        }

        let (mut l, mut h) = (1e+9f32, -1e+9f32);

        for pixel in pixels {
            let color = vec4f_from_color(pixel);

            let q = vec4f_sub(&color, &mean_color_scaled);
            let d = vec4f_dot(&q, &axis);

            l = minimumf(l, d);
            h = maximumf(h, d);
        }

        l *= 1.0f32 / 255.0f32;
        h *= 1.0f32 / 255.0f32;

        let b0 = vec4f_mul(&axis, l);
        let b1 = vec4f_mul(&axis, h);
        let c0 = vec4f_add(&mean_color, &b0);
        let c1 = vec4f_add(&mean_color, &b1);
        let mut min_color = vec4f_saturate(&c0);
        let mut max_color = vec4f_saturate(&c1);

        let white_vec = [1.0f32; 4];
        if vec4f_dot(&min_color, &white_vec) > vec4f_dot(&max_color, &white_vec) {
            std::mem::swap(&mut min_color, &mut max_color);
        }

        // First find a solution using the block's PCA.
        if self.find_optimal_solution(
            mode,
            min_color,
            max_color,
            params,
            pixels,
            results,
            comp_params,
        ) == 0
        {
            return 0;
        }

        let least_squares = |selectors: &[u8]| -> (Vec4F, Vec4F) {
            let mut xl = [0.0f32; 4];
            let mut xh = [0.0f32; 4];
            if params.has_alpha {
                compute_least_squares_endpoints_rgba(
                    selectors,
                    params.selector_weightsx,
                    &mut xl,
                    &mut xh,
                    pixels,
                );
            } else {
                compute_least_squares_endpoints_rgb(
                    selectors,
                    params.selector_weightsx,
                    &mut xl,
                    &mut xh,
                    pixels,
                );
            }

            (
                vec4f_mul(&xl, 1.0f32 / 255.0f32),
                vec4f_mul(&xh, 1.0f32 / 255.0f32),
            )
        };

        if comp_params.try_least_squares {
            // Now try to refine the solution using least squares by
            // computing the optimal endpoints from the current selectors.
            let (xl, xh) = least_squares(&results.selectors);
            if self.find_optimal_solution(mode, xl, xh, params, pixels, results, comp_params) == 0 {
                return 0;
            }
        }

        let uber_level = comp_params.uber_level.min(MAX_UBER_LEVEL);
        if uber_level > 0 {
            // In uber level 1, try varying the selectors a little, somewhat like
            // cluster fit would. First try incrementing the minimum selectors,
            // then try decrementing the selectrors, then try both.
            let mut selectors_temp = [0u8; 16];
            let mut selectors_temp1 = [0u8; 16];
            selectors_temp[..num_pixels].copy_from_slice(&results.selectors[..num_pixels]);

            let max_selector = params.num_selector_weights as i32 - 1;

            let mut min_sel = 16u32;
            let mut max_sel = 0u32;
            for i in 0..num_pixels {
                let sel = u32::from(selectors_temp[i]);
                min_sel = min_sel.min(sel);
                max_sel = max_sel.max(sel);
            }

            for i in 0..num_pixels {
                let mut sel = u32::from(selectors_temp[i]);
                if sel == min_sel && sel < (params.num_selector_weights - 1) {
                    sel += 1;
                }
                selectors_temp1[i] = sel as u8;
            }

            let (xl, xh) = least_squares(&selectors_temp1);
            if self.find_optimal_solution(mode, xl, xh, params, pixels, results, comp_params) == 0 {
                return 0;
            }

            for i in 0..num_pixels {
                let mut sel = u32::from(selectors_temp[i]);
                if sel == max_sel && sel > 0 {
                    sel -= 1;
                }
                selectors_temp1[i] = sel as u8;
            }

            let (xl, xh) = least_squares(&selectors_temp1);
            if self.find_optimal_solution(mode, xl, xh, params, pixels, results, comp_params) == 0 {
                return 0;
            }

            for i in 0..num_pixels {
                let mut sel = u32::from(selectors_temp[i]);
                if sel == min_sel && sel < (params.num_selector_weights - 1) {
                    sel += 1;
                } else if sel == max_sel && sel > 0 {
                    sel -= 1;
                }
                selectors_temp1[i] = sel as u8;
            }

            let (xl, xh) = least_squares(&selectors_temp1);
            if self.find_optimal_solution(mode, xl, xh, params, pixels, results, comp_params) == 0 {
                return 0;
            }

            // In uber levels 2+, try taking more advantage of endpoint
            // extrapolation by scaling the selectors in one direction or another.
            let uber_err_thresh = (num_pixels as u32 * 56) >> 4;
            if uber_level >= 2 && results.best_overall_err > u64::from(uber_err_thresh) {
                let q = if uber_level >= 4 {
                    (uber_level - 2) as i32
                } else {
                    1
                };
                for ly in -q..=1 {
                    for hy in (max_selector - 1)..=(max_selector + q) {
                        if ly == 0 && hy == max_selector {
                            continue;
                        }

                        for i in 0..num_pixels {
                            selectors_temp1[i] = clampf(
                                fmath::floor(
                                    max_selector as f32
                                        * (f32::from(selectors_temp[i]) - ly as f32)
                                        / (hy as f32 - ly as f32)
                                        + 0.5,
                                ),
                                0.0,
                                max_selector as f32,
                            ) as u8;
                        }

                        let (xl, xh) = least_squares(&selectors_temp1);
                        if self.find_optimal_solution(
                            mode,
                            xl,
                            xh,
                            params,
                            pixels,
                            results,
                            comp_params,
                        ) == 0
                        {
                            return 0;
                        }
                    }
                }
            }
        }

        if mode == 1 {
            // Try encoding the partition as a single color by using the
            // optimal singe colors tables to encode the block to its mean.
            let r = f2i(0.5 + mean_color[0] * 255.0) as u32;
            let g = f2i(0.5 + mean_color[1] * 255.0) as u32;
            let b = f2i(0.5 + mean_color[2] * 255.0) as u32;
            let avg = self.pack_mode1_to_one_color(params, pixels, r, g, b);

            if avg.total_err < results.best_overall_err {
                results.low_endpoint = avg.low_endpoint;
                results.high_endpoint = avg.high_endpoint;
                results.pbits = avg.pbits;
                results.selectors[..num_pixels].fill(MODE_1_OPTIMAL_INDEX as u8);
                results.best_overall_err = avg.total_err;
            }
        } else if mode == 7 {
            // Try encoding the partition as a single color by using the
            // optimal singe colors tables to encode the block to its mean.
            let r = f2i(0.5 + mean_color[0] * 255.0) as u32;
            let g = f2i(0.5 + mean_color[1] * 255.0) as u32;
            let b = f2i(0.5 + mean_color[2] * 255.0) as u32;
            let a = f2i(0.5 + mean_color[3] * 255.0) as u32;
            let avg = self.pack_mode7_to_one_color(params, pixels, r, g, b, a);

            if avg.total_err < results.best_overall_err {
                results.low_endpoint = avg.low_endpoint;
                results.high_endpoint = avg.high_endpoint;
                results.pbits = avg.pbits;
                results.selectors[..num_pixels].fill(MODE_7_OPTIMAL_INDEX as u8);
                results.best_overall_err = avg.total_err;
            }
        }

        results.best_overall_err
    }
}

// (One pass, step for step as the original's, its state shared throughout.)
#[allow(clippy::too_many_lines)]
fn color_cell_compression_est_mode1(
    pixels: &[ColorRgba],
    perceptual: bool,
    pweights: &[u32; 4],
    best_err_so_far: u64,
) -> u64 {
    const N: usize = 8;
    // Find RGB bounds as an approximation of the block's principle axis
    let (mut lr, mut lg, mut lb) = (255u32, 255u32, 255u32);
    let (mut hr, mut hg, mut hb) = (0u32, 0u32, 0u32);
    for c in pixels {
        if u32::from(c[0]) < lr {
            lr = u32::from(c[0]);
        }
        if u32::from(c[1]) < lg {
            lg = u32::from(c[1]);
        }
        if u32::from(c[2]) < lb {
            lb = u32::from(c[2]);
        }
        if u32::from(c[0]) > hr {
            hr = u32::from(c[0]);
        }
        if u32::from(c[1]) > hg {
            hg = u32::from(c[1]);
        }
        if u32::from(c[2]) > hb {
            hb = u32::from(c[2]);
        }
    }

    let low_color = color_quad_u8_set(lr, lg, lb, 0);
    let high_color = color_quad_u8_set(hr, hg, hb, 0);

    // Place endpoints at bbox diagonals and compute interpolated colors
    let mut weighted_colors = [[0u8; 4]; N];

    weighted_colors[0] = low_color;
    weighted_colors[N - 1] = high_color;
    for i in 1..(N - 1) {
        for c in 0..3 {
            weighted_colors[i][c] = ((u32::from(low_color[c]) * (64 - WEIGHTS3[i])
                + u32::from(high_color[c]) * WEIGHTS3[i]
                + 32)
                >> 6) as u8;
        }
    }

    // Compute dots and thresholds
    let ar = i32::from(high_color[0]) - i32::from(low_color[0]);
    let ag = i32::from(high_color[1]) - i32::from(low_color[1]);
    let ab = i32::from(high_color[2]) - i32::from(low_color[2]);

    let mut dots = [0i32; N];
    for i in 0..N {
        dots[i] = i32::from(weighted_colors[i][0]) * ar
            + i32::from(weighted_colors[i][1]) * ag
            + i32::from(weighted_colors[i][2]) * ab;
    }

    let mut thresh = [0i32; N - 1];
    for i in 0..(N - 1) {
        thresh[i] = (dots[i] + dots[i + 1] + 1) >> 1;
    }

    // Find approximate selector
    let selector = |d: i32| -> usize {
        if d >= thresh[6] {
            7
        } else if d >= thresh[5] {
            6
        } else if d >= thresh[4] {
            5
        } else if d >= thresh[3] {
            4
        } else if d >= thresh[2] {
            3
        } else if d >= thresh[1] {
            2
        } else {
            usize::from(d >= thresh[0])
        }
    };

    let mut total_err = 0u64;
    if perceptual {
        // Transform block's interpolated colors to YCbCr
        let mut l1 = [0i32; N];
        let mut cr1 = [0i32; N];
        let mut cb1 = [0i32; N];
        for j in 0..N {
            let e1 = &weighted_colors[j];
            l1[j] = i32::from(e1[0]) * 109 + i32::from(e1[1]) * 366 + i32::from(e1[2]) * 37;
            cr1[j] = (i32::from(e1[0]) << 9) - l1[j];
            cb1[j] = (i32::from(e1[2]) << 9) - l1[j];
        }

        for c in pixels {
            let d = ar * i32::from(c[0]) + ag * i32::from(c[1]) + ab * i32::from(c[2]);

            let s = selector(d);

            // Compute error
            let l2 = i32::from(c[0]) * 109 + i32::from(c[1]) * 366 + i32::from(c[2]) * 37;
            let cr2 = (i32::from(c[0]) << 9) - l2;
            let cb2 = (i32::from(c[2]) << 9) - l2;

            let dl = (l1[s] - l2) >> 8;
            let dcr = (cr1[s] - cr2) >> 8;
            let dcb = (cb1[s] - cb2) >> 8;

            // (The C++ works this out unsigned, keeps it in an int, and adds that to the
            // 64-bit total.)
            let ie = pweights[0]
                .wrapping_mul(dl as u32)
                .wrapping_mul(dl as u32)
                .wrapping_add(
                    pweights[1]
                        .wrapping_mul(dcr as u32)
                        .wrapping_mul(dcr as u32),
                )
                .wrapping_add(
                    pweights[2]
                        .wrapping_mul(dcb as u32)
                        .wrapping_mul(dcb as u32),
                ) as i32;

            total_err = total_err.wrapping_add(i64::from(ie) as u64);
            if total_err > best_err_so_far {
                break;
            }
        }
    } else {
        for c in pixels {
            let d = ar * i32::from(c[0]) + ag * i32::from(c[1]) + ab * i32::from(c[2]);

            let s = selector(d);

            // Compute error
            let e1 = &weighted_colors[s];

            let dr = i32::from(e1[0]) - i32::from(c[0]);
            let dg = i32::from(e1[1]) - i32::from(c[1]);
            let db = i32::from(e1[2]) - i32::from(c[2]);

            total_err += u64::from(
                pweights[0]
                    .wrapping_mul((dr * dr) as u32)
                    .wrapping_add(pweights[1].wrapping_mul((dg * dg) as u32))
                    .wrapping_add(pweights[2].wrapping_mul((db * db) as u32)),
            );
            if total_err > best_err_so_far {
                break;
            }
        }
    }

    total_err
}

// (One pass, step for step as the original's, its state shared throughout.)
#[allow(clippy::too_many_lines)]
fn color_cell_compression_est_mode7(
    pixels: &[ColorRgba],
    perceptual: bool,
    pweights: &[u32; 4],
    best_err_so_far: u64,
) -> u64 {
    const N: usize = 4;
    // Find RGB bounds as an approximation of the block's principle axis
    let (mut lr, mut lg, mut lb, mut la) = (255u32, 255u32, 255u32, 255u32);
    let (mut hr, mut hg, mut hb, mut ha) = (0u32, 0u32, 0u32, 0u32);
    for c in pixels {
        if u32::from(c[0]) < lr {
            lr = u32::from(c[0]);
        }
        if u32::from(c[1]) < lg {
            lg = u32::from(c[1]);
        }
        if u32::from(c[2]) < lb {
            lb = u32::from(c[2]);
        }
        if u32::from(c[3]) < la {
            la = u32::from(c[3]);
        }
        if u32::from(c[0]) > hr {
            hr = u32::from(c[0]);
        }
        if u32::from(c[1]) > hg {
            hg = u32::from(c[1]);
        }
        if u32::from(c[2]) > hb {
            hb = u32::from(c[2]);
        }
        if u32::from(c[3]) > ha {
            ha = u32::from(c[3]);
        }
    }

    let low_color = color_quad_u8_set(lr, lg, lb, la);
    let high_color = color_quad_u8_set(hr, hg, hb, ha);

    // Place endpoints at bbox diagonals and compute interpolated colors
    let mut weighted_colors = [[0u8; 4]; N];

    weighted_colors[0] = low_color;
    weighted_colors[N - 1] = high_color;
    for i in 1..(N - 1) {
        for c in 0..4 {
            weighted_colors[i][c] = ((u32::from(low_color[c]) * (64 - WEIGHTS2[i])
                + u32::from(high_color[c]) * WEIGHTS2[i]
                + 32)
                >> 6) as u8;
        }
    }

    // Compute dots and thresholds
    let ar = i32::from(high_color[0]) - i32::from(low_color[0]);
    let ag = i32::from(high_color[1]) - i32::from(low_color[1]);
    let ab = i32::from(high_color[2]) - i32::from(low_color[2]);
    let aa = i32::from(high_color[3]) - i32::from(low_color[3]);

    let mut dots = [0i32; N];
    for i in 0..N {
        dots[i] = i32::from(weighted_colors[i][0]) * ar
            + i32::from(weighted_colors[i][1]) * ag
            + i32::from(weighted_colors[i][2]) * ab
            + i32::from(weighted_colors[i][3]) * aa;
    }

    let mut thresh = [0i32; N - 1];
    for i in 0..(N - 1) {
        thresh[i] = (dots[i] + dots[i + 1] + 1) >> 1;
    }

    // Find approximate selector
    let selector = |d: i32| -> usize {
        if d >= thresh[2] {
            3
        } else if d >= thresh[1] {
            2
        } else {
            usize::from(d >= thresh[0])
        }
    };

    let mut total_err = 0u64;
    if perceptual {
        // Transform block's interpolated colors to YCbCr
        let mut l1 = [0i32; N];
        let mut cr1 = [0i32; N];
        let mut cb1 = [0i32; N];
        for j in 0..N {
            let e1 = &weighted_colors[j];
            l1[j] = i32::from(e1[0]) * 109 + i32::from(e1[1]) * 366 + i32::from(e1[2]) * 37;
            cr1[j] = (i32::from(e1[0]) << 9) - l1[j];
            cb1[j] = (i32::from(e1[2]) << 9) - l1[j];
        }

        for c in pixels {
            let d = ar * i32::from(c[0])
                + ag * i32::from(c[1])
                + ab * i32::from(c[2])
                + aa * i32::from(c[3]);

            let s = selector(d);

            // Compute error
            let l2 = i32::from(c[0]) * 109 + i32::from(c[1]) * 366 + i32::from(c[2]) * 37;
            let cr2 = (i32::from(c[0]) << 9) - l2;
            let cb2 = (i32::from(c[2]) << 9) - l2;

            let dl = (l1[s] - l2) >> 8;
            let dcr = (cr1[s] - cr2) >> 8;
            let dcb = (cb1[s] - cb2) >> 8;

            let dca = i32::from(c[3]) - i32::from(weighted_colors[s][3]);

            // (Unsigned, kept in an int, added to the 64-bit total: as in mode 1's.)
            let ie = pweights[0]
                .wrapping_mul(dl as u32)
                .wrapping_mul(dl as u32)
                .wrapping_add(
                    pweights[1]
                        .wrapping_mul(dcr as u32)
                        .wrapping_mul(dcr as u32),
                )
                .wrapping_add(
                    pweights[2]
                        .wrapping_mul(dcb as u32)
                        .wrapping_mul(dcb as u32),
                )
                .wrapping_add(
                    pweights[3]
                        .wrapping_mul(dca as u32)
                        .wrapping_mul(dca as u32),
                ) as i32;

            total_err = total_err.wrapping_add(i64::from(ie) as u64);
            if total_err > best_err_so_far {
                break;
            }
        }
    } else {
        for c in pixels {
            let d = ar * i32::from(c[0])
                + ag * i32::from(c[1])
                + ab * i32::from(c[2])
                + aa * i32::from(c[3]);

            let s = selector(d);

            // Compute error
            let e1 = &weighted_colors[s];

            let dr = i32::from(e1[0]) - i32::from(c[0]);
            let dg = i32::from(e1[1]) - i32::from(c[1]);
            let db = i32::from(e1[2]) - i32::from(c[2]);
            let da = i32::from(e1[3]) - i32::from(c[3]);

            total_err += u64::from(
                pweights[0]
                    .wrapping_mul((dr * dr) as u32)
                    .wrapping_add(pweights[1].wrapping_mul((dg * dg) as u32))
                    .wrapping_add(pweights[2].wrapping_mul((db * db) as u32))
                    .wrapping_add(pweights[3].wrapping_mul((da * da) as u32)),
            );
            if total_err > best_err_so_far {
                break;
            }
        }
    }

    total_err
}

// This table contains bitmasks indicating which "key" partitions
// must be best ranked before this partition is worth evaluating.
// We first rank the best/most used 14 partitions (sorted by
// usefulness), record the best one found as the key partition, then use
// that to control the other partitions to evaluate. The quality loss
// is ~.08 dB RGB PSNR, the perf gain is up to ~11% (at uber level 0).
const PARTITION_PREDICTORS: [u32; 35] = [
    u32::MAX,
    u32::MAX,
    u32::MAX,
    u32::MAX,
    u32::MAX,
    (1 << 1) | (1 << 2) | (1 << 8),
    (1 << 1) | (1 << 3) | (1 << 7),
    u32::MAX,
    u32::MAX,
    (1 << 2) | (1 << 8) | (1 << 16),
    (1 << 7) | (1 << 3) | (1 << 15),
    u32::MAX,
    (1 << 8) | (1 << 14) | (1 << 16),
    (1 << 7) | (1 << 14) | (1 << 15),
    u32::MAX,
    u32::MAX,
    u32::MAX,
    u32::MAX,
    (1 << 14) | (1 << 15),
    (1 << 16) | (1 << 22) | (1 << 14),
    (1 << 17) | (1 << 24) | (1 << 14),
    (1 << 2) | (1 << 14) | (1 << 15) | (1 << 1),
    u32::MAX,
    (1 << 1) | (1 << 3) | (1 << 14) | (1 << 16) | (1 << 22),
    u32::MAX,
    (1 << 1) | (1 << 2) | (1 << 15) | (1 << 17) | (1 << 24),
    (1 << 1) | (1 << 3) | (1 << 22),
    u32::MAX,
    u32::MAX,
    u32::MAX,
    (1 << 14) | (1 << 15) | (1 << 16) | (1 << 17),
    u32::MAX,
    u32::MAX,
    (1 << 1) | (1 << 2) | (1 << 3) | (1 << 27) | (1 << 4) | (1 << 24),
    (1 << 14) | (1 << 15) | (1 << 16) | (1 << 11) | (1 << 17) | (1 << 27),
];

// Partition order sorted by usage frequency across a large test
// corpus. Pattern 34 (checkerboard) must appear in slot 34.
// Using a sorted order allows the user to decrease the
// # of partitions to scan with minimal loss in quality.
#[rustfmt::skip]
#[allow(clippy::eq_op)]
const SORTED_PARTITION_ORDER: [u8; 64] = [
    1 - 1, 14 - 1, 2 - 1, 3 - 1, 16 - 1, 15 - 1, 11 - 1, 17 - 1,
    4 - 1, 24 - 1, 27 - 1, 7 - 1, 8 - 1, 22 - 1, 20 - 1, 30 - 1,
    9 - 1, 5 - 1, 10 - 1, 21 - 1, 6 - 1, 32 - 1, 23 - 1, 18 - 1,
    19 - 1, 12 - 1, 13 - 1, 31 - 1, 25 - 1, 26 - 1, 29 - 1, 28 - 1,
    33 - 1, 34 - 1, 35 - 1, 46 - 1, 47 - 1, 52 - 1, 50 - 1, 51 - 1,
    49 - 1, 39 - 1, 40 - 1, 38 - 1, 54 - 1, 53 - 1, 55 - 1, 37 - 1,
    58 - 1, 59 - 1, 56 - 1, 42 - 1, 41 - 1, 43 - 1, 44 - 1, 60 - 1,
    45 - 1, 57 - 1, 48 - 1, 36 - 1, 61 - 1, 64 - 1, 63 - 1, 62 - 1,
];

/// A block's pixels dealt out to the two subsets of a partition: each subset's pixels, how
/// many it has, and where in the block each came from.
struct Subsets {
    colors: [[ColorRgba; 16]; 2],
    total_colors: [usize; 2],
    pixel_index: [[u8; 16]; 2],
}

impl Subsets {
    fn new(pixels: &[ColorRgba; 16], partition: u32) -> Self {
        let table = &PARTITION2[partition as usize * 16..partition as usize * 16 + 16];
        let mut subsets = Subsets {
            colors: [[[0; 4]; 16]; 2],
            total_colors: [0; 2],
            pixel_index: [[0; 16]; 2],
        };
        for index in 0..16 {
            let p = table[index] as usize;
            subsets.colors[p][subsets.total_colors[p]] = pixels[index];
            subsets.pixel_index[p][subsets.total_colors[p]] = index as u8;
            subsets.total_colors[p] += 1;
        }
        subsets
    }

    fn pixels(&self, subset: usize) -> &[ColorRgba] {
        &self.colors[subset][..self.total_colors[subset]]
    }
}

// Estimate the partition used by modes 1/7. This scans through
// each partition and computes an approximate error for each.
fn estimate_partition(
    pixels: &[ColorRgba; 16],
    comp_params: &CompressBlockParams,
    pweights: &[u32; 4],
    mode: u32,
) -> u32 {
    let total_partitions = comp_params.max_partitions.min(MAX_PARTITIONS);
    if total_partitions <= 1 {
        return 0;
    }

    let mut best_err = u64::MAX;
    let mut best_partition = 0u32;

    debug_assert_eq!(SORTED_PARTITION_ORDER[34], 34);

    let mut best_key_partition = 0u32;

    let mut partition_iter = 0u32;
    while partition_iter < total_partitions && best_err > 0 {
        let partition = u32::from(SORTED_PARTITION_ORDER[partition_iter as usize]);

        // Check to see if we should bother evaluating this partition at
        // all, depending on the best partition found from the first 14.
        if comp_params.mode17_partition_estimation_filterbank && (14..=34).contains(&partition_iter)
        {
            let best_key_partition_bitmask = 1u32 << (best_key_partition + 1);
            if (PARTITION_PREDICTORS[partition as usize] & best_key_partition_bitmask) == 0 {
                if partition_iter == 34 {
                    break;
                }

                partition_iter += 1;
                continue;
            }
        }

        let subsets = Subsets::new(pixels, partition);

        let mut total_subset_err = 0u64;

        let mut subset = 0;
        while subset < 2 && total_subset_err < best_err {
            if mode == 7 {
                total_subset_err = total_subset_err.wrapping_add(color_cell_compression_est_mode7(
                    subsets.pixels(subset),
                    comp_params.perceptual,
                    pweights,
                    best_err,
                ));
            } else {
                total_subset_err = total_subset_err.wrapping_add(color_cell_compression_est_mode1(
                    subsets.pixels(subset),
                    comp_params.perceptual,
                    pweights,
                    best_err,
                ));
            }
            subset += 1;
        }

        if partition < 16 {
            total_subset_err = (total_subset_err as f64
                * f64::from(comp_params.low_frequency_partition_weight)
                + f64::from(0.5f32)) as u64;
        }

        if total_subset_err < best_err {
            best_err = total_subset_err;
            best_partition = partition;
        }

        // If the checkerboard pattern doesn't get the highest ranking vs. the
        // previous (lower frequency) patterns, then just stop now because
        // statistically the subsequent patterns won't do well either.
        if partition == 34 && best_partition != 34 {
            break;
        }

        if partition_iter == 13 {
            best_key_partition = best_partition;
        }

        partition_iter += 1;
    }

    best_partition
}

fn set_block_bits(bytes: &mut [u8; 16], mut val: u32, mut num_bits: u32, cur_ofs: &mut u32) {
    debug_assert!(num_bits <= 32 && u64::from(val) < (1u64 << num_bits));
    while num_bits != 0 {
        let n = (8 - (*cur_ofs & 7)).min(num_bits);
        bytes[(*cur_ofs >> 3) as usize] |= (val << (*cur_ofs & 7)) as u8;
        val >>= n;
        num_bits -= n;
        *cur_ofs += n;
    }
    debug_assert!(*cur_ofs <= 128);
}

/// How a block is to be packed: `bc7_optimization_results`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct OptimizationResults {
    /// The block's mode, 0 to 7.
    pub mode: u32,
    /// The partition, for the modes of more than one subset.
    pub partition: u32,
    /// Each pixel's colour selector.
    pub selectors: [u8; 16],
    /// Each pixel's alpha selector, for modes 4 and 5.
    pub alpha_selectors: [u8; 16],
    /// Each subset's low endpoint, at the mode's precision.
    pub low: [ColorRgba; 3],
    /// Each subset's high endpoint.
    pub high: [ColorRgba; 3],
    /// Each subset's p-bits: the low endpoint's and the high one's (the first is the one a
    /// mode with a shared p-bit uses).
    pub pbits: [[u32; 2]; 3],
    /// Modes 4 and 5: which channel is swapped with alpha.
    pub rotation: u32,
    /// Mode 4: 1 when the colour takes the wider selectors.
    pub index_selector: u32,
}

/// Writes a block of any mode from its endpoints and selectors: `encode_bc7_block`.
///
/// Out-of-range fields are sanitized cleanly (`mode >= 8` writes an all-zero reserved block,
/// and partitions, rotations, index selectors, endpoints, p-bits, and selectors are masked to
/// the mode's bit widths).
// (One pass, step for step as the original's, its state shared throughout.)
#[allow(clippy::too_many_lines)]
pub fn encode_bc7_block(block: &mut [u8; 16], results: &OptimizationResults) {
    let best_mode = results.mode;
    if best_mode >= 8 {
        *block = [0; BLOCK_SIZE];
        return;
    }

    let index_selector = if best_mode == 4 {
        results.index_selector & 1
    } else {
        0
    };
    let rotation = if best_mode == 4 || best_mode == 5 {
        results.rotation & 3
    } else {
        0
    };

    let total_subsets = u32::from(NUM_SUBSETS[best_mode as usize]);

    let total_partitions = 1u32 << PARTITION_BITS[best_mode as usize];
    let partition_idx = results.partition & (total_partitions - 1);

    let partition_at = partition_idx as usize * 16;
    let partition: &[u8] = if total_subsets == 1 {
        &PARTITION1
    } else if total_subsets == 2 {
        &PARTITION2[partition_at..partition_at + 16]
    } else {
        &PARTITION3[partition_at..partition_at + 16]
    };

    let color_index_bits = get_bc7_color_index_size(best_mode, index_selector);
    let num_color_indices = 1u32 << color_index_bits;
    let color_sel_mask = (num_color_indices - 1) as u8;
    let mut color_selectors = results.selectors.map(|s| s & color_sel_mask);

    let mut alpha_selectors = results.alpha_selectors;
    if get_bc7_mode_has_seperate_alpha_selectors(best_mode) {
        let alpha_index_bits = get_bc7_alpha_index_size(best_mode, index_selector);
        let alpha_sel_mask = ((1u32 << alpha_index_bits) - 1) as u8;
        alpha_selectors = alpha_selectors.map(|s| s & alpha_sel_mask);
    }

    let mut low = results.low;
    let mut high = results.high;

    let mut pbits = results.pbits.map(|pair| [pair[0] & 1, pair[1] & 1]);

    let mut anchor = [-1i32; 3];

    for k in 0..total_subsets as usize {
        let mut anchor_index = 0usize;
        if k != 0 {
            if total_subsets == 3 && k == 1 {
                anchor_index = ANCHOR_INDEX_THIRD_SUBSET_1[partition_idx as usize] as usize;
            } else if total_subsets == 3 && k == 2 {
                anchor_index = ANCHOR_INDEX_THIRD_SUBSET_2[partition_idx as usize] as usize;
            } else {
                anchor_index = ANCHOR_INDEX_SECOND_SUBSET[partition_idx as usize] as usize;
            }
        }

        anchor[k] = anchor_index as i32;

        if (u32::from(color_selectors[anchor_index]) & (num_color_indices >> 1)) != 0 {
            for i in 0..16 {
                if partition[i] as usize == k {
                    color_selectors[i] =
                        ((num_color_indices - 1).wrapping_sub(u32::from(color_selectors[i]))) as u8;
                }
            }

            if get_bc7_mode_has_seperate_alpha_selectors(best_mode) {
                for q in 0..3 {
                    std::mem::swap(&mut low[k][q], &mut high[k][q]);
                }
            } else {
                std::mem::swap(&mut low[k], &mut high[k]);
            }

            if MODE_HAS_SHARED_P_BITS[best_mode as usize] == 0 {
                pbits[k].swap(0, 1);
            }
        }

        if get_bc7_mode_has_seperate_alpha_selectors(best_mode) {
            let alpha_index_bits = get_bc7_alpha_index_size(best_mode, index_selector);
            let num_alpha_indices = 1u32 << alpha_index_bits;

            if (u32::from(alpha_selectors[anchor_index]) & (num_alpha_indices >> 1)) != 0 {
                for i in 0..16 {
                    if partition[i] as usize == k {
                        alpha_selectors[i] = ((num_alpha_indices - 1)
                            .wrapping_sub(u32::from(alpha_selectors[i])))
                            as u8;
                    }
                }

                std::mem::swap(&mut low[k][3], &mut high[k][3]);
            }
        }
    }

    *block = [0; BLOCK_SIZE];

    let mut cur_bit_ofs = 0u32;

    set_block_bits(block, 1 << best_mode, best_mode + 1, &mut cur_bit_ofs);

    if best_mode == 4 || best_mode == 5 {
        set_block_bits(block, rotation, 2, &mut cur_bit_ofs);
    }

    if best_mode == 4 {
        set_block_bits(block, index_selector, 1, &mut cur_bit_ofs);
    }

    if total_partitions > 1 {
        set_block_bits(
            block,
            partition_idx,
            if total_partitions == 64 { 6 } else { 4 },
            &mut cur_bit_ofs,
        );
    }

    let total_comps = if best_mode >= 4 { 4 } else { 3 };
    for comp in 0..total_comps {
        for subset in 0..total_subsets as usize {
            let bits = u32::from(if comp == 3 {
                ALPHA_PRECISION_TABLE[best_mode as usize]
            } else {
                COLOR_PRECISION_TABLE[best_mode as usize]
            });
            let comp_mask = (1u32 << bits) - 1;
            set_block_bits(
                block,
                u32::from(low[subset][comp]) & comp_mask,
                bits,
                &mut cur_bit_ofs,
            );
            set_block_bits(
                block,
                u32::from(high[subset][comp]) & comp_mask,
                bits,
                &mut cur_bit_ofs,
            );
        }
    }

    if MODE_HAS_P_BITS[best_mode as usize] != 0 {
        for subset in 0..total_subsets as usize {
            set_block_bits(block, pbits[subset][0], 1, &mut cur_bit_ofs);
            if MODE_HAS_SHARED_P_BITS[best_mode as usize] == 0 {
                set_block_bits(block, pbits[subset][1], 1, &mut cur_bit_ofs);
            }
        }
    }

    for y in 0..4 {
        for x in 0..4 {
            let idx = x + y * 4;

            let mut n = if index_selector != 0 {
                get_bc7_alpha_index_size(best_mode, index_selector)
            } else {
                get_bc7_color_index_size(best_mode, index_selector)
            };

            if idx == anchor[0] || idx == anchor[1] || idx == anchor[2] {
                n -= 1;
            }

            set_block_bits(
                block,
                u32::from(if index_selector != 0 {
                    alpha_selectors[idx as usize]
                } else {
                    color_selectors[idx as usize]
                }),
                n,
                &mut cur_bit_ofs,
            );
        }
    }

    if get_bc7_mode_has_seperate_alpha_selectors(best_mode) {
        for y in 0..4 {
            for x in 0..4 {
                let idx = x + y * 4;

                let mut n = if index_selector != 0 {
                    get_bc7_color_index_size(best_mode, index_selector)
                } else {
                    get_bc7_alpha_index_size(best_mode, index_selector)
                };

                if idx == anchor[0] || idx == anchor[1] || idx == anchor[2] {
                    n -= 1;
                }

                set_block_bits(
                    block,
                    u32::from(if index_selector != 0 {
                        color_selectors[idx as usize]
                    } else {
                        alpha_selectors[idx as usize]
                    }),
                    n,
                    &mut cur_bit_ofs,
                );
            }
        }
    }

    debug_assert_eq!(cur_bit_ofs, 128);
}

/// An error scaled by a mode's weight, as the C++ rounds it. (A weight below zero has no
/// meaning there; here it gives 0.)
#[inline]
fn weighted_error(err: u64, weight: f32) -> u64 {
    (err as f32 * weight + 0.5) as u64
}

impl Bc7Enc {
    /// Mode 5's error and the part of it that is alpha's.
    fn handle_alpha_block_mode5(
        &self,
        pixels: &[ColorRgba; 16],
        comp_params: &CompressBlockParams,
        params: &mut ColorCellCompressorParams,
        mut lo_a: u32,
        mut hi_a: u32,
        opt_results5: &mut OptimizationResults,
    ) -> (u64, u64) {
        params.selector_weights = &WEIGHTS2;
        params.selector_weightsx = &WEIGHTS2X;
        params.num_selector_weights = 4;

        params.comp_bits = 7;
        params.has_pbits = false;
        params.endpoints_share_pbit = false;
        params.has_alpha = false;

        params.perceptual = comp_params.perceptual;

        let mut results5 = ColorCellCompressorResults::new();

        let mut mode5_err =
            self.color_cell_compression(5, params, pixels, &mut results5, comp_params);
        debug_assert_eq!(mode5_err, results5.best_overall_err);

        opt_results5.selectors = results5.selectors;
        opt_results5.low[0] = results5.low_endpoint;
        opt_results5.high[0] = results5.high_endpoint;

        let mut mode5_alpha_err;
        if lo_a == hi_a {
            mode5_alpha_err = 0;
            opt_results5.low[0][3] = lo_a as u8;
            opt_results5.high[0][3] = hi_a as u8;
            opt_results5.alpha_selectors = [0; 16];
        } else {
            mode5_alpha_err = u64::MAX;

            let total_passes = if comp_params.uber_level >= 1 { 3 } else { 2 };
            for pass in 0..total_passes {
                let mut vals = [0i32; 4];
                vals[0] = lo_a as i32;
                vals[3] = hi_a as i32;

                let (w_s1, w_s2) = (21i32, 43i32);
                vals[1] = (vals[0] * (64 - w_s1) + vals[3] * w_s1 + 32) >> 6;
                vals[2] = (vals[0] * (64 - w_s2) + vals[3] * w_s2 + 32) >> 6;

                let mut trial_alpha_selectors = [0u8; 16];

                let mut trial_alpha_err = 0u64;
                for i in 0..16 {
                    let a = i32::from(pixels[i][3]);

                    let mut s = 0;
                    let mut be = iabs32(a - vals[0]);

                    let mut e = iabs32(a - vals[1]);
                    if e < be {
                        be = e;
                        s = 1;
                    }

                    e = iabs32(a - vals[2]);
                    if e < be {
                        be = e;
                        s = 2;
                    }

                    e = iabs32(a - vals[3]);
                    if e < be {
                        be = e;
                        s = 3;
                    }

                    trial_alpha_selectors[i] = s;

                    let a_err = ((be * be) as u32).wrapping_mul(params.weights[3]);

                    trial_alpha_err += u64::from(a_err);
                }

                if trial_alpha_err < mode5_alpha_err {
                    mode5_alpha_err = trial_alpha_err;
                    opt_results5.low[0][3] = lo_a as u8;
                    opt_results5.high[0][3] = hi_a as u8;
                    opt_results5.alpha_selectors = trial_alpha_selectors;
                }

                if pass != total_passes - 1 {
                    let (xl, xh) = compute_least_squares_endpoints_a(
                        &trial_alpha_selectors,
                        &WEIGHTS2X,
                        pixels,
                    );

                    let mut new_lo_a = clampi(f2i(fmath::floor(xl + 0.5)), 0, 255) as u32;
                    let mut new_hi_a = clampi(f2i(fmath::floor(xh + 0.5)), 0, 255) as u32;
                    if new_lo_a > new_hi_a {
                        std::mem::swap(&mut new_lo_a, &mut new_hi_a);
                    }

                    if new_lo_a == lo_a && new_hi_a == hi_a {
                        break;
                    }

                    lo_a = new_lo_a;
                    hi_a = new_hi_a;
                }
            }

            mode5_err += mode5_alpha_err;
        }

        (mode5_err, mode5_alpha_err)
    }

    // (One pass, step for step as the original's, its state shared throughout.)
    #[allow(clippy::too_many_lines)]
    fn handle_alpha_block(
        &self,
        block: &mut [u8; 16],
        pixels: &[ColorRgba; 16],
        comp_params: &CompressBlockParams,
        params: &mut ColorCellCompressorParams,
    ) -> Result<(), CompressBlockError> {
        let mut mode_mask = comp_params.mode_mask & (1 << 5 | 1 << 6 | 1 << 7);
        if mode_mask == 0 {
            return Err(CompressBlockError::NoModeAllowed);
        }
        if comp_params.force_selectors {
            let max_sel = comp_params.selectors.iter().copied().max().unwrap_or(0);
            if max_sel >= 4 {
                mode_mask &= !(1 << 5 | 1 << 7);
            }
            if mode_mask == 0 {
                return Err(CompressBlockError::SelectorOutOfRange);
            }
        }

        params.selector_weights = &WEIGHTS4;
        params.selector_weightsx = &WEIGHTS4X;
        params.num_selector_weights = 16;
        params.comp_bits = 7;
        params.has_pbits = true;
        params.endpoints_share_pbit = false;
        params.has_alpha = true;

        params.perceptual = comp_params.perceptual;

        let mut opt_results6 = OptimizationResults::default();
        let mut opt_results5 = OptimizationResults::default();
        let mut opt_results7 = OptimizationResults::default();

        let mut results6 = ColorCellCompressorResults::new();

        let mut best_err = u64::MAX;
        let mut best_mode = 0u32;

        if (mode_mask & (1 << 6)) != 0 {
            best_err = weighted_error(
                self.color_cell_compression(6, params, pixels, &mut results6, comp_params),
                comp_params.mode6_error_weight,
            );
            opt_results6.selectors = results6.selectors;
            best_mode = 6;
        }

        if best_err > 0 && (mode_mask & (1 << 5)) != 0 {
            let (mut lo_a, mut hi_a) = (255u32, 0u32);
            for pixel in pixels {
                let a = u32::from(pixel[3]);
                lo_a = lo_a.min(a);
                hi_a = hi_a.max(a);
            }

            let (mode5_err, _mode5_alpha_err) = self.handle_alpha_block_mode5(
                pixels,
                comp_params,
                params,
                lo_a,
                hi_a,
                &mut opt_results5,
            );

            let mode5_err = weighted_error(mode5_err, comp_params.mode5_error_weight);

            if mode5_err < best_err {
                best_err = mode5_err;
                best_mode = 5;
            }
        }

        if best_err > 0 && (mode_mask & (1 << 7)) != 0 {
            let trial_partition = estimate_partition(pixels, comp_params, &params.weights, 7);

            params.selector_weights = &WEIGHTS2;
            params.selector_weightsx = &WEIGHTS2X;
            params.num_selector_weights = 4;
            params.comp_bits = 5;
            params.has_pbits = true;
            params.endpoints_share_pbit = false;
            params.has_alpha = true;

            let subsets = Subsets::new(pixels, trial_partition);

            let mut subset_results7 = [ColorCellCompressorResults::new(); 2];

            let mut trial_err = 0u64;
            for subset in 0..2 {
                let err = self.color_cell_compression(
                    7,
                    params,
                    subsets.pixels(subset),
                    &mut subset_results7[subset],
                    comp_params,
                );
                trial_err += err;
                if weighted_error(trial_err, comp_params.mode7_error_weight) > best_err {
                    break;
                }
            }

            let mode7_trial_err = weighted_error(trial_err, comp_params.mode7_error_weight);

            if mode7_trial_err < best_err {
                best_mode = 7;
                opt_results7.mode = 7;
                opt_results7.partition = trial_partition;
                opt_results7.index_selector = 0;
                opt_results7.rotation = 0;
                for subset in 0..2 {
                    for i in 0..subsets.total_colors[subset] {
                        opt_results7.selectors[subsets.pixel_index[subset][i] as usize] =
                            subset_results7[subset].selectors[i];
                    }
                    opt_results7.low[subset] = subset_results7[subset].low_endpoint;
                    opt_results7.high[subset] = subset_results7[subset].high_endpoint;
                    opt_results7.pbits[subset][0] = subset_results7[subset].pbits[0];
                    opt_results7.pbits[subset][1] = subset_results7[subset].pbits[1];
                }
            }
        }

        if best_mode == 7 {
            encode_bc7_block(block, &opt_results7);
        } else if best_mode == 5 {
            opt_results5.mode = 5;
            opt_results5.partition = 0;
            opt_results5.rotation = 0;
            opt_results5.index_selector = 0;

            encode_bc7_block(block, &opt_results5);
        } else if best_mode == 6 {
            opt_results6.mode = 6;
            opt_results6.partition = 0;
            opt_results6.low[0] = results6.low_endpoint;
            opt_results6.high[0] = results6.high_endpoint;
            opt_results6.pbits[0][0] = results6.pbits[0];
            opt_results6.pbits[0][1] = results6.pbits[1];
            opt_results6.rotation = 0;
            opt_results6.index_selector = 0;

            encode_bc7_block(block, &opt_results6);
        } else {
            return Err(CompressBlockError::NoModeFits);
        }
        Ok(())
    }

    fn handle_opaque_block(
        &self,
        block: &mut [u8; 16],
        pixels: &[ColorRgba; 16],
        comp_params: &CompressBlockParams,
        params: &mut ColorCellCompressorParams,
    ) -> Result<(), CompressBlockError> {
        let mut mode_mask = comp_params.mode_mask & (1 << 1 | 1 << 6);
        if mode_mask == 0 {
            return Err(CompressBlockError::NoModeAllowed);
        }
        if comp_params.force_selectors {
            let max_sel = comp_params.selectors.iter().copied().max().unwrap_or(0);
            if max_sel >= 8 {
                mode_mask &= !(1 << 1);
            }
            if mode_mask == 0 {
                return Err(CompressBlockError::SelectorOutOfRange);
            }
        }

        let mut opt_results = OptimizationResults::default();
        // (The C++ leaves the mode unset until one is chosen.)
        let mut chosen = false;

        let mut best_err = u64::MAX;

        params.perceptual = comp_params.perceptual;
        params.has_alpha = false;

        opt_results.partition = 0;
        opt_results.index_selector = 0;
        opt_results.rotation = 0;

        // Mode 6
        if (mode_mask & (1 << 6)) != 0 {
            params.selector_weights = &WEIGHTS4;
            params.selector_weightsx = &WEIGHTS4X;
            params.num_selector_weights = 16;

            params.comp_bits = 7;
            params.has_pbits = true;
            params.endpoints_share_pbit = false;

            let mut results6 = ColorCellCompressorResults::new();

            best_err = weighted_error(
                self.color_cell_compression(6, params, pixels, &mut results6, comp_params),
                comp_params.mode6_error_weight,
            );

            opt_results.mode = 6;
            opt_results.selectors = results6.selectors;
            opt_results.low[0] = results6.low_endpoint;
            opt_results.high[0] = results6.high_endpoint;
            opt_results.pbits[0][0] = results6.pbits[0];
            opt_results.pbits[0][1] = results6.pbits[1];
            chosen = true;
        }

        // Mode 1
        if best_err > 0 && comp_params.max_partitions > 0 && (mode_mask & (1 << 1)) != 0 {
            let trial_partition = estimate_partition(pixels, comp_params, &params.weights, 1);

            params.selector_weights = &WEIGHTS3;
            params.selector_weightsx = &WEIGHTS3X;
            params.num_selector_weights = 8;

            params.comp_bits = 6;
            params.has_pbits = true;
            params.endpoints_share_pbit = true;

            let subsets = Subsets::new(pixels, trial_partition);

            let mut subset_results1 = [ColorCellCompressorResults::new(); 2];

            let mut trial_err = 0u64;
            for subset in 0..2 {
                let err = self.color_cell_compression(
                    1,
                    params,
                    subsets.pixels(subset),
                    &mut subset_results1[subset],
                    comp_params,
                );
                trial_err += err;
                if weighted_error(trial_err, comp_params.mode1_error_weight) > best_err {
                    break;
                }
            }

            let mode1_trial_err = weighted_error(trial_err, comp_params.mode1_error_weight);

            if mode1_trial_err < best_err {
                opt_results.mode = 1;
                opt_results.partition = trial_partition;
                for subset in 0..2 {
                    for i in 0..subsets.total_colors[subset] {
                        opt_results.selectors[subsets.pixel_index[subset][i] as usize] =
                            subset_results1[subset].selectors[i];
                    }
                    opt_results.low[subset] = subset_results1[subset].low_endpoint;
                    opt_results.high[subset] = subset_results1[subset].high_endpoint;
                    opt_results.pbits[subset][0] = subset_results1[subset].pbits[0];
                }
                chosen = true;
            }
        }

        if !chosen {
            return Err(CompressBlockError::NoModeFits);
        }

        encode_bc7_block(block, &opt_results);
        Ok(())
    }

    /// Packs a single block of 16 RGBA pixels (R first in memory) to the 128-bit BC7 block
    /// `block`: `bc7enc_compress_block`. Blocks with alpha use mode 5, 6 or 7, and opaque
    /// blocks mode 1 or 6, as the mode mask allows.
    ///
    /// Returns true if the block had any pixels with alpha below 255 (or alpha was forced),
    /// otherwise false.
    ///
    /// # Errors
    ///
    /// If the mode mask has none of the modes the block needs (1 or 6 for an opaque block; 5,
    /// 6 or 7 for one with alpha), if none of them can pack it (mode 1 is the only one and
    /// `max_partitions` is 0, or the error weights are out of range), or if a forced selector
    /// is 16 or more. `block` is then left as it was.
    pub fn compress_block(
        &self,
        block: &mut [u8; 16],
        pixels: &[ColorRgba; 16],
        comp_params: &CompressBlockParams,
    ) -> Result<bool, CompressBlockError> {
        if comp_params.force_selectors && comp_params.selectors.iter().any(|&s| s >= 16) {
            return Err(CompressBlockError::SelectorOutOfRange);
        }
        debug_assert!(self.tables.mode_1_optimal_endpoints[255][0].hi != 0);

        let mut params = ColorCellCompressorParams {
            num_selector_weights: 0,
            selector_weights: &[],
            selector_weightsx: &[],
            comp_bits: 0,
            weights: [0; 4],
            has_alpha: false,
            has_pbits: false,
            endpoints_share_pbit: false,
            perceptual: false,
        };

        if comp_params.perceptual {
            // https://en.wikipedia.org/wiki/YCbCr#ITU-R_BT.709_conversion
            let pr_weight = (0.5f32 / (1.0f32 - 0.2126f32)) * (0.5f32 / (1.0f32 - 0.2126f32));
            let pb_weight = (0.5f32 / (1.0f32 - 0.0722f32)) * (0.5f32 / (1.0f32 - 0.0722f32));
            params.weights[0] = f2i(comp_params.weights[0] as f32 * 4.0) as u32;
            params.weights[1] = f2i(comp_params.weights[1] as f32 * 4.0 * pr_weight) as u32;
            params.weights[2] = f2i(comp_params.weights[2] as f32 * 4.0 * pb_weight) as u32;
            params.weights[3] = comp_params.weights[3].wrapping_mul(4);
        } else {
            params.weights = comp_params.weights;
        }

        if comp_params.force_alpha || pixels.iter().any(|pixel| pixel[3] < 255) {
            self.handle_alpha_block(block, pixels, comp_params, &mut params)?;
            return Ok(true);
        }
        self.handle_opaque_block(block, pixels, comp_params, &mut params)?;
        Ok(false)
    }
}
