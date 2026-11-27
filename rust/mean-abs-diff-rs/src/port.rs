//! The Rust port of `tools/research/pixel_diff/__init__.py`.
//!
//! Replace each `unimplemented!` with the port of the source function. Return `Err` where
//! the source throws or raises: the caller gets an error there too. After changing a
//! signature, run `rust-anything refresh` to regenerate the bindings. `rust-anything diff` checks
//! behavior against what the source recorded.

#![forbid(unsafe_code)]

/// Port of `mean_abs_diff` (`tools/research/pixel_diff/__init__.py:10`).
///
/// Python sums ints and divides them exactly rounded; the sum stays below 2^53 (255 per byte), so
/// one `f64` division of the two gives the same float.
pub fn mean_abs_diff(left: Vec<u8>, right: Vec<u8>) -> Result<f64, String> {
    if left.is_empty() {
        return Err("ZeroDivisionError: division by zero".into());
    }
    let total: u64 = left
        .iter()
        .zip(&right)
        .map(|(a, b)| u64::from(a.abs_diff(*b)))
        .sum();
    Ok(total as f64 / left.len() as f64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn divides_by_the_left_length() {
        assert_eq!(mean_abs_diff(vec![69, 137], vec![78]), Ok(4.5));
        assert_eq!(mean_abs_diff(vec![1, 2, 3], vec![1, 2, 3]), Ok(0.0));
        assert_eq!(mean_abs_diff(vec![0], vec![255, 9]), Ok(255.0));
    }

    #[test]
    fn empty_left_divides_by_zero() {
        assert_eq!(
            mean_abs_diff(vec![], vec![1]),
            Err("ZeroDivisionError: division by zero".into())
        );
    }
}
