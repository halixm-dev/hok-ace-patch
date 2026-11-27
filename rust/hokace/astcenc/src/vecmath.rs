//! The 4-lane vector layer (`astcenc_vecmathlib_none_4.h`, `_common_4.h`, `astcenc_vecmathlib.h`)
//! and the `astc::` helpers of `astcenc_mathlib.h`.
//!
//! Each operation is the C++ one lane by lane, in the same order, with no fused multiply-add:
//! MSVC `/fp:precise` on x64 computes every `float` in SSE registers at single precision. The
//! lanes run through `lanes`' SSE2 kernels on x86_64, which give the same bits lane for lane.

use crate::lanes;
use std::ops::{Add, AddAssign, BitAnd, BitOr, BitXor, Div, Mul, Not, Sub};

pub const PI: f32 = std::f32::consts::PI;
pub const PI_OVER_TWO: f32 = std::f32::consts::FRAC_PI_2;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
#[repr(C, align(16))]
pub struct VFloat4(pub [f32; 4]);

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(C, align(16))]
pub struct VInt4(pub [i32; 4]);

/// A lane is set when its sign bit is set; comparisons write -1 or 0.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C, align(16))]
pub struct VMask4(pub [i32; 4]);

/// `static_cast<int>(float)` as MSVC's `cvttss2si`: truncation, and `INT_MIN` for NaN or out of range.
#[inline(always)]
pub fn f2i(v: f32) -> i32 {
    if v.is_nan() || v >= 2_147_483_648.0 || v < -2_147_483_648.0 {
        i32::MIN
    } else {
        v as i32
    }
}

impl VFloat4 {
    #[inline(always)]
    pub const fn new(a: f32, b: f32, c: f32, d: f32) -> Self {
        Self([a, b, c, d])
    }
    #[inline(always)]
    pub const fn splat(a: f32) -> Self {
        Self([a; 4])
    }
    #[inline(always)]
    pub const fn zero() -> Self {
        Self([0.0; 4])
    }
    #[inline(always)]
    pub fn load(p: &[f32]) -> Self {
        let p = &p[..4];
        Self([p[0], p[1], p[2], p[3]])
    }
    #[inline(always)]
    pub fn lane(self, l: usize) -> f32 {
        self.0[l]
    }
    #[inline(always)]
    pub fn set_lane(&mut self, l: usize, a: f32) {
        self.0[l] = a;
    }
    #[inline(always)]
    pub fn swz2(self, l0: usize, l1: usize) -> Self {
        Self([self.0[l0], self.0[l1], 0.0, 0.0])
    }
    #[inline(always)]
    pub fn swz3(self, l0: usize, l1: usize, l2: usize) -> Self {
        Self([self.0[l0], self.0[l1], self.0[l2], 0.0])
    }
    #[inline(always)]
    pub fn swz4(self, l0: usize, l1: usize, l2: usize, l3: usize) -> Self {
        Self([self.0[l0], self.0[l1], self.0[l2], self.0[l3]])
    }
    #[inline(always)]
    pub fn store(self, p: &mut [f32]) {
        p[..4].copy_from_slice(&self.0);
    }
    #[inline(always)]
    pub fn eq(self, b: Self) -> VMask4 {
        VMask4(lanes::eq(self.0, b.0))
    }
    #[inline(always)]
    pub fn ne(self, b: Self) -> VMask4 {
        VMask4(lanes::ne(self.0, b.0))
    }
    #[inline(always)]
    pub fn lt(self, b: Self) -> VMask4 {
        VMask4(lanes::lt(self.0, b.0))
    }
    #[inline(always)]
    pub fn gt(self, b: Self) -> VMask4 {
        VMask4(lanes::gt(self.0, b.0))
    }
    #[inline(always)]
    pub fn le(self, b: Self) -> VMask4 {
        VMask4(lanes::le(self.0, b.0))
    }
    #[inline(always)]
    pub fn ge(self, b: Self) -> VMask4 {
        VMask4(lanes::ge(self.0, b.0))
    }
}

impl VInt4 {
    #[inline(always)]
    pub const fn new(a: i32, b: i32, c: i32, d: i32) -> Self {
        Self([a, b, c, d])
    }
    #[inline(always)]
    pub const fn splat(a: i32) -> Self {
        Self([a; 4])
    }
    #[inline(always)]
    pub const fn zero() -> Self {
        Self([0; 4])
    }
    #[inline(always)]
    pub const fn lane_id() -> Self {
        Self([0, 1, 2, 3])
    }
    #[inline(always)]
    pub fn from_u8(p: &[u8]) -> Self {
        let p = &p[..4];
        Self([p[0] as i32, p[1] as i32, p[2] as i32, p[3] as i32])
    }
    #[inline(always)]
    pub fn load(p: &[i32]) -> Self {
        let p = &p[..4];
        Self([p[0], p[1], p[2], p[3]])
    }
    #[inline(always)]
    pub fn lane(self, l: usize) -> i32 {
        self.0[l]
    }
    #[inline(always)]
    pub fn set_lane(&mut self, l: usize, a: i32) {
        self.0[l] = a;
    }
    #[inline(always)]
    pub fn store(self, p: &mut [i32]) {
        p[..4].copy_from_slice(&self.0);
    }
    #[inline(always)]
    pub fn eq(self, b: Self) -> VMask4 {
        VMask4(lanes::eqi(self.0, b.0))
    }
    #[inline(always)]
    pub fn ne(self, b: Self) -> VMask4 {
        !self.eq(b)
    }
    #[inline(always)]
    pub fn lt(self, b: Self) -> VMask4 {
        VMask4(lanes::lti(self.0, b.0))
    }
    #[inline(always)]
    pub fn gt(self, b: Self) -> VMask4 {
        VMask4(lanes::gti(self.0, b.0))
    }
    #[inline(always)]
    pub fn lsl(self, s: u32) -> Self {
        Self(lanes::lsl(self.0, s))
    }
    #[inline(always)]
    pub fn lsr(self, s: u32) -> Self {
        Self(lanes::lsr(self.0, s))
    }
    #[inline(always)]
    pub fn asr(self, s: u32) -> Self {
        Self(lanes::asr(self.0, s))
    }
}

impl VMask4 {
    #[inline(always)]
    pub const fn splat(a: bool) -> Self {
        Self([if a { -1 } else { 0 }; 4])
    }
    #[inline(always)]
    pub const fn new(a: bool, b: bool, c: bool, d: bool) -> Self {
        Self([
            if a { -1 } else { 0 },
            if b { -1 } else { 0 },
            if c { -1 } else { 0 },
            if d { -1 } else { 0 },
        ])
    }
    #[inline(always)]
    pub fn lane(self, l: usize) -> bool {
        self.0[l] != 0
    }
}

macro_rules! binop {
    ($t:ident, $s:ty, $tr:ident, $f:ident, $e:expr) => {
        impl $tr for $t {
            type Output = $t;
            #[inline(always)]
            fn $f(self, b: $t) -> $t {
                Self($e(self.0, b.0))
            }
        }
        impl $tr<$s> for $t {
            type Output = $t;
            #[inline(always)]
            fn $f(self, b: $s) -> $t {
                Self($e(self.0, [b; 4]))
            }
        }
    };
}
binop!(VFloat4, f32, Add, add, lanes::add);
binop!(VFloat4, f32, Sub, sub, lanes::sub);
binop!(VFloat4, f32, Mul, mul, lanes::mul);
binop!(VFloat4, f32, Div, div, lanes::div);
binop!(VInt4, i32, Add, add, lanes::addi);
binop!(VInt4, i32, Sub, sub, lanes::subi);
binop!(VInt4, i32, Mul, mul, lanes::muli);
binop!(VInt4, i32, BitOr, bitor, lanes::or);
binop!(VInt4, i32, BitAnd, bitand, lanes::and);
binop!(VInt4, i32, BitXor, bitxor, lanes::xor);

impl Mul<VFloat4> for f32 {
    type Output = VFloat4;
    #[inline(always)]
    fn mul(self, b: VFloat4) -> VFloat4 {
        VFloat4::splat(self) * b
    }
}
impl Div<VFloat4> for f32 {
    type Output = VFloat4;
    #[inline(always)]
    fn div(self, b: VFloat4) -> VFloat4 {
        VFloat4::splat(self) / b
    }
}
impl AddAssign for VFloat4 {
    #[inline(always)]
    fn add_assign(&mut self, b: VFloat4) {
        *self = *self + b;
    }
}
impl AddAssign for VInt4 {
    #[inline(always)]
    fn add_assign(&mut self, b: VInt4) {
        *self = *self + b;
    }
}
impl Not for VInt4 {
    type Output = VInt4;
    #[inline(always)]
    fn not(self) -> VInt4 {
        Self(lanes::xor(self.0, [-1; 4]))
    }
}
impl BitOr for VMask4 {
    type Output = VMask4;
    #[inline(always)]
    fn bitor(self, b: VMask4) -> VMask4 {
        VMask4(lanes::or(self.0, b.0))
    }
}
impl BitAnd for VMask4 {
    type Output = VMask4;
    #[inline(always)]
    fn bitand(self, b: VMask4) -> VMask4 {
        VMask4(lanes::and(self.0, b.0))
    }
}
impl BitXor for VMask4 {
    type Output = VMask4;
    #[inline(always)]
    fn bitxor(self, b: VMask4) -> VMask4 {
        VMask4(lanes::xor(self.0, b.0))
    }
}
impl Not for VMask4 {
    type Output = VMask4;
    #[inline(always)]
    fn not(self) -> VMask4 {
        VMask4(lanes::xor(self.0, [-1; 4]))
    }
}

#[inline(always)]
pub fn mask(a: VMask4) -> u32 {
    (((a.0[0] >> 31) & 1) | ((a.0[1] >> 30) & 2) | ((a.0[2] >> 29) & 4) | ((a.0[3] >> 28) & 8))
        as u32
}
#[inline(always)]
pub fn any(a: VMask4) -> bool {
    mask(a) != 0
}
#[inline(always)]
pub fn all(a: VMask4) -> bool {
    mask(a) == 0xF
}

// ---- vint4 ----

#[inline(always)]
pub fn mini(a: VInt4, b: VInt4) -> VInt4 {
    select_i(b, a, a.lt(b))
}
#[inline(always)]
pub fn maxi(a: VInt4, b: VInt4) -> VInt4 {
    select_i(b, a, a.gt(b))
}
#[inline(always)]
pub fn clampi(minv: i32, maxv: i32, a: VInt4) -> VInt4 {
    mini(maxi(a, VInt4::splat(minv)), VInt4::splat(maxv))
}
#[inline(always)]
pub fn hmin_i(a: VInt4) -> VInt4 {
    let b = a.0[0].min(a.0[1]);
    let c = a.0[2].min(a.0[3]);
    VInt4::splat(b.min(c))
}
#[inline(always)]
pub fn hmax_i(a: VInt4) -> VInt4 {
    let b = a.0[0].max(a.0[1]);
    let c = a.0[2].max(a.0[3]);
    VInt4::splat(b.max(c))
}
#[inline(always)]
pub fn hmin_s_i(a: VInt4) -> i32 {
    hmin_i(a).0[0]
}
#[inline(always)]
pub fn hmax_s_i(a: VInt4) -> i32 {
    hmax_i(a).0[0]
}
#[inline(always)]
pub fn hadd_s_i(a: VInt4) -> i32 {
    a.0[0]
        .wrapping_add(a.0[1])
        .wrapping_add(a.0[2])
        .wrapping_add(a.0[3])
}
#[inline(always)]
pub fn hadd_rgb_s_i(a: VInt4) -> i32 {
    a.0[0] + a.0[1] + a.0[2]
}
#[inline(always)]
pub fn select_i(a: VInt4, b: VInt4, cond: VMask4) -> VInt4 {
    VInt4(lanes::select_i(a.0, b.0, cond.0))
}
/// `pack_and_store_low_bytes`: the low byte of each lane, in lane order.
#[inline(always)]
pub fn pack_low_bytes(a: VInt4) -> [u8; 4] {
    [a.0[0] as u8, a.0[1] as u8, a.0[2] as u8, a.0[3] as u8]
}
#[inline(always)]
pub fn interleave_rgba8(r: VInt4, g: VInt4, b: VInt4, a: VInt4) -> VInt4 {
    r + g.lsl(8) + b.lsl(16) + a.lsl(24)
}
#[inline(always)]
pub fn popcount(mut v: u64) -> i32 {
    let mask1 = 0x5555_5555_5555_5555u64;
    let mask2 = 0x3333_3333_3333_3333u64;
    let mask3 = 0x0F0F_0F0F_0F0F_0F0Fu64;
    v -= (v >> 1) & mask1;
    v = (v & mask2) + ((v >> 2) & mask2);
    v += v >> 4;
    v &= mask3;
    v = v.wrapping_mul(0x0101_0101_0101_0101);
    v >>= 56;
    v as i32
}
#[inline(always)]
pub fn bit_transfer_signed(input0: &mut VInt4, input1: &mut VInt4) {
    *input1 = input1.lsr(1) | (*input0 & 0x80);
    *input0 = input0.lsr(1) & 0x3F;
    let mask = (*input0 & 0x20).ne(VInt4::zero());
    *input0 = select_i(*input0, *input0 - 0x40, mask);
}

// ---- vfloat4 ----

#[inline(always)]
pub fn min(a: VFloat4, b: VFloat4) -> VFloat4 {
    VFloat4(lanes::min(a.0, b.0))
}
#[inline(always)]
pub fn max(a: VFloat4, b: VFloat4) -> VFloat4 {
    VFloat4(lanes::max(a.0, b.0))
}
#[inline(always)]
pub fn min_s(a: VFloat4, b: f32) -> VFloat4 {
    min(a, VFloat4::splat(b))
}
#[inline(always)]
pub fn max_s(a: VFloat4, b: f32) -> VFloat4 {
    max(a, VFloat4::splat(b))
}
#[inline(always)]
pub fn clamp(minv: f32, maxv: f32, a: VFloat4) -> VFloat4 {
    min_s(max_s(a, minv), maxv)
}
#[inline(always)]
pub fn clampzo(a: VFloat4) -> VFloat4 {
    min_s(max(a, VFloat4::zero()), 1.0)
}
#[inline(always)]
pub fn abs(a: VFloat4) -> VFloat4 {
    VFloat4(lanes::abs(a.0))
}
/// `std::nearbyint` in round-to-nearest-even mode.
#[inline(always)]
pub fn round(a: VFloat4) -> VFloat4 {
    VFloat4(lanes::round(a.0))
}
/// `std::min(a, b)`: `(b < a) ? b : a`.
#[inline(always)]
fn std_min(a: f32, b: f32) -> f32 {
    if b < a { b } else { a }
}
/// `std::max(a, b)`: `(a < b) ? b : a`.
#[inline(always)]
fn std_max(a: f32, b: f32) -> f32 {
    if a < b { b } else { a }
}
#[inline(always)]
pub fn hmin(a: VFloat4) -> VFloat4 {
    let t1 = std_min(a.0[0], a.0[1]);
    let t2 = std_min(a.0[2], a.0[3]);
    VFloat4::splat(std_min(t1, t2))
}
#[inline(always)]
pub fn hmax(a: VFloat4) -> VFloat4 {
    let t1 = std_max(a.0[0], a.0[1]);
    let t2 = std_max(a.0[2], a.0[3]);
    VFloat4::splat(std_max(t1, t2))
}
#[inline(always)]
pub fn hmin_s(a: VFloat4) -> f32 {
    hmin(a).0[0]
}
#[inline(always)]
pub fn hmax_s(a: VFloat4) -> f32 {
    hmax(a).0[0]
}
#[inline(always)]
pub fn hmin_rgb_s(mut a: VFloat4) -> f32 {
    a.0[3] = a.0[0];
    hmin_s(a)
}
/// The invariant horizontal sum: `(a0 + a2) + (a1 + a3)`.
#[inline(always)]
pub fn hadd_s(a: VFloat4) -> f32 {
    (a.0[0] + a.0[2]) + (a.0[1] + a.0[3])
}
#[inline(always)]
pub fn hadd_rgb_s(a: VFloat4) -> f32 {
    a.0[0] + a.0[1] + a.0[2]
}
#[inline(always)]
pub fn sqrt(a: VFloat4) -> VFloat4 {
    VFloat4(lanes::sqrt(a.0))
}
#[inline(always)]
pub fn select(a: VFloat4, b: VFloat4, cond: VMask4) -> VFloat4 {
    VFloat4(lanes::select(a.0, b.0, cond.0))
}
/// `gatherf_byte_inds`: `gatherf` at four byte indices read straight from memory.
#[inline(always)]
pub fn gatherf_u8(base: &[f32], idx: &[u8]) -> VFloat4 {
    let idx = &idx[..4];
    VFloat4([
        base[idx[0] as usize],
        base[idx[1] as usize],
        base[idx[2] as usize],
        base[idx[3] as usize],
    ])
}
#[inline(always)]
pub fn haccumulate(accum: &mut VFloat4, a: VFloat4) {
    *accum += a;
}
#[inline(always)]
pub fn haccumulate_m(accum: &mut VFloat4, a: VFloat4, m: VMask4) {
    let a = select(VFloat4::zero(), a, m);
    haccumulate(accum, a);
}
#[inline(always)]
pub fn dot_s(a: VFloat4, b: VFloat4) -> f32 {
    hadd_s(a * b)
}
#[inline(always)]
pub fn dot(a: VFloat4, b: VFloat4) -> VFloat4 {
    VFloat4::splat(hadd_s(a * b))
}
#[inline(always)]
pub fn dot3_s(a: VFloat4, b: VFloat4) -> f32 {
    hadd_rgb_s(a * b)
}
#[inline(always)]
pub fn dot3(a: VFloat4, b: VFloat4) -> VFloat4 {
    let d3 = hadd_rgb_s(a * b);
    VFloat4([d3, d3, d3, 0.0])
}
#[inline(always)]
pub fn float_to_int(a: VFloat4) -> VInt4 {
    VInt4(lanes::f2i(a.0))
}
#[inline(always)]
pub fn float_to_int_rtn(a: VFloat4) -> VInt4 {
    float_to_int(a + VFloat4::splat(0.5))
}
#[inline(always)]
pub fn int_to_float(a: VInt4) -> VFloat4 {
    VFloat4(lanes::i2f(a.0))
}
#[inline(always)]
pub fn float_as_int(a: VFloat4) -> VInt4 {
    VInt4(bytemuck::cast(a.0))
}
#[inline(always)]
pub fn int_as_float(a: VInt4) -> VFloat4 {
    VFloat4(bytemuck::cast(a.0))
}

// ---- astcenc_vecmathlib.h ----

#[inline(always)]
pub fn round_down_to_simd_multiple_4(count: u32) -> u32 {
    count & !3
}
#[inline(always)]
pub fn round_down_to_simd_multiple_vla(count: u32) -> u32 {
    count & !3
}
#[inline(always)]
pub fn round_up_to_simd_multiple_vla(count: u32) -> u32 {
    count.div_ceil(4) * 4
}
#[inline(always)]
pub fn change_sign(a: VFloat4, b: VFloat4) -> VFloat4 {
    let ia = float_as_int(a);
    let ib = float_as_int(b);
    int_as_float(ia ^ (ib & i32::MIN))
}
#[inline(always)]
pub fn atan(x: VFloat4) -> VFloat4 {
    let c = abs(x).gt(VFloat4::splat(1.0));
    let z = change_sign(VFloat4::splat(PI_OVER_TWO), x);
    let y = select(x, VFloat4::splat(1.0) / x, c);
    let y = y / (y * y * VFloat4::splat(0.28) + VFloat4::splat(1.0));
    select(y, z - y, c)
}
#[inline(always)]
pub fn atan2(y: VFloat4, x: VFloat4) -> VFloat4 {
    let z = atan(abs(y / x));
    let xmask = x.lt(VFloat4::zero());
    change_sign(select(z, VFloat4::splat(PI) - z, xmask), y)
}
#[inline(always)]
pub fn unit4() -> VFloat4 {
    VFloat4::splat(0.5)
}
#[inline(always)]
pub fn unit3() -> VFloat4 {
    #[expect(clippy::excessive_precision, reason = "the C++ literal")]
    let v = 0.577350258827209473_f32;
    VFloat4([v, v, v, 0.0])
}
#[inline(always)]
pub fn unit2() -> VFloat4 {
    #[expect(clippy::excessive_precision, reason = "the C++ literal")]
    let v = 0.707106769084930420_f32;
    VFloat4([v, v, 0.0, 0.0])
}
#[inline(always)]
pub fn vfloat3(a: f32, b: f32, c: f32) -> VFloat4 {
    VFloat4([a, b, c, 0.0])
}
#[inline(always)]
pub fn vfloat2(a: f32, b: f32) -> VFloat4 {
    VFloat4([a, b, 0.0, 0.0])
}
#[inline(always)]
pub fn normalize(a: VFloat4) -> VFloat4 {
    let length = dot(a, a);
    a / sqrt(length)
}
#[inline(always)]
pub fn normalize_safe(a: VFloat4, safe: VFloat4) -> VFloat4 {
    let length = dot(a, a);
    if length.0[0] != 0.0 {
        return a / sqrt(length);
    }
    safe
}
pub fn exp2(x: VFloat4) -> VFloat4 {
    let x = clamp(-126.999_99, 129.0, x);
    let ipart = float_to_int(x - 0.5);
    let fpart = x - int_to_float(ipart);
    let iexp = int_as_float((ipart + 127).lsl(23));
    let c = [
        9.9999994e-1_f32,
        6.931_531e-1,
        2.4015361e-1,
        5.5826318e-2,
        8.989_34e-3,
        1.8775767e-3,
    ];
    let fexp = ((((VFloat4::splat(c[5]) * fpart + c[4]) * fpart + c[3]) * fpart + c[2]) * fpart
        + c[1])
        * fpart
        + c[0];
    iexp * fexp
}
pub fn log2(x: VFloat4) -> VFloat4 {
    let i = float_as_int(x);
    let e = int_to_float((i & 0x7F80_0000).lsr(23) - 127);
    let mm = int_as_float((i & 0x007F_FFFF) | 0x3F80_0000);
    #[expect(clippy::excessive_precision, reason = "the C++ literals")]
    let c = [
        2.8882704548164776201_f32,
        -2.52074962577807006663,
        1.48116647521213171641,
        -0.465725644288844778798,
        0.0596515482674574969533,
    ];
    let p = (((VFloat4::splat(c[4]) * mm + c[3]) * mm + c[2]) * mm + c[1]) * mm + c[0];
    let p = p * (mm - 1.0);
    p + e
}
pub fn pow(x: VFloat4, y: VFloat4) -> VFloat4 {
    let zero_mask = y.eq(VFloat4::splat(0.0));
    let estimate = exp2(log2(x) * y);
    select(estimate, VFloat4::splat(1.0), zero_mask)
}
pub fn clz(a: VInt4) -> VInt4 {
    let a = (!a.lsr(8)) & a;
    let a = float_as_int(int_to_float(a));
    let a = VInt4::splat(127 + 31) - a.lsr(23);
    clampi(0, 32, a)
}
pub fn two_to_the_n(a: VInt4) -> VInt4 {
    let exp = (a + 127).lsl(23);
    float_to_int(int_as_float(exp))
}
pub fn frexp(a: VFloat4, exp: &mut VInt4) -> VFloat4 {
    let ai = float_as_int(a);
    *exp = (ai.lsr(23) & 0xFF) - 126;
    int_as_float((ai & 0x807F_FFFFu32 as i32) | 0x3F00_0000)
}

// ---- astc:: (astcenc_mathlib.h) ----

pub mod astc {
    #[inline(always)]
    pub fn min<T: PartialOrd>(p: T, q: T) -> T {
        if p < q { p } else { q }
    }
    #[inline(always)]
    pub fn max<T: PartialOrd>(p: T, q: T) -> T {
        if p > q { p } else { q }
    }
    #[inline(always)]
    pub fn min3<T: PartialOrd + Copy>(p: T, q: T, r: T) -> T {
        min(min(p, q), r)
    }
    #[inline(always)]
    pub fn max3<T: PartialOrd + Copy>(p: T, q: T, r: T) -> T {
        max(max(p, q), r)
    }
    #[inline(always)]
    pub fn min4<T: PartialOrd + Copy>(p: T, q: T, r: T, s: T) -> T {
        min(min(p, q), min(r, s))
    }
    #[inline(always)]
    pub fn max4<T: PartialOrd + Copy>(p: T, q: T, r: T, s: T) -> T {
        max(max(p, q), max(r, s))
    }
    #[inline(always)]
    pub fn clamp<T: PartialOrd>(v: T, mn: T, mx: T) -> T {
        if v > mx {
            return mx;
        }
        if v > mn {
            return v;
        }
        mn
    }
    #[inline(always)]
    pub fn clamp1f(v: f32) -> f32 {
        clamp(v, 0.0, 1.0)
    }
    #[inline(always)]
    pub fn clamp255f(v: f32) -> f32 {
        clamp(v, 0.0, 255.0)
    }
    #[inline(always)]
    pub fn flt_rd(v: f32) -> f32 {
        v.floor()
    }
    #[inline(always)]
    pub fn flt2int_rtn(v: f32) -> i32 {
        super::f2i(v + 0.5)
    }
    #[inline(always)]
    pub fn flt2int_rd(v: f32) -> i32 {
        super::f2i(v)
    }
    #[inline(always)]
    pub fn float_as_int(v: f32) -> i32 {
        v.to_bits() as i32
    }
    #[inline(always)]
    pub fn int_as_float(v: i32) -> f32 {
        f32::from_bits(v as u32)
    }
    #[inline(always)]
    pub fn rsqrt(v: f32) -> f32 {
        1.0 / v.sqrt()
    }
    #[inline(always)]
    pub fn isnan(v: f32) -> bool {
        v.is_nan()
    }
    pub fn pow(x: f32, y: f32) -> f32 {
        super::pow(super::VFloat4::splat(x), super::VFloat4::splat(y)).0[0]
    }
    pub fn rand_init() -> [u64; 2] {
        [0xfaf9_e171_cea1_ec6b, 0xf1b3_18cc_06af_5d71]
    }
    pub fn rand(state: &mut [u64; 2]) -> u64 {
        let s0 = state[0];
        let mut s1 = state[1];
        let res = s0.wrapping_add(s1);
        s1 ^= s0;
        state[0] = s0.rotate_left(24) ^ s1 ^ (s1 << 16);
        state[1] = s1.rotate_left(37);
        res
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn horizontal_sum_is_invariant_order() {
        // (a0 + a2) + (a1 + a3), not left to right.
        let a = VFloat4::new(1e8, 1.0, -1e8, 1.0);
        assert_eq!(hadd_s(a), 2.0);
    }

    #[test]
    fn truncation_matches_cvttss2si() {
        assert_eq!(f2i(f32::NAN), i32::MIN);
        assert_eq!(f2i(3e9), i32::MIN);
        assert_eq!(f2i(-2.7), -2);
    }

    #[test]
    fn select_reads_the_sign_bit() {
        let r = select(
            VFloat4::splat(1.0),
            VFloat4::splat(2.0),
            VMask4([-1, 0, i32::MIN, 1]),
        );
        assert_eq!(r.0, [2.0, 1.0, 2.0, 1.0]);
    }

    #[test]
    fn clz_and_popcount() {
        assert_eq!(clz(VInt4::new(1, 0x8000, 0, 0xFFFF)).0, [31, 16, 32, 16]);
        assert_eq!(popcount(0xF0F0), 8);
    }
}
