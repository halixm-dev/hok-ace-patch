//! Compression and image decoding for the Python patchers.

use hokace_codecs::{bc7, lz4, png, texture, zstd};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

mod runtime;
use pyo3::types::PyBytes;

fn as_bytes<E: std::fmt::Display>(
    py: Python<'_>,
    result: Result<Vec<u8>, E>,
) -> PyResult<Bound<'_, PyBytes>> {
    let bytes = result.map_err(|err| PyValueError::new_err(err.to_string()))?;
    Ok(PyBytes::new(py, &bytes))
}

#[pymodule]
mod hok_codecs {
    #[pymodule_export]
    use super::runtime::RuntimeCatalog;
    #[pymodule_export]
    use super::runtime::{qts_extract, qts_index, qts_live_replacements, qts_slots};
    use super::*;

    #[pyfunction]
    fn lz4_decompress<'py>(
        py: Python<'py>,
        data: &[u8],
        size: usize,
    ) -> PyResult<Bound<'py, PyBytes>> {
        as_bytes(py, py.detach(|| lz4::decompress(data, size)))
    }

    #[pyfunction]
    fn lz4_compress<'py>(py: Python<'py>, data: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
        as_bytes(py, py.detach(|| lz4::compress_hc12(data)))
    }

    #[pyfunction]
    fn zstd_decompress<'py>(
        py: Python<'py>,
        data: &[u8],
        size: usize,
    ) -> PyResult<Bound<'py, PyBytes>> {
        as_bytes(py, py.detach(|| zstd::decompress(data, size)))
    }

    #[pyfunction]
    fn oodle_decompress<'py>(
        py: Python<'py>,
        data: &[u8],
        size: usize,
    ) -> PyResult<Bound<'py, PyBytes>> {
        as_bytes(py, py.detach(|| hokace_oodle::decode(data, size)))
    }

    #[pyfunction]
    fn oodle_stored<'py>(py: Python<'py>, data: &[u8]) -> Bound<'py, PyBytes> {
        let stored = py.detach(|| hokace_oodle::encode_stored(data));
        PyBytes::new(py, &stored)
    }

    #[pyfunction]
    fn decode_astc<'py>(
        py: Python<'py>,
        data: &[u8],
        width: usize,
        height: usize,
        bx: usize,
        by: usize,
    ) -> PyResult<Bound<'py, PyBytes>> {
        as_bytes(
            py,
            py.detach(|| texture::decode_astc(data, width, height, bx, by)),
        )
    }

    #[pyfunction]
    fn decode_bc7<'py>(
        py: Python<'py>,
        data: &[u8],
        width: usize,
        height: usize,
    ) -> PyResult<Bound<'py, PyBytes>> {
        as_bytes(py, py.detach(|| texture::decode_bc7(data, width, height)))
    }

    #[pyfunction]
    fn encode_bc7<'py>(py: Python<'py>, rgba: &[u8]) -> PyResult<(Bound<'py, PyBytes>, usize)> {
        let rgba = rgba
            .try_into()
            .map_err(|_| PyValueError::new_err("a BC7 block needs 64 RGBA bytes"))?;
        let (block, tried) = py
            .detach(|| bc7::encode_block_search(rgba))
            .map_err(PyValueError::new_err)?;
        Ok((PyBytes::new(py, &block), tried))
    }

    #[pyfunction]
    fn decode_png<'py>(py: Python<'py>, data: &[u8]) -> PyResult<(u32, u32, Bound<'py, PyBytes>)> {
        let (width, height, pixels) = py
            .detach(|| png::decode_rgba(data))
            .map_err(PyValueError::new_err)?;
        Ok((width, height, PyBytes::new(py, &pixels)))
    }
}
