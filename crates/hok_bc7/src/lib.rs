//! BC7 modes 6, 5, 4 and 7 for the PC edition's atlas ports, a bit-exact port of the hand-written
//! modes in `tools/bc7_mode6.py` (`_mode6`, `_separate`, `_mode7_python`) and of the search
//! `encode_block` runs over them once etcpak's block is not close enough.
//!
//! The reference is the specification: every float operation runs in the reference's order, so
//! the bytes match. Three Python 3.12 behaviors are reproduced on purpose:
//!
//! - `sum()` over floats is Neumaier-compensated (CPython 3.12, gh-100425): [`PySum`].
//! - `x ** 2` calls the C runtime's `pow(|x|, 2.0)`, which differs from `x * x` on about one value
//!   in 2000 (measured 2026-11-26): [`py_square`] calls the same `pow` with the exponent hidden from
//!   the optimizer, so LLVM cannot turn it into a multiply.
//! - `round()` rounds half to even: [`f64::round_ties_even`].
//!
//! Python interface, 64 row-order RGBA bytes in each time:
//!
//! - `encode_mode7(rgba) -> bytes`: one mode 7 block.
//! - `encode_mode(rgba, mode, index_mode=0) -> (bytes, bytes)`: one mode 6, 5, 4 or 7 block and its
//!   decoded RGBA, as the reference computes it.
//! - `encode_search(rgba, best_error) -> (bytes | None, int)`: `encode_block`'s loop over modes 6, 5,
//!   4 (both index modes) and 7: the block closest to the pixels if it beats `best_error` (the
//!   native block's mismatch), else None, and how many modes it tried (5: mode 7 ran).

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

const WEIGHTS2: [i32; 4] = [0, 21, 43, 64];
const WEIGHTS3: [i32; 8] = [0, 9, 18, 27, 37, 46, 55, 64];
const WEIGHTS4: [i32; 16] = [0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64];
const REFINE_PASSES: usize = 3;
const MODE7_TRIES: usize = 4;
const TRANSPARENT_WEIGHT: f64 = 1e-3;
const GOOD_ENOUGH: f64 = 1.0;

const PARTITIONS2: [u16; 64] = [
    0xCCCC, 0x8888, 0xEEEE, 0xECC8, 0xC880, 0xFEEC, 0xFEC8, 0xEC80, 0xC800, 0xFFEC, 0xFE80, 0xE800,
    0xFFE8, 0xFF00, 0xFFF0, 0xF000, 0xF710, 0x008E, 0x7100, 0x08CE, 0x008C, 0x7310, 0x3100, 0x8CCE,
    0x088C, 0x3110, 0x6666, 0x366C, 0x17E8, 0x0FF0, 0x718E, 0x399C, 0xAAAA, 0xF0F0, 0x5A5A, 0x33CC,
    0x3C3C, 0x55AA, 0x9696, 0xA55A, 0x73CE, 0x13C8, 0x324C, 0x3BDC, 0x6996, 0xC33C, 0x9966, 0x0660,
    0x0272, 0x04E4, 0x4E40, 0x2720, 0xC936, 0x936C, 0x39C6, 0x639C, 0x9336, 0x9CC6, 0x817E, 0xE718,
    0xCCF0, 0x0FCC, 0x7744, 0xEE22,
];
const ANCHORS2: [usize; 64] = [
    15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 2, 8, 2, 2, 8, 8, 15, 2, 8,
    2, 2, 8, 8, 2, 2, 15, 15, 6, 8, 2, 8, 15, 15, 2, 8, 2, 2, 2, 15, 15, 6, 6, 2, 6, 8, 15, 15, 2,
    2, 15, 15, 15, 15, 15, 2, 2, 15,
];

type Pixel = [i32; 4];
type Point = [f64; 4];
type Decoded = [[i32; 4]; 16];

extern "C" {
    fn pow(x: f64, y: f64) -> f64;
}

/// Python 3.12's `x ** 2` for a float `x` (`float_pow`): zero and one short-circuit, a negative
/// base is raised as its absolute value, everything else goes to the C runtime's `pow`.
#[inline]
fn py_square(x: f64) -> f64 {
    if x == 0.0 {
        return 0.0;
    }
    let base = x.abs();
    if base == 1.0 {
        return 1.0;
    }
    // SAFETY: `pow` is the C runtime's pure math function.
    unsafe { pow(base, std::hint::black_box(2.0)) }
}

/// Python 3.12's `sum()` over floats, started from the integer 0: Neumaier summation.
struct PySum {
    total: f64,
    compensation: f64,
}

impl PySum {
    #[inline]
    fn new() -> Self {
        PySum { total: 0.0, compensation: 0.0 }
    }

    #[inline]
    fn add(&mut self, x: f64) {
        let t = self.total + x;
        if self.total.abs() >= x.abs() {
            self.compensation += (self.total - t) + x;
        } else {
            self.compensation += (x - t) + self.total;
        }
        self.total = t;
    }

    #[inline]
    fn value(&self) -> f64 {
        if self.compensation != 0.0 && self.compensation.is_finite() {
            self.total + self.compensation
        } else {
            self.total
        }
    }
}

fn py_sum(values: impl Iterator<Item = f64>) -> f64 {
    let mut sum = PySum::new();
    for value in values {
        sum.add(value);
    }
    sum.value()
}

/// Python's `max(0.0, min(255.0, x))`, ties kept as Python keeps them.
#[inline]
fn clamp(x: f64) -> f64 {
    let low = if x < 255.0 { x } else { 255.0 };
    if low > 0.0 {
        low
    } else {
        0.0
    }
}

/// Python's `max(0, min(top, round(x)))` for a float `x`.
#[inline]
fn round_clamp(x: f64, top: i64) -> i64 {
    let rounded = x.round_ties_even() as i64;
    rounded.min(top).max(0)
}

#[inline]
fn lerp(low: i32, high: i32, weight: i32) -> i32 {
    ((64 - weight) * low + weight * high + 32) >> 6
}

#[inline]
fn expand6(value: i32) -> i32 {
    (value << 2) | (value >> 4)
}

/// An endpoint quantizer from the reference: `QUANTIZE_<bits>`, `_quantize_pbit` (mode 6) or
/// `_quantize_pbit5` (mode 7).
#[derive(Clone, Copy)]
enum Quantizer {
    Plain(u32),
    PBit7,
    PBit5,
}

/// A quantized endpoint: its codes, its p-bit (0 for plain endpoints) and its decoded 8-bit values.
#[derive(Clone, Copy, Default)]
struct Endpoint {
    codes: [i32; 4],
    pbit: i32,
    actual: [i32; 4],
}

/// `_quantizer(bits)`'s expansion: bit replication, as the BC7 decoder does it.
#[inline]
fn expand_plain(code: i64, bits: u32) -> i64 {
    let code = code << (8 - bits);
    code | (code >> bits)
}

/// `_nearest`: the <bits>-bit code whose expansion is nearest <value>, and that expansion.
fn nearest(value: f64, bits: u32) -> (i32, i32) {
    let top = (1i64 << bits) - 1;
    let guess = round_clamp(value * top as f64 / 255.0, top);
    let mut best: Option<(i64, f64)> = None;
    for code in [guess - 1, guess, guess + 1] {
        if code < 0 || code > top {
            continue;
        }
        let key = (expand_plain(code, bits) as f64 - value).abs();
        if best.map_or(true, |b| key < b.1) {
            best = Some((code, key));
        }
    }
    let code = best.unwrap().0;
    (code as i32, expand_plain(code, bits) as i32)
}

fn quantize(quantizer: Quantizer, endpoint: &Point, dims: usize) -> Endpoint {
    match quantizer {
        Quantizer::Plain(bits) => {
            let mut out = Endpoint::default();
            for c in 0..dims {
                let (code, value) = nearest(endpoint[c], bits);
                out.codes[c] = code;
                out.actual[c] = value;
            }
            out
        }
        Quantizer::PBit7 | Quantizer::PBit5 => {
            let mut best: Option<(f64, Endpoint)> = None;
            for pbit in 0..2 {
                let mut choice = Endpoint { pbit, ..Endpoint::default() };
                for c in 0..dims {
                    let value = endpoint[c];
                    let code = match quantizer {
                        Quantizer::PBit7 => round_clamp((value - pbit as f64) / 2.0, 127) as i32,
                        _ => {
                            let mut best_code = 0;
                            let mut best_key = f64::INFINITY;
                            for q in 0..32 {
                                let key = (expand6((q << 1) | pbit) as f64 - value).abs();
                                if q == 0 || key < best_key {
                                    best_code = q;
                                    best_key = key;
                                }
                            }
                            best_code
                        }
                    };
                    choice.codes[c] = code;
                    choice.actual[c] = match quantizer {
                        Quantizer::PBit7 => code * 2 + pbit,
                        _ => expand6((code << 1) | pbit),
                    };
                }
                let error = py_sum((0..dims).map(|c| py_square(endpoint[c] - choice.actual[c] as f64)));
                if best.as_ref().map_or(true, |b| error < b.0) {
                    best = Some((error, choice));
                }
            }
            best.unwrap().1
        }
    }
}

/// `_initial`: endpoints at the ends of the weighted principal axis.
fn initial(points: &[Point], importance: &[Point], dims: usize) -> (Point, Point) {
    let n = points.len();
    let mut weight = [0.0f64; 16];
    for k in 0..n {
        let row = &importance[k];
        let mut m = row[0];
        for &v in &row[1..dims] {
            if v > m {
                m = v;
            }
        }
        weight[k] = m;
    }
    let mut total = py_sum(weight[..n].iter().copied());
    if total == 0.0 {
        total = 1.0;
    }
    let mut mean = [0.0f64; 4];
    for c in 0..dims {
        mean[c] = py_sum((0..n).map(|k| weight[k] * points[k][c])) / total;
    }
    let mut centred = [[0.0f64; 4]; 16];
    for k in 0..n {
        for c in 0..dims {
            centred[k][c] = points[k][c] - mean[c];
        }
    }
    let mut cov = [[0.0f64; 4]; 4];
    for i in 0..dims {
        for j in 0..dims {
            cov[i][j] = py_sum((0..n).map(|k| weight[k] * centred[k][i] * centred[k][j]));
        }
    }
    let mut axis = [0.0f64; 4];
    for i in 0..dims {
        axis[i] = cov[i][i];
    }
    if axis[..dims].iter().all(|&v| v == 0.0) {
        return (mean, mean);
    }
    for _ in 0..8 {
        let mut next = [0.0f64; 4];
        for i in 0..dims {
            next[i] = py_sum((0..dims).map(|j| cov[i][j] * axis[j]));
        }
        let mut norm = next[0].abs();
        for v in &next[1..dims] {
            if v.abs() > norm {
                norm = v.abs();
            }
        }
        if norm == 0.0 {
            return (mean, mean);
        }
        for i in 0..dims {
            axis[i] = next[i] / norm;
        }
    }
    let length = py_sum(axis[..dims].iter().map(|v| v * v));
    let mut low = 0.0f64;
    let mut high = 0.0f64;
    let mut any = false;
    for k in 0..n {
        if weight[k] > TRANSPARENT_WEIGHT {
            let span = py_sum((0..dims).map(|c| centred[k][c] * axis[c])) / length;
            if !any {
                low = span;
                high = span;
                any = true;
            } else {
                if span < low {
                    low = span;
                }
                if span > high {
                    high = span;
                }
            }
        }
    }
    let mut a = [0.0f64; 4];
    let mut b = [0.0f64; 4];
    for c in 0..dims {
        a[c] = clamp(mean[c] + axis[c] * low);
        b[c] = clamp(mean[c] + axis[c] * high);
    }
    (a, b)
}

/// `_assign`: each point's nearest palette index between decoded endpoints, and the weighted
/// squared error.
fn assign(points: &[Point], importance: &[Point], weights: &[i32], dims: usize, low: &[i32; 4],
          high: &[i32; 4], indices: &mut [usize; 16]) -> f64 {
    let mut palette = [[0i32; 4]; 16];
    for (w, weight) in weights.iter().enumerate() {
        for c in 0..dims {
            palette[w][c] = lerp(low[c], high[c], *weight);
        }
    }
    let mut total = 0.0f64;
    for (k, (point, imp)) in points.iter().zip(importance).enumerate() {
        let mut best_index = 0usize;
        let mut best_error = 0.0f64;
        for (index, colour) in palette[..weights.len()].iter().enumerate() {
            let mut error = 0.0f64;
            for c in 0..dims {
                let delta = colour[c] as f64 - point[c];
                error += imp[c] * delta * delta;
            }
            if index == 0 || error < best_error {
                best_index = index;
                best_error = error;
            }
        }
        indices[k] = best_index;
        total += best_error;
    }
    total
}

/// `_refine`: least-squares endpoints for fixed indices, channel by channel.
fn refine(points: &[Point], importance: &[Point], weights: &[i32], dims: usize,
          indices: &[usize; 16]) -> (Point, Point) {
    let n = points.len();
    let mut low = [0.0f64; 4];
    let mut high = [0.0f64; 4];
    let mut fractions = [0.0f64; 16];
    for k in 0..n {
        fractions[k] = weights[indices[k]] as f64 / 64.0;
    }
    for c in 0..dims {
        let (mut aa, mut ab, mut bb, mut ra, mut rb, mut mass, mut moment) =
            (0.0f64, 0.0f64, 0.0f64, 0.0f64, 0.0f64, 0.0f64, 0.0f64);
        for k in 0..n {
            let f = fractions[k];
            let p = points[k][c];
            let s = importance[k][c];
            aa += s * py_square(1.0 - f);
            ab += s * f * (1.0 - f);
            bb += s * f * f;
            ra += s * (1.0 - f) * p;
            rb += s * f * p;
            mass += s;
            moment += s * p;
        }
        let determinant = aa * bb - ab * ab;
        if determinant < 1e-9 {
            let v = if mass != 0.0 { moment / mass } else { 0.0 };
            low[c] = v;
            high[c] = v;
        } else {
            low[c] = (ra * bb - rb * ab) / determinant;
            high[c] = (rb * aa - ra * ab) / determinant;
        }
        low[c] = clamp(low[c]);
        high[c] = clamp(high[c]);
    }
    (low, high)
}

struct Line {
    ends: [Endpoint; 2],
    indices: [usize; 16],
}

/// `_fit`: the best quantized line through <points>; the anchor's index keeps its top bit clear.
fn fit(points: &[Point], importance: &[Point], weights: &[i32], quantizer: Quantizer, dims: usize,
       anchor: usize) -> Line {
    let n = points.len();
    let (mut low, mut high) = initial(points, importance, dims);
    let mut best: Option<(f64, Line)> = None;
    let mut indices = [0usize; 16];
    for _ in 0..=REFINE_PASSES {
        let end0 = quantize(quantizer, &low, dims);
        let end1 = quantize(quantizer, &high, dims);
        let error = assign(points, importance, weights, dims, &end0.actual, &end1.actual, &mut indices);
        if best.as_ref().map_or(true, |b| error < b.0) {
            best = Some((error, Line { ends: [end0, end1], indices }));
        }
        let refined = refine(points, importance, weights, dims, &indices);
        low = refined.0;
        high = refined.1;
    }
    let (_, mut line) = best.unwrap();
    let top = weights.len() - 1;
    if line.indices[anchor] > top / 2 {
        line.ends.swap(0, 1);
        for index in line.indices[..n].iter_mut() {
            *index = top - *index;
        }
    }
    line
}

/// `mismatch` times 16: the summed premultiplied difference. Divided by 16 it is the reference's
/// float exactly.
fn mismatch_total(pixels: &[Pixel; 16], decoded: &Decoded) -> i32 {
    let mut total = 0;
    for (p, d) in pixels.iter().zip(decoded) {
        let (r, g, b, a) = (p[0], p[1], p[2], p[3]);
        let (dr, dg, db, da) = (d[0], d[1], d[2], d[3]);
        total += (a - da).abs()
            .max((r * a - dr * da).abs() / 255)
            .max((g * a - dg * da).abs() / 255)
            .max((b * a - db * da).abs() / 255);
    }
    total
}

struct Bits {
    value: u128,
    position: u32,
}

impl Bits {
    fn new() -> Self {
        Bits { value: 0, position: 0 }
    }

    fn write(&mut self, value: u32, width: u32) {
        self.value |= (value as u128) << self.position;
        self.position += width;
    }

    /// `_Bits.indices` with one anchor at pixel 0.
    fn indices(&mut self, indices: &[usize; 16], width: u32) {
        for (i, &index) in indices.iter().enumerate() {
            self.write(index as u32, if i == 0 { width - 1 } else { width });
        }
    }

    fn bytes(&self) -> [u8; 16] {
        debug_assert_eq!(self.position, 128);
        self.value.to_le_bytes()
    }
}

/// The pixels, and `_importance` joined per pixel as modes 6 and 7 use it: color weight three
/// times, then alpha's 1.0.
fn prepare(rgba: &[u8; 64]) -> ([Pixel; 16], [Point; 16]) {
    let mut pixels = [[0i32; 4]; 16];
    let mut importance = [[0.0f64; 4]; 16];
    for i in 0..16 {
        for c in 0..4 {
            pixels[i][c] = rgba[i * 4 + c] as i32;
        }
        let squared = py_square(pixels[i][3] as f64 / 255.0);
        let w = if squared > TRANSPARENT_WEIGHT { squared } else { TRANSPARENT_WEIGHT };
        importance[i] = [w, w, w, 1.0];
    }
    (pixels, importance)
}

/// `_mode6`: one RGBA line, 7-bit endpoints with a p-bit each, 4-bit indices.
fn mode6(pixels: &[Pixel; 16], importance: &[Point; 16]) -> ([u8; 16], Decoded) {
    let points: [Point; 16] = std::array::from_fn(|i| pixels[i].map(|v| v as f64));
    let line = fit(&points, importance, &WEIGHTS4, Quantizer::PBit7, 4, 0);
    let mut bits = Bits::new();
    bits.write(1 << 6, 7);
    for channel in 0..4 {
        bits.write(line.ends[0].codes[channel] as u32, 7);
        bits.write(line.ends[1].codes[channel] as u32, 7);
    }
    bits.write(line.ends[0].pbit as u32, 1);
    bits.write(line.ends[1].pbit as u32, 1);
    bits.indices(&line.indices, 4);
    let decoded = std::array::from_fn(|i| {
        std::array::from_fn(|c| lerp(line.ends[0].actual[c], line.ends[1].actual[c], WEIGHTS4[line.indices[i]]))
    });
    (bits.bytes(), decoded)
}

/// `_separate`: mode 5 or mode 4, an RGB line and an alpha line, rotation 0. Mode 4's
/// <index_mode> 0 gives the color 2-bit indices and the alpha 3-bit ones; 1 the reverse.
fn separate(pixels: &[Pixel; 16], importance: &[Point; 16], mode: u32, index_mode: u32) -> ([u8; 16], Decoded) {
    let rgb: [Point; 16] = std::array::from_fn(|i| [pixels[i][0] as f64, pixels[i][1] as f64, pixels[i][2] as f64, 0.0]);
    let alphas: [Point; 16] = std::array::from_fn(|i| [pixels[i][3] as f64, 0.0, 0.0, 0.0]);
    let colour_imp: [Point; 16] = std::array::from_fn(|i| [importance[i][0], importance[i][1], importance[i][2], 0.0]);
    let alpha_imp: [Point; 16] = [[1.0, 0.0, 0.0, 0.0]; 16];
    let (colour_weights, alpha_weights, colour_q, alpha_q, colour_bits, alpha_bits): (&[i32], &[i32], _, _, u32, u32) =
        if mode == 5 {
            (&WEIGHTS2, &WEIGHTS2, Quantizer::Plain(7), Quantizer::Plain(8), 7, 8)
        } else if index_mode == 0 {
            (&WEIGHTS2, &WEIGHTS3, Quantizer::Plain(5), Quantizer::Plain(6), 5, 6)
        } else {
            (&WEIGHTS3, &WEIGHTS2, Quantizer::Plain(5), Quantizer::Plain(6), 5, 6)
        };
    let colour = fit(&rgb, &colour_imp, colour_weights, colour_q, 3, 0);
    let alpha = fit(&alphas, &alpha_imp, alpha_weights, alpha_q, 1, 0);
    let mut bits = Bits::new();
    bits.write(1 << mode, mode + 1);
    bits.write(0, 2); // rotation: none
    if mode == 4 {
        bits.write(index_mode, 1);
    }
    for channel in 0..3 {
        bits.write(colour.ends[0].codes[channel] as u32, colour_bits);
        bits.write(colour.ends[1].codes[channel] as u32, colour_bits);
    }
    bits.write(alpha.ends[0].codes[0] as u32, alpha_bits);
    bits.write(alpha.ends[1].codes[0] as u32, alpha_bits);
    // The 2-bit index set comes first in the stream, whichever channel it belongs to.
    if colour_weights.len() == 4 {
        bits.indices(&colour.indices, 2);
        bits.indices(&alpha.indices, if alpha_weights.len() == 4 { 2 } else { 3 });
    } else {
        bits.indices(&alpha.indices, 2);
        bits.indices(&colour.indices, 3);
    }
    let decoded = std::array::from_fn(|i| {
        let ci = colour_weights[colour.indices[i]];
        let ai = alpha_weights[alpha.indices[i]];
        [
            lerp(colour.ends[0].actual[0], colour.ends[1].actual[0], ci),
            lerp(colour.ends[0].actual[1], colour.ends[1].actual[1], ci),
            lerp(colour.ends[0].actual[2], colour.ends[1].actual[2], ci),
            lerp(alpha.ends[0].actual[0], alpha.ends[1].actual[0], ai),
        ]
    });
    (bits.bytes(), decoded)
}

/// `_spread`: weighted squared spread of <members> around their mean.
fn spread(pixels: &[Pixel; 16], members: &[usize], importance: &[Point; 16]) -> f64 {
    let mut total = 0.0f64;
    for c in 0..4 {
        let mass = py_sum(members.iter().map(|&i| importance[i][c]));
        if mass == 0.0 {
            continue;
        }
        let mean = py_sum(members.iter().map(|&i| importance[i][c] * pixels[i][c] as f64)) / mass;
        total += py_sum(members.iter().map(|&i| importance[i][c] * py_square(pixels[i][c] as f64 - mean)));
    }
    total
}

fn subsets(partition: usize) -> ([usize; 16], usize, [usize; 16], usize) {
    let mask = PARTITIONS2[partition];
    let (mut zero, mut one) = ([0usize; 16], [0usize; 16]);
    let (mut nz, mut no) = (0, 0);
    for i in 0..16 {
        if mask >> i & 1 == 0 {
            zero[nz] = i;
            nz += 1;
        } else {
            one[no] = i;
            no += 1;
        }
    }
    (zero, nz, one, no)
}

/// `_mode7_python`: two RGBA lines split by the best of the 64 two-subset partitions.
fn mode7(pixels: &[Pixel; 16], importance: &[Point; 16]) -> ([u8; 16], Decoded) {
    let mut keys = [0.0f64; 64];
    for (p, key) in keys.iter_mut().enumerate() {
        let (zero, nz, one, no) = subsets(p);
        *key = spread(pixels, &zero[..nz], importance) + spread(pixels, &one[..no], importance);
    }
    let mut ranked: [usize; 64] = std::array::from_fn(|p| p);
    ranked.sort_by(|a, b| keys[*a].partial_cmp(&keys[*b]).unwrap_or(std::cmp::Ordering::Equal));

    let mut best: Option<(i32, usize, [Endpoint; 4], [usize; 16], Decoded)> = None;
    for &partition in &ranked[..MODE7_TRIES] {
        let (zero, nz, one, no) = subsets(partition);
        let mut decoded = [[0i32; 4]; 16];
        let mut indices = [0usize; 16];
        let mut ends = [Endpoint::default(); 4];
        for (subset, (members, anchor)) in
            [(&zero[..nz], 0usize), (&one[..no], ANCHORS2[partition])].into_iter().enumerate()
        {
            let mut points = [[0.0f64; 4]; 16];
            let mut imp = [[0.0f64; 4]; 16];
            for (k, &i) in members.iter().enumerate() {
                points[k] = pixels[i].map(|v| v as f64);
                imp[k] = importance[i];
            }
            let position = members.iter().position(|&i| i == anchor).expect("anchor in its subset");
            let m = members.len();
            let line = fit(&points[..m], &imp[..m], &WEIGHTS2, Quantizer::PBit5, 4, position);
            ends[subset * 2] = line.ends[0];
            ends[subset * 2 + 1] = line.ends[1];
            for (k, &i) in members.iter().enumerate() {
                let index = line.indices[k];
                indices[i] = index;
                for c in 0..4 {
                    decoded[i][c] = lerp(line.ends[0].actual[c], line.ends[1].actual[c], WEIGHTS2[index]);
                }
            }
        }
        let error = mismatch_total(pixels, &decoded);
        if best.as_ref().map_or(true, |b| error < b.0) {
            best = Some((error, partition, ends, indices, decoded));
        }
    }
    let (_, partition, ends, indices, decoded) = best.unwrap();
    let mut bits = Bits::new();
    bits.write(1 << 7, 8);
    bits.write(partition as u32, 6);
    for channel in 0..4 {
        for end in &ends {
            bits.write(end.codes[channel] as u32, 5);
        }
    }
    for end in &ends {
        bits.write(end.pbit as u32, 1);
    }
    let anchor = ANCHORS2[partition];
    for (i, &index) in indices.iter().enumerate() {
        bits.write(index as u32, if i == 0 || i == anchor { 1 } else { 2 });
    }
    (bits.bytes(), decoded)
}

/// One block in <mode> (4 takes <index_mode>), and its decoded pixels.
fn encode(rgba: &[u8; 64], mode: u32, index_mode: u32) -> ([u8; 16], Decoded) {
    let (pixels, importance) = prepare(rgba);
    match mode {
        6 => mode6(&pixels, &importance),
        5 => separate(&pixels, &importance, 5, 0),
        4 => separate(&pixels, &importance, 4, index_mode),
        _ => mode7(&pixels, &importance),
    }
}

/// `encode_block`'s loop past etcpak, cheapest mode first, stopping at the first that comes within
/// `GOOD_ENOUGH`: the best block if it beats <best_error>, and how many modes ran.
pub fn search(rgba: &[u8; 64], best_error: f64) -> (Option<[u8; 16]>, usize) {
    let (pixels, importance) = prepare(rgba);
    let mut best_error = best_error;
    let mut best: Option<[u8; 16]> = None;
    let mut tried = 0;
    for step in 0..5 {
        let (block, decoded) = match step {
            0 => mode6(&pixels, &importance),
            1 => separate(&pixels, &importance, 5, 0),
            2 => separate(&pixels, &importance, 4, 0),
            3 => separate(&pixels, &importance, 4, 1),
            _ => mode7(&pixels, &importance),
        };
        tried += 1;
        let error = mismatch_total(&pixels, &decoded) as f64 / 16.0;
        if error < best_error {
            best_error = error;
            best = Some(block);
        }
        if best_error <= GOOD_ENOUGH {
            break;
        }
    }
    (best, tried)
}

fn block_of(rgba: &[u8]) -> PyResult<&[u8; 64]> {
    rgba.try_into()
        .map_err(|_| PyValueError::new_err(format!("a BC7 block needs 64 RGBA bytes, got {}", rgba.len())))
}

fn flat(decoded: &Decoded) -> [u8; 64] {
    std::array::from_fn(|i| decoded[i / 4][i % 4] as u8)
}

/// `encode_mode7(rgba: bytes) -> bytes`: exactly 64 row-order RGBA bytes in, one 16-byte BC7 block out.
#[pyfunction]
fn encode_mode7<'py>(py: Python<'py>, rgba: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    let block = block_of(rgba)?;
    Ok(PyBytes::new(py, &encode(block, 7, 0).0))
}

/// `encode_mode(rgba, mode, index_mode=0) -> (block, decoded RGBA)` for mode 6, 5, 4 or 7.
#[pyfunction]
#[pyo3(signature = (rgba, mode, index_mode=0))]
fn encode_mode<'py>(py: Python<'py>, rgba: &[u8], mode: u32, index_mode: u32)
                    -> PyResult<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)> {
    let block = block_of(rgba)?;
    if !matches!(mode, 4..=7) || index_mode > 1 || (index_mode == 1 && mode != 4) {
        return Err(PyValueError::new_err(format!("no BC7 mode {mode} with index mode {index_mode}")));
    }
    let (bytes, decoded) = encode(block, mode, index_mode);
    Ok((PyBytes::new(py, &bytes), PyBytes::new(py, &flat(&decoded))))
}

/// `encode_search(rgba, best_error) -> (block or None, modes tried)`.
#[pyfunction]
fn encode_search<'py>(py: Python<'py>, rgba: &[u8], best_error: f64)
                      -> PyResult<(Option<Bound<'py, PyBytes>>, usize)> {
    let block = block_of(rgba)?;
    let (found, tried) = search(block, best_error);
    Ok((found.map(|b| PyBytes::new(py, &b)), tried))
}

#[pymodule]
fn hok_bc7(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encode_mode7, m)?)?;
    m.add_function(wrap_pyfunction!(encode_mode, m)?)?;
    m.add_function(wrap_pyfunction!(encode_search, m)?)?;
    Ok(())
}
