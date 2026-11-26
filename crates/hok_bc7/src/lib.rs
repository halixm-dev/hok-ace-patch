//! BC7 mode 7 for the PC edition's atlas ports, a bit-exact port of `_mode7_python` in
//! `tools/bc7_mode6.py`.
//!
//! The reference is the specification: every float operation runs in the reference's order, so
//! the bytes match. Two Python 3.12 behaviors are reproduced on purpose:
//!
//! - `sum()` over floats is Neumaier-compensated (CPython 3.12, gh-100425): [`PySum`].
//! - `x ** 2` calls the C runtime's `pow(|x|, 2.0)`, which differs from `x * x` on about one value
//!   in 2000 (measured 2026-11-26): [`py_square`] calls the same `pow` with the exponent hidden from
//!   the optimizer, so LLVM cannot turn it into a multiply.
//!
//! Python interface: `encode_mode7(rgba: bytes) -> bytes`, 64 row-order RGBA bytes in, one 16-byte
//! BC7 block out.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

const WEIGHTS2: [i32; 4] = [0, 21, 43, 64];
const REFINE_PASSES: usize = 3;
const MODE7_TRIES: usize = 4;
const TRANSPARENT_WEIGHT: f64 = 1e-3;

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

#[inline]
fn lerp(low: i32, high: i32, weight: i32) -> i32 {
    ((64 - weight) * low + weight * high + 32) >> 6
}

#[inline]
fn expand6(value: i32) -> i32 {
    (value << 2) | (value >> 4)
}

/// `_quantize_pbit5`: 5-bit codes with one p-bit, and the 8-bit values they decode to.
fn quantize_pbit5(endpoint: &Point) -> ([i32; 4], i32, [i32; 4]) {
    let mut best: Option<(f64, [i32; 4], i32, [i32; 4])> = None;
    for pbit in 0..2 {
        let mut codes = [0i32; 4];
        let mut actual = [0i32; 4];
        for c in 0..4 {
            let value = endpoint[c];
            let mut best_code = 0;
            let mut best_key = f64::INFINITY;
            for q in 0..32 {
                let key = (expand6((q << 1) | pbit) as f64 - value).abs();
                if q == 0 || key < best_key {
                    best_code = q;
                    best_key = key;
                }
            }
            codes[c] = best_code;
            actual[c] = expand6((best_code << 1) | pbit);
        }
        let error = py_sum((0..4).map(|c| py_square(endpoint[c] - actual[c] as f64)));
        if best.as_ref().map_or(true, |b| error < b.0) {
            best = Some((error, codes, pbit, actual));
        }
    }
    let (_, codes, pbit, actual) = best.unwrap();
    (codes, pbit, actual)
}

/// `_initial`: endpoints at the ends of the weighted principal axis.
fn initial(points: &[Point], importance: &[Point]) -> (Point, Point) {
    let n = points.len();
    let mut weight = [0.0f64; 16];
    for k in 0..n {
        let row = &importance[k];
        let mut m = row[0];
        for &v in &row[1..] {
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
    for c in 0..4 {
        mean[c] = py_sum((0..n).map(|k| weight[k] * points[k][c])) / total;
    }
    let mut centred = [[0.0f64; 4]; 16];
    for k in 0..n {
        for c in 0..4 {
            centred[k][c] = points[k][c] - mean[c];
        }
    }
    let mut cov = [[0.0f64; 4]; 4];
    for i in 0..4 {
        for j in 0..4 {
            cov[i][j] = py_sum((0..n).map(|k| weight[k] * centred[k][i] * centred[k][j]));
        }
    }
    let mut axis = [cov[0][0], cov[1][1], cov[2][2], cov[3][3]];
    if axis.iter().all(|&v| v == 0.0) {
        return (mean, mean);
    }
    for _ in 0..8 {
        let mut next = [0.0f64; 4];
        for i in 0..4 {
            next[i] = py_sum((0..4).map(|j| cov[i][j] * axis[j]));
        }
        let mut norm = next[0].abs();
        for v in &next[1..] {
            if v.abs() > norm {
                norm = v.abs();
            }
        }
        if norm == 0.0 {
            return (mean, mean);
        }
        for i in 0..4 {
            axis[i] = next[i] / norm;
        }
    }
    let length = py_sum(axis.iter().map(|v| v * v));
    let mut low = 0.0f64;
    let mut high = 0.0f64;
    let mut any = false;
    for k in 0..n {
        if weight[k] > TRANSPARENT_WEIGHT {
            let span = py_sum((0..4).map(|c| centred[k][c] * axis[c])) / length;
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
    for c in 0..4 {
        a[c] = clamp(mean[c] + axis[c] * low);
        b[c] = clamp(mean[c] + axis[c] * high);
    }
    (a, b)
}

/// `_assign`: each point's nearest palette index, and the weighted squared error.
fn assign(points: &[Point], importance: &[Point], low: &[i32; 4], high: &[i32; 4],
          indices: &mut [usize; 16]) -> f64 {
    let mut palette = [[0i32; 4]; 4];
    for (w, weight) in WEIGHTS2.iter().enumerate() {
        for c in 0..4 {
            palette[w][c] = lerp(low[c], high[c], *weight);
        }
    }
    let mut total = 0.0f64;
    for (k, (point, imp)) in points.iter().zip(importance).enumerate() {
        let mut best_index = 0usize;
        let mut best_error = 0.0f64;
        for (index, colour) in palette.iter().enumerate() {
            let mut error = 0.0f64;
            for c in 0..4 {
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
fn refine(points: &[Point], importance: &[Point], indices: &[usize; 16]) -> (Point, Point) {
    let n = points.len();
    let mut low = [0.0f64; 4];
    let mut high = [0.0f64; 4];
    let mut fractions = [0.0f64; 16];
    for k in 0..n {
        fractions[k] = WEIGHTS2[indices[k]] as f64 / 64.0;
    }
    for c in 0..4 {
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
    codes: [[i32; 4]; 2],
    pbits: [i32; 2],
    decoded: [[i32; 4]; 2],
    indices: [usize; 16],
}

/// `_fit` with mode 7's weights and quantizer; the anchor's index keeps its top bit clear.
fn fit(points: &[Point], importance: &[Point], anchor: usize) -> Line {
    let n = points.len();
    let (mut low, mut high) = initial(points, importance);
    let mut best: Option<(f64, Line)> = None;
    let mut indices = [0usize; 16];
    for _ in 0..=REFINE_PASSES {
        let (code0, pbit0, decoded0) = quantize_pbit5(&low);
        let (code1, pbit1, decoded1) = quantize_pbit5(&high);
        let error = assign(points, importance, &decoded0, &decoded1, &mut indices);
        if best.as_ref().map_or(true, |b| error < b.0) {
            best = Some((error, Line { codes: [code0, code1], pbits: [pbit0, pbit1],
                                       decoded: [decoded0, decoded1], indices }));
        }
        let refined = refine(points, importance, &indices);
        low = refined.0;
        high = refined.1;
    }
    let (_, mut line) = best.unwrap();
    if line.indices[anchor] > 1 {
        line.codes.swap(0, 1);
        line.pbits.swap(0, 1);
        line.decoded.swap(0, 1);
        for index in line.indices[..n].iter_mut() {
            *index = 3 - *index;
        }
    }
    line
}

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

/// `mismatch` times 16: the summed premultiplied difference, compared as the reference compares it.
fn mismatch_total(pixels: &[Pixel; 16], decoded: &[[i32; 4]; 16]) -> i32 {
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
    fn write(&mut self, value: u32, width: u32) {
        self.value |= (value as u128) << self.position;
        self.position += width;
    }
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

/// One mode 7 block for 16 RGBA pixels in row order.
pub fn mode7(rgba: &[u8; 64]) -> [u8; 16] {
    let mut pixels = [[0i32; 4]; 16];
    let mut importance = [[0.0f64; 4]; 16];
    for i in 0..16 {
        for c in 0..4 {
            pixels[i][c] = rgba[i * 4 + c] as i32;
        }
        let ratio = pixels[i][3] as f64 / 255.0;
        let squared = py_square(ratio);
        let w = if squared > TRANSPARENT_WEIGHT { squared } else { TRANSPARENT_WEIGHT };
        importance[i] = [w, w, w, 1.0];
    }
    let mut keys = [0.0f64; 64];
    for (p, key) in keys.iter_mut().enumerate() {
        let (zero, nz, one, no) = subsets(p);
        *key = spread(&pixels, &zero[..nz], &importance) + spread(&pixels, &one[..no], &importance);
    }
    let mut ranked: [usize; 64] = std::array::from_fn(|p| p);
    ranked.sort_by(|a, b| keys[*a].partial_cmp(&keys[*b]).unwrap_or(std::cmp::Ordering::Equal));

    let mut best: Option<(i32, usize, [[[i32; 4]; 2]; 2], [[i32; 2]; 2], [usize; 16])> = None;
    for &partition in &ranked[..MODE7_TRIES] {
        let (zero, nz, one, no) = subsets(partition);
        let mut decoded = [[0i32; 4]; 16];
        let mut indices = [0usize; 16];
        let mut codes = [[[0i32; 4]; 2]; 2];
        let mut pbits = [[0i32; 2]; 2];
        for (subset, (members, anchor)) in
            [(&zero[..nz], 0usize), (&one[..no], ANCHORS2[partition])].into_iter().enumerate()
        {
            let mut points = [[0.0f64; 4]; 16];
            let mut imp = [[0.0f64; 4]; 16];
            for (k, &i) in members.iter().enumerate() {
                for c in 0..4 {
                    points[k][c] = pixels[i][c] as f64;
                }
                imp[k] = importance[i];
            }
            let position = members.iter().position(|&i| i == anchor).expect("anchor in its subset");
            let line = fit(&points[..members.len()], &imp[..members.len()], position);
            codes[subset] = line.codes;
            pbits[subset] = line.pbits;
            for (k, &i) in members.iter().enumerate() {
                let index = line.indices[k];
                indices[i] = index;
                for c in 0..4 {
                    decoded[i][c] = lerp(line.decoded[0][c], line.decoded[1][c], WEIGHTS2[index]);
                }
            }
        }
        let error = mismatch_total(&pixels, &decoded);
        if best.as_ref().map_or(true, |b| error < b.0) {
            best = Some((error, partition, codes, pbits, indices));
        }
    }
    let (_, partition, codes, pbits, indices) = best.unwrap();
    let mut bits = Bits { value: 0, position: 0 };
    bits.write(1 << 7, 8);
    bits.write(partition as u32, 6);
    let endpoints = [codes[0][0], codes[0][1], codes[1][0], codes[1][1]];
    for channel in 0..4 {
        for endpoint in &endpoints {
            bits.write(endpoint[channel] as u32, 5);
        }
    }
    for pbit in [pbits[0][0], pbits[0][1], pbits[1][0], pbits[1][1]] {
        bits.write(pbit as u32, 1);
    }
    let anchor = ANCHORS2[partition];
    for (i, &index) in indices.iter().enumerate() {
        bits.write(index as u32, if i == 0 || i == anchor { 1 } else { 2 });
    }
    debug_assert_eq!(bits.position, 128);
    bits.value.to_le_bytes()
}

/// `encode_mode7(rgba: bytes) -> bytes`: exactly 64 row-order RGBA bytes in, one 16-byte BC7 block out.
#[pyfunction]
fn encode_mode7<'py>(py: Python<'py>, rgba: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    let block: &[u8; 64] = rgba
        .try_into()
        .map_err(|_| PyValueError::new_err(format!("BC7 mode 7 needs 64 RGBA bytes, got {}", rgba.len())))?;
    Ok(PyBytes::new(py, &mode7(block)))
}

#[pymodule]
fn hok_bc7(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encode_mode7, m)?)?;
    Ok(())
}
