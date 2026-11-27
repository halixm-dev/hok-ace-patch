//! Python entry point for translating one complete localization table at a time.

use hokace_core::{
    qts,
    translation::{self, Catalog},
};
use pyo3::exceptions::{PyUnicodeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use std::collections::HashMap;
use std::{fs::File, path::PathBuf};

fn qts_error(error: qts::Error) -> PyErr {
    match error {
        qts::Error::Io(error) => error.into(),
        other => PyValueError::new_err(other.to_string()),
    }
}

#[pyfunction]
pub(crate) fn qts_index(py: Python<'_>, path: PathBuf) -> PyResult<Vec<[u64; 6]>> {
    let entries = py
        .detach(|| qts::parse_index(File::open(path)?))
        .map_err(qts_error)?;
    Ok(entries.iter().map(qts::IndexEntry::fields).collect())
}

#[pyfunction]
pub(crate) fn qts_slots(
    py: Python<'_>,
    path: PathBuf,
    include_reserved: bool,
) -> PyResult<Vec<[u64; 11]>> {
    let slots = py
        .detach(|| qts::chunk_slots(File::open(path)?, include_reserved))
        .map_err(qts_error)?;
    Ok(slots.iter().map(qts::ChunkSlot::fields).collect())
}

type PayloadFields = (PathBuf, u64, u32, u32);

#[pyfunction]
pub(crate) fn qts_extract(
    py: Python<'_>,
    compression: u16,
    chunks: HashMap<u32, PayloadFields>,
) -> PyResult<Bound<'_, PyBytes>> {
    let bytes = py
        .detach(|| {
            let chunks = chunks
                .into_iter()
                .map(|(id, (path, offset, compressed_size, uncompressed_size))| {
                    (
                        id,
                        qts::Payload {
                            path,
                            offset,
                            compressed_size,
                            uncompressed_size,
                        },
                    )
                })
                .collect();
            qts::extract(compression, &chunks)
        })
        .map_err(|err| PyValueError::new_err(format!("{err:?}")))?;
    Ok(PyBytes::new(py, &bytes))
}

type StockSlot = (u64, u32, u64, u32);

#[pyfunction]
pub(crate) fn qts_live_replacements(
    py: Python<'_>,
    path: PathBuf,
    stock: Vec<StockSlot>,
) -> PyResult<Vec<[u64; 11]>> {
    let slots = py
        .detach(|| qts::live_replacements(File::open(path)?, stock))
        .map_err(qts_error)?;
    Ok(slots.iter().map(qts::ChunkSlot::fields).collect())
}

#[pyclass(module = "hok_codecs", frozen)]
pub(crate) struct RuntimeCatalog {
    catalog: Catalog,
}

#[pymethods]
impl RuntimeCatalog {
    #[new]
    fn new(
        unique: HashMap<String, String>,
        context: Vec<(String, String, String, String)>,
        updates: Vec<(String, String, String, String, String)>,
    ) -> Self {
        Self {
            catalog: Catalog::from_entries(unique, context, updates),
        }
    }

    fn translate<'py>(
        &self,
        py: Python<'py>,
        raw: &[u8],
        asset: u64,
        build_output: bool,
    ) -> PyResult<(Option<Bound<'py, PyBytes>>, Bound<'py, PyDict>)> {
        let result = py
            .detach(|| translation::translate_table(raw, asset, &self.catalog, build_output))
            .map_err(|error| {
                if error.python_class() == "UnicodeDecodeError" {
                    PyUnicodeError::new_err(error.to_string())
                } else {
                    PyValueError::new_err(error.to_string())
                }
            })?;
        let counts = PyDict::new(py);
        for (key, value) in result.counts {
            counts.set_item(key, value)?;
        }
        Ok((result.output.map(|bytes| PyBytes::new(py, &bytes)), counts))
    }
}
