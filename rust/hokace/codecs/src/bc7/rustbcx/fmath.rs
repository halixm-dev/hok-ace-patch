//! Float helpers the ports share. (The crate's own.)

/// `f32::floor`, by way of an int. On x86-64 without SSE4.1, which is what Rust builds for
/// unless told otherwise, the standard library's `floor` is a call into a software routine;
/// this is a conversion and a compare, and gives the same float for every float, the sign of a
/// zero included.
#[inline]
pub(crate) fn floor(x: f32) -> f32 {
    // (Not-a-number and the infinities fail the test and come back as they are, as do floats
    // of 2^23 and beyond, which are whole already.)
    if x.abs() < 8_388_608.0 && x != 0.0 {
        let truncated = x as i32 as f32;
        if truncated > x {
            truncated - 1.0
        } else {
            truncated
        }
    } else {
        x
    }
}

#[cfg(test)]
mod tests {
    use super::floor;

    #[test]
    fn floor_is_the_standard_librarys_floor() {
        let same = |x: f32| {
            let (ours, theirs) = (floor(x), x.floor());
            assert!(
                ours.to_bits() == theirs.to_bits() || (ours.is_nan() && theirs.is_nan()),
                "{x}: {ours} {theirs}"
            );
        };
        for x in [
            0.0,
            -0.0,
            0.5,
            -0.5,
            1.0,
            -1.0,
            0.999_999_94,
            -0.999_999_94,
            8_388_607.5,
            -8_388_607.5,
            8_388_608.0,
            -8_388_608.0,
            1e30,
            -1e30,
            f32::INFINITY,
            f32::NEG_INFINITY,
            f32::NAN,
            f32::MIN_POSITIVE,
            -f32::MIN_POSITIVE,
            1e-45,
            -1e-45,
        ] {
            same(x);
        }
        // A spread of every kind of float: one bit pattern in each 9,973.
        let mut bits = 0u32;
        loop {
            same(f32::from_bits(bits));
            match bits.checked_add(9973) {
                Some(next) => bits = next,
                None => break,
            }
        }
        // And every float near the whole numbers a colour goes through.
        for whole in -300..300 {
            let x = whole as f32;
            for step in -3i32..=3 {
                same(f32::from_bits((x.to_bits() as i32 + step) as u32));
            }
        }
    }
}
