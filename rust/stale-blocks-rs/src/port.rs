//! The Rust port of `tools/block_scan/__init__.py`.
//!
//! Python's ints never overflow, its `//` and `%` floor, and a negative index counts from the end, so
//! the arithmetic runs in `i128` with checked steps and every read goes through [`index`], which
//! raises the `IndexError`s Python raises, in the order it raises them.

#![forbid(unsafe_code)]

const OUT_OF_RANGE: &str = "IndexError: index out of range"; // recorded-literal: CPython's bytes index message
const CANNOT_FIT: &str = "IndexError: cannot fit 'int' into an index-sized integer"; // recorded-literal: CPython's Py_ssize_t overflow message
const ZERO_DIVISION: &str = "ZeroDivisionError: integer division or modulo by zero"; // recorded-literal: CPython's `//` by zero message

/// `data[at]` as Python's bytes indexing does it; `None` is an int past `i128` (it cannot fit either).
fn index(data: &[u8], at: Option<i128>) -> Result<i128, &'static str> {
    let at = i64::try_from(at.ok_or(CANNOT_FIT)?).map_err(|_| CANNOT_FIT)?;
    let at = if at < 0 { at + data.len() as i64 } else { at };
    let byte = usize::try_from(at).ok().and_then(|at| data.get(at));
    byte.map(|&b| i128::from(b)).ok_or(OUT_OF_RANGE)
}

/// Python's `a // b` and `a % b` (both floor toward negative infinity).
fn floor_div_mod(a: i128, b: i128) -> (i128, i128) {
    let (q, r) = (a / b, a % b);
    if r != 0 && ((r < 0) != (b < 0)) {
        (q - 1, r + b)
    } else {
        (q, r)
    }
}

/// `premultiplied_diff`: the largest channel difference once each pixel is weighted by its own alpha.
fn premultiplied_diff(left: &[u8], right: &[u8], at: i128) -> Result<i128, &'static str> {
    let (la, ra) = (index(left, Some(at + 3))?, index(right, Some(at + 3))?);
    let mut worst = (la - ra).abs();
    for channel in 0..3 {
        let (l, r) = (
            index(left, Some(at + channel))?,
            index(right, Some(at + channel))?,
        );
        worst = worst.max((l * la - r * ra).abs() / 255);
    }
    Ok(worst)
}

/// `block_mismatch`: the mean premultiplied difference over a block's decided pixels.
fn block_mismatch(
    images: (&[u8], &[u8], &[u8]),
    block: i128,
    blocks_x: i128,
    width: i128,
) -> Result<f64, &'static str> {
    let (target, device, decided) = images;
    let (row_block, column_block) = floor_div_mod(block, blocks_x);
    let (raw_row, column) = (row_block * 4, column_block * 4);
    let (mut total, mut count) = (0_i128, 0_i128);
    for row in raw_row..raw_row + 4 {
        for x in column..column + 4 {
            let pixel = row.checked_mul(width).and_then(|p| p.checked_add(x));
            if index(decided, pixel)? != 0 {
                // INFALLIBLE: `index` just took `pixel` as an i64, so four times it fits an i128.
                total += premultiplied_diff(target, device, pixel.unwrap_or_default() * 4)?;
                count += 1;
            }
        }
    }
    Ok(if count == 0 {
        0.0
    } else {
        total as f64 / count as f64
    })
}

/// Port of `stale_blocks` (`tools/block_scan/__init__.py:32`).
pub fn stale_blocks(
    target: Vec<u8>,
    device: Vec<u8>,
    decided: Vec<u8>,
    blocks: Vec<i64>,
    width: i64,
    threshold: f64,
) -> Result<Vec<i64>, String> {
    let width = i128::from(width);
    let blocks_x = floor_div_mod(width, 4).0;
    let images = (&target[..], &device[..], &decided[..]);
    let mut stale = Vec::new();
    for &block in &blocks {
        if blocks_x == 0 {
            return Err(ZERO_DIVISION.to_string());
        }
        if block_mismatch(images, i128::from(block), blocks_x, width)? > threshold {
            stale.push(block);
        }
    }
    Ok(stale)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_block_is_stale_only_where_decided_pixels_differ_past_the_threshold() {
        let (white, clear, all) = (vec![255; 64], vec![0; 64], vec![1; 16]);
        let scan = |t: &[u8], d: &[u8], m: &[u8], at| {
            stale_blocks(t.into(), d.into(), m.into(), vec![0], 4, at)
        };
        assert_eq!(scan(&white, &clear, &all, 6.0), Ok(vec![0]));
        assert_eq!(scan(&white, &clear, &[0; 16], 6.0), Ok(vec![]));
        assert_eq!(scan(&white, &white, &all, 0.0), Ok(vec![]));
    }

    #[test]
    fn a_narrow_image_divides_by_zero_only_with_blocks() {
        assert_eq!(
            stale_blocks(vec![], vec![], vec![], vec![], 3, 1.0),
            Ok(vec![])
        );
        let err = stale_blocks(vec![], vec![], vec![], vec![0], 3, 1.0);
        assert_eq!(err, Err(ZERO_DIVISION.to_string()));
    }

    #[test]
    fn indexing_follows_python() {
        assert_eq!(index(&[1, 2, 3], Some(-1)), Ok(3));
        assert_eq!(index(&[1, 2, 3], Some(-4)), Err(OUT_OF_RANGE));
        assert_eq!(index(&[1, 2, 3], Some(3)), Err(OUT_OF_RANGE));
        assert_eq!(index(&[1], Some(i128::from(i64::MAX) + 1)), Err(CANNOT_FIT));
        assert_eq!(index(&[1], None), Err(CANNOT_FIT));
    }

    #[test]
    fn division_floors() {
        assert_eq!(floor_div_mod(-1, 4), (-1, 3));
        assert_eq!(floor_div_mod(7, -2), (-4, -1));
        assert_eq!(floor_div_mod(8, 4), (2, 0));
    }
}
