//! The lane-wise kernels under `vecmath`'s 4-lane types: SSE2 through `safe_arch` on x86_64, plain
//! Rust elsewhere (NEON needs `unsafe`, which the workspace forbids). Every kernel gives the scalar layer's result in every lane, bit for bit: IEEE
//! single-precision add, subtract, multiply, divide and square root with no fusing, `min` as
//! `a < b ? a : b`, `max` as `a > b ? a : b`, `select` on the condition's sign bit, and truncation
//! to `INT_MIN` for NaN or out of range, as MSVC's `cvttss2si`.

pub type F = [f32; 4];
pub type I = [i32; 4];

#[cfg(target_arch = "x86_64")]
mod imp {
    use super::{F, I};
    use bytemuck::cast;
    use safe_arch::*;

    #[inline(always)]
    fn ps(a: F) -> m128 {
        cast(a)
    }
    #[inline(always)]
    fn si(a: I) -> m128i {
        cast(a)
    }
    #[inline(always)]
    fn f(a: m128) -> F {
        cast(a)
    }
    #[inline(always)]
    fn i(a: m128i) -> I {
        cast(a)
    }
    #[inline(always)]
    fn m(a: m128) -> I {
        cast(a)
    }

    #[inline(always)]
    pub fn add(a: F, b: F) -> F {
        f(add_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn sub(a: F, b: F) -> F {
        f(sub_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn mul(a: F, b: F) -> F {
        f(mul_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn div(a: F, b: F) -> F {
        f(div_m128(ps(a), ps(b)))
    }
    /// `minps` returns its second operand unless the first is less: `a < b ? a : b`.
    #[inline(always)]
    pub fn min(a: F, b: F) -> F {
        f(min_m128(ps(a), ps(b)))
    }
    /// `maxps` returns its second operand unless the first is greater: `a > b ? a : b`.
    #[inline(always)]
    pub fn max(a: F, b: F) -> F {
        f(max_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn abs(a: F) -> F {
        f(bitand_m128(ps(a), cast(set_splat_i32_m128i(0x7FFF_FFFF))))
    }
    /// Round half to even without SSE4.1: below 2^23, `(|a| + 2^23) - 2^23` rounds in the default
    /// mode, and the sign bit is put back so `-0.3` gives `-0.0`; larger values, infinities and NaN
    /// pass through unchanged.
    #[inline(always)]
    pub fn round(a: F) -> F {
        let sign = set_splat_i32_m128i(i32::MIN);
        let mag = bitandnot_m128i(sign, si(cast(a)));
        let two23 = set_splat_m128(8_388_608.0);
        let m = cast_to_m128_from_m128i(mag);
        let r = sub_m128(add_m128(m, two23), two23);
        let small = cmp_lt_mask_m128(m, two23);
        let r = bitor_m128(bitand_m128(small, r), bitandnot_m128(small, m));
        f(bitor_m128(
            r,
            bitand_m128(ps(a), cast_to_m128_from_m128i(sign)),
        ))
    }
    #[inline(always)]
    pub fn sqrt(a: F) -> F {
        f(sqrt_m128(ps(a)))
    }
    #[inline(always)]
    pub fn eq(a: F, b: F) -> I {
        m(cmp_eq_mask_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn ne(a: F, b: F) -> I {
        m(cmp_neq_mask_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn lt(a: F, b: F) -> I {
        m(cmp_lt_mask_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn gt(a: F, b: F) -> I {
        m(cmp_gt_mask_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn le(a: F, b: F) -> I {
        m(cmp_le_mask_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn ge(a: F, b: F) -> I {
        m(cmp_ge_mask_m128(ps(a), ps(b)))
    }
    #[inline(always)]
    pub fn select(a: F, b: F, c: I) -> F {
        cast(select_i(cast(a), cast(b), c))
    }
    /// The condition's sign bit spread over its lane, then `(mask & b) | (!mask & a)`.
    #[inline(always)]
    pub fn select_i(a: I, b: I, c: I) -> I {
        let mk = shr_imm_i32_m128i::<31>(si(c));
        i(bitor_m128i(
            bitand_m128i(mk, si(b)),
            bitandnot_m128i(mk, si(a)),
        ))
    }
    #[inline(always)]
    pub fn i2f(a: I) -> F {
        f(convert_to_m128_from_i32_m128i(si(a)))
    }
    /// `cvttps2dq` writes `0x80000000` for NaN or out of range, as `cvttss2si` does.
    #[inline(always)]
    pub fn f2i(a: F) -> I {
        i(truncate_m128_to_m128i(ps(a)))
    }
    #[inline(always)]
    pub fn addi(a: I, b: I) -> I {
        i(add_i32_m128i(si(a), si(b)))
    }
    #[inline(always)]
    pub fn subi(a: I, b: I) -> I {
        i(sub_i32_m128i(si(a), si(b)))
    }
    /// SSE2 has no 32-bit low multiply; the lanes wrap as the scalar layer's do.
    #[inline(always)]
    pub fn muli(a: I, b: I) -> I {
        [
            a[0].wrapping_mul(b[0]),
            a[1].wrapping_mul(b[1]),
            a[2].wrapping_mul(b[2]),
            a[3].wrapping_mul(b[3]),
        ]
    }
    #[inline(always)]
    pub fn and(a: I, b: I) -> I {
        i(bitand_m128i(si(a), si(b)))
    }
    #[inline(always)]
    pub fn or(a: I, b: I) -> I {
        i(bitor_m128i(si(a), si(b)))
    }
    #[inline(always)]
    pub fn xor(a: I, b: I) -> I {
        i(bitxor_m128i(si(a), si(b)))
    }
    #[inline(always)]
    pub fn eqi(a: I, b: I) -> I {
        i(cmp_eq_mask_i32_m128i(si(a), si(b)))
    }
    #[inline(always)]
    pub fn lti(a: I, b: I) -> I {
        i(cmp_lt_mask_i32_m128i(si(a), si(b)))
    }
    #[inline(always)]
    pub fn gti(a: I, b: I) -> I {
        i(cmp_gt_mask_i32_m128i(si(a), si(b)))
    }
    #[inline(always)]
    fn count(s: u32) -> m128i {
        si([s as i32, 0, 0, 0])
    }
    #[inline(always)]
    pub fn lsl(a: I, s: u32) -> I {
        i(shl_all_u32_m128i(si(a), count(s)))
    }
    #[inline(always)]
    pub fn lsr(a: I, s: u32) -> I {
        i(shr_all_u32_m128i(si(a), count(s)))
    }
    #[inline(always)]
    pub fn asr(a: I, s: u32) -> I {
        i(shr_all_i32_m128i(si(a), count(s)))
    }
}

#[cfg(not(target_arch = "x86_64"))]
mod imp {
    use super::{F, I};

    #[inline(always)]
    fn zf(a: F, b: F, op: impl Fn(f32, f32) -> f32) -> F {
        [
            op(a[0], b[0]),
            op(a[1], b[1]),
            op(a[2], b[2]),
            op(a[3], b[3]),
        ]
    }
    #[inline(always)]
    fn zi(a: I, b: I, op: impl Fn(i32, i32) -> i32) -> I {
        [
            op(a[0], b[0]),
            op(a[1], b[1]),
            op(a[2], b[2]),
            op(a[3], b[3]),
        ]
    }
    #[inline(always)]
    fn cf(a: F, b: F, op: impl Fn(f32, f32) -> bool) -> I {
        zf(a, b, |x, y| {
            if op(x, y) {
                f32::from_bits(u32::MAX)
            } else {
                0.0
            }
        })
        .map(|x| x.to_bits() as i32)
    }
    #[inline(always)]
    fn ci(a: I, b: I, op: impl Fn(i32, i32) -> bool) -> I {
        zi(a, b, |x, y| if op(x, y) { -1 } else { 0 })
    }
    pub fn add(a: F, b: F) -> F {
        zf(a, b, |x, y| x + y)
    }
    pub fn sub(a: F, b: F) -> F {
        zf(a, b, |x, y| x - y)
    }
    pub fn mul(a: F, b: F) -> F {
        zf(a, b, |x, y| x * y)
    }
    pub fn div(a: F, b: F) -> F {
        zf(a, b, |x, y| x / y)
    }
    pub fn min(a: F, b: F) -> F {
        zf(a, b, |x, y| if x < y { x } else { y })
    }
    pub fn max(a: F, b: F) -> F {
        zf(a, b, |x, y| if x > y { x } else { y })
    }
    pub fn abs(a: F) -> F {
        a.map(f32::abs)
    }
    pub fn sqrt(a: F) -> F {
        a.map(f32::sqrt)
    }
    pub fn round(a: F) -> F {
        a.map(f32::round_ties_even)
    }
    pub fn eq(a: F, b: F) -> I {
        cf(a, b, |x, y| x == y)
    }
    pub fn ne(a: F, b: F) -> I {
        cf(a, b, |x, y| x != y)
    }
    pub fn lt(a: F, b: F) -> I {
        cf(a, b, |x, y| x < y)
    }
    pub fn gt(a: F, b: F) -> I {
        cf(a, b, |x, y| x > y)
    }
    pub fn le(a: F, b: F) -> I {
        cf(a, b, |x, y| x <= y)
    }
    pub fn ge(a: F, b: F) -> I {
        cf(a, b, |x, y| x >= y)
    }
    pub fn select(a: F, b: F, c: I) -> F {
        [0, 1, 2, 3].map(|k| if c[k] < 0 { b[k] } else { a[k] })
    }
    pub fn select_i(a: I, b: I, c: I) -> I {
        [0, 1, 2, 3].map(|k| if c[k] < 0 { b[k] } else { a[k] })
    }
    pub fn i2f(a: I) -> F {
        a.map(|x| x as f32)
    }
    pub fn f2i(a: F) -> I {
        a.map(crate::vecmath::f2i)
    }
    pub fn addi(a: I, b: I) -> I {
        zi(a, b, i32::wrapping_add)
    }
    pub fn subi(a: I, b: I) -> I {
        zi(a, b, i32::wrapping_sub)
    }
    pub fn muli(a: I, b: I) -> I {
        zi(a, b, i32::wrapping_mul)
    }
    pub fn and(a: I, b: I) -> I {
        zi(a, b, |x, y| x & y)
    }
    pub fn or(a: I, b: I) -> I {
        zi(a, b, |x, y| x | y)
    }
    pub fn xor(a: I, b: I) -> I {
        zi(a, b, |x, y| x ^ y)
    }
    pub fn eqi(a: I, b: I) -> I {
        ci(a, b, |x, y| x == y)
    }
    pub fn lti(a: I, b: I) -> I {
        ci(a, b, |x, y| x < y)
    }
    pub fn gti(a: I, b: I) -> I {
        ci(a, b, |x, y| x > y)
    }
    pub fn lsl(a: I, s: u32) -> I {
        a.map(|x| ((x as u32) << s) as i32)
    }
    pub fn lsr(a: I, s: u32) -> I {
        a.map(|x| ((x as u32) >> s) as i32)
    }
    pub fn asr(a: I, s: u32) -> I {
        a.map(|x| x >> s)
    }
}

pub use imp::*;

#[cfg(test)]
mod tests {
    use super::*;

    const SPECIAL: [f32; 12] = [
        0.0,
        -0.0,
        1.0,
        -1.5,
        f32::NAN,
        f32::INFINITY,
        f32::NEG_INFINITY,
        1e-40,
        -1e-40,
        2_147_483_648.0,
        -2_147_483_648.0,
        2_147_483_520.0,
    ];

    /// Bits, with every NaN as one value: LLVM folds the scalar side's NaN sign at compile time.
    fn bits(a: F) -> [u32; 4] {
        a.map(|x| if x.is_nan() { u32::MAX } else { x.to_bits() })
    }

    /// Each kernel against the scalar definition, over every pair of special values.
    #[test]
    fn kernels_match_the_scalar_layer() {
        for &x in &SPECIAL {
            for &y in &SPECIAL {
                let (a, b) = ([x, y, x, -y], [y, x, -x, y]);
                let s = |op: fn(f32, f32) -> f32| [0, 1, 2, 3].map(|k| op(a[k], b[k]));
                assert_eq!(bits(add(a, b)), bits(s(|p, q| p + q)));
                assert_eq!(bits(sub(a, b)), bits(s(|p, q| p - q)));
                assert_eq!(bits(mul(a, b)), bits(s(|p, q| p * q)));
                assert_eq!(bits(div(a, b)), bits(s(|p, q| p / q)));
                assert_eq!(bits(min(a, b)), bits(s(|p, q| if p < q { p } else { q })));
                assert_eq!(bits(max(a, b)), bits(s(|p, q| if p > q { p } else { q })));
                let m = |op: fn(f32, f32) -> bool| {
                    [0, 1, 2, 3].map(|k| if op(a[k], b[k]) { -1 } else { 0 })
                };
                assert_eq!(lt(a, b), m(|p, q| p < q));
                assert_eq!(le(a, b), m(|p, q| p <= q));
                assert_eq!(gt(a, b), m(|p, q| p > q));
                assert_eq!(ge(a, b), m(|p, q| p >= q));
                assert_eq!(eq(a, b), m(|p, q| p == q));
                assert_eq!(ne(a, b), m(|p, q| p != q));
            }
            let a = [x, -x, x * 3.0, x - 7.0];
            assert_eq!(f2i(a), a.map(crate::vecmath::f2i));
            assert_eq!(bits(abs(a)), bits(a.map(f32::abs)));
            let r = [x, x * 0.5 + 0.5, -x * 0.25 - 0.5, x + 2.5];
            assert_eq!(
                round(r).map(f32::to_bits),
                r.map(|v| f32::round_ties_even(v).to_bits())
            );
        }
        let r = [-0.3, 0.5, 1.5, -2.5];
        assert_eq!(
            round(r).map(f32::to_bits),
            [-0.0f32, 0.0, 2.0, -2.0].map(f32::to_bits)
        );
        let r = [8_388_607.5, -8_388_609.0, 0.49999997, f32::MIN_POSITIVE];
        assert_eq!(
            round(r).map(f32::to_bits),
            r.map(|v| f32::round_ties_even(v).to_bits())
        );
        let c = [i32::MIN, 0, -1, 5];
        assert_eq!(
            select([1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], c),
            [5.0, 2.0, 7.0, 4.0]
        );
        assert_eq!(select_i([1, 2, 3, 4], [5, 6, 7, 8], c), [5, 2, 7, 4]);
        let v = [i32::MIN, -7, 0x1234_5678, 255];
        assert_eq!(lsr(v, 4), v.map(|x| ((x as u32) >> 4) as i32));
        assert_eq!(asr(v, 4), v.map(|x| x >> 4));
        assert_eq!(lsl(v, 8), v.map(|x| ((x as u32) << 8) as i32));
        assert_eq!(
            muli(v, [3, -3, 7, i32::MAX]),
            [0, 1, 2, 3].map(|k| v[k].wrapping_mul([3, -3, 7, i32::MAX][k]))
        );
        assert_eq!(
            i2f([i32::MAX, -1, 16_777_217, 0]),
            [i32::MAX as f32, -1.0, 16_777_217_i32 as f32, 0.0]
        );
    }
}
