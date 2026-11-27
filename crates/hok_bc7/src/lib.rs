//! Python bindings for the BC7 fallback search shared with the Rust migration.
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

#[path = "../../../rust/hokace/codecs/src/bc7/search.rs"]
mod search;

fn block_of(rgba: &[u8]) -> PyResult<&[u8; 64]> {
    rgba.try_into().map_err(|_| {
        PyValueError::new_err(format!(
            "a BC7 block needs 64 RGBA bytes, got {}",
            rgba.len()
        ))
    })
}

/// `encode_mode7(rgba: bytes) -> bytes`: exactly 64 row-order RGBA bytes in, one 16-byte BC7 block out.
#[pyfunction]
fn encode_mode7<'py>(py: Python<'py>, rgba: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    encode_mode(py, rgba, 7, 0).map(|(block, _)| block)
}

/// `encode_mode(rgba, mode, index_mode=0) -> (block, decoded RGBA)` for mode 6, 5, 4 or 7.
#[pyfunction]
#[pyo3(signature = (rgba, mode, index_mode=0))]
fn encode_mode<'py>(
    py: Python<'py>,
    rgba: &[u8],
    mode: u32,
    index_mode: u32,
) -> PyResult<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)> {
    let block = block_of(rgba)?;
    let (bytes, decoded) = search::encode_mode(block, mode, index_mode).ok_or_else(|| {
        PyValueError::new_err(format!("no BC7 mode {mode} with index mode {index_mode}"))
    })?;
    Ok((PyBytes::new(py, &bytes), PyBytes::new(py, &decoded)))
}

/// `encode_search(rgba, best_error) -> (block or None, modes tried)`.
#[pyfunction]
fn encode_search<'py>(
    py: Python<'py>,
    rgba: &[u8],
    best_error: f64,
) -> PyResult<(Option<Bound<'py, PyBytes>>, usize)> {
    let block = block_of(rgba)?;
    let (found, tried) = search::search(block, best_error);
    Ok((found.map(|b| PyBytes::new(py, &b)), tried))
}

#[pymodule]
fn hok_bc7(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encode_mode7, m)?)?;
    m.add_function(wrap_pyfunction!(encode_mode, m)?)?;
    m.add_function(wrap_pyfunction!(encode_search, m)?)?;
    Ok(())
}
