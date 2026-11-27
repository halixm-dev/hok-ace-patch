//! Python bindings for the Rust ASTC encoder (`hokace_codecs::astc_encode`, ADR-026), which
//! `tools/mobile_graphics` uses in place of the `astc_encoder` wheel when this module loads.
//!
//! Python interface:
//!
//! - `Encoder(threads)`: one context per footprint, kept for the encoder's lifetime, each with
//!   `threads` workers (the bytes do not depend on it).
//! - `Encoder.encode(rgba, width, height, bx, by) -> bytes`: LDR, quality 85, identity swizzle;
//!   exactly `width * height * 4` row-order RGBA bytes in, the blocks in row order out, 16 bytes
//!   each with no file header. The GIL is released while it encodes.
//!
//! The bytes are the Windows wheel's: every call of both language taps matches.

use hokace_codecs::astc_encode::AstcEncoder;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

#[pyclass(module = "hok_astc")]
struct Encoder {
    inner: AstcEncoder,
}

#[pymethods]
impl Encoder {
    #[new]
    fn new(threads: usize) -> Self {
        Self {
            inner: AstcEncoder::new(threads),
        }
    }

    fn encode<'py>(
        &mut self,
        py: Python<'py>,
        rgba: &[u8],
        width: u32,
        height: u32,
        bx: u32,
        by: u32,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let inner = &mut self.inner;
        let blocks = py
            .detach(|| inner.encode(rgba, width, height, bx, by))
            .map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, &blocks))
    }
}

#[pymodule]
fn hok_astc(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Encoder>()?;
    Ok(())
}
