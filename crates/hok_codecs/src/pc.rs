//! Python entry points for the PC edition's package metadata and native verification.

use crate::runtime::RuntimeCatalog;
use hokace_core::{
    catalog::CatalogData,
    native_verify, package_metadata, scan,
    scan::{PyError, PyErrorDetail},
};
use hokace_qtsvfs::DllLoader;
use pyo3::exceptions::{PyKeyError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyType};
use serde_json::{Map, Value};
use std::{
    collections::{BTreeMap, HashSet},
    path::PathBuf,
};

type Counts = Vec<(&'static str, usize)>;
type ScanPlan = (PathBuf, PathBuf, Vec<(u64, Counts)>);
type ScanResult = (
    Vec<ScanPlan>,
    Vec<(String, String)>,
    Counts,
    Vec<(String, Option<String>, String)>,
    Vec<(String, String)>,
);

#[pyfunction]
pub(crate) fn pc_scan(
    py: Python<'_>,
    game: PathBuf,
    assets: PathBuf,
    work: PathBuf,
    text: &RuntimeCatalog,
    metadata: (HashSet<i128>, String),
    options: (bool, bool),
) -> Option<ScanResult> {
    py.detach(|| {
        let (known, graphics) = metadata;
        let graphics: Vec<(i128, Map<String, Value>)> = serde_json::from_str(&graphics).ok()?;
        let catalog = CatalogData {
            known,
            graphics: graphics.into_iter().collect(),
            ..CatalogData::default()
        };
        let (materialize, follow_btree) = options;
        let report = scan::scan_with_slots(
            &game,
            &assets,
            &catalog,
            &text.catalog,
            &work,
            materialize,
            follow_btree,
        )
        .ok()?;
        Some((
            report
                .plans
                .into_iter()
                .map(|plan| (plan.package.package_dir, plan.replacements, plan.per_asset))
                .collect(),
            report.fingerprints.into_iter().collect(),
            report.total.into_iter().collect(),
            report
                .skipped
                .into_iter()
                .map(|skip| (skip.package, skip.asset, skip.reason))
                .collect(),
            report.fallbacks,
        ))
    })
}

pub(crate) fn python_error(py: Python<'_>, error: PyError) -> PyErr {
    match error.detail.as_deref() {
        Some(PyErrorDetail::Key(key)) => return PyKeyError::new_err(key.clone()),
        Some(PyErrorDetail::Json(doc)) => {
            return py
                .import("json")
                .and_then(|json| json.call_method1("loads", (doc,)))
                .err()
                .unwrap_or_else(|| PyValueError::new_err(error.message));
        }
        Some(PyErrorDetail::Utf8(bytes)) => {
            return PyBytes::new(py, bytes)
                .call_method1("decode", ("utf-8",))
                .err()
                .unwrap_or_else(|| PyValueError::new_err(error.message));
        }
        _ => {}
    }
    let module = match error.class {
        "NativeReadError" => "wxq_patch.native_verify",
        "LZ4BlockError" => "lz4.block",
        "Error" => "shutil",
        "error" => "struct",
        _ => "builtins",
    };
    let class = py
        .import(module)
        .and_then(|module| module.getattr(error.class));
    match class.and_then(|class| class.cast_into::<PyType>().map_err(Into::into)) {
        Ok(class) => {
            let exception = PyErr::from_type(class, (error.message,));
            if let Some(PyErrorDetail::Os { errno, winerror }) = error.detail.as_deref() {
                let value = exception.value(py);
                let _ = value.setattr("errno", *errno);
                if let Some(code) = winerror {
                    let _ = value.setattr("winerror", *code);
                }
            }
            exception
        }
        Err(_) => PyRuntimeError::new_err(format!("{}: {}", error.class, error.message)),
    }
}

fn report(py: Python<'_>, result: Result<Value, PyError>) -> PyResult<Bound<'_, PyAny>> {
    let value = result.map_err(|error| python_error(py, error))?;
    py.import("json")?
        .call_method1("loads", (value.to_string(),))
}

#[pyfunction]
pub(crate) fn pc_query_package_hash(
    py: Python<'_>,
    game: PathBuf,
    package_dir: PathBuf,
) -> PyResult<u64> {
    // The DLL calls share process state. The query also changes the current directory temporarily.
    package_metadata::query_package_hash(&mut DllLoader, &game, &package_dir)
        .map_err(|error| python_error(py, error))
}

#[pyfunction]
pub(crate) fn pc_stage_package_hash_metadata_batch<'py>(
    py: Python<'py>,
    game: PathBuf,
    package_hashes: &Bound<'py, PyDict>,
    output: PathBuf,
) -> PyResult<Bound<'py, PyAny>> {
    let encoded: String = py
        .import("json")?
        .call_method1("dumps", (package_hashes,))?
        .extract()?;
    let hashes =
        serde_json::from_str(&encoded).map_err(|error| PyValueError::new_err(error.to_string()))?;
    report(
        py,
        py.detach(|| package_metadata::stage_package_hash_metadata_batch(&game, &hashes, &output)),
    )
}

#[pyfunction]
#[pyo3(signature = (game, source, staged, replacements, work, *, verify_all_unrelated=true))]
pub(crate) fn pc_verify_staged_package(
    py: Python<'_>,
    game: PathBuf,
    source: PathBuf,
    staged: PathBuf,
    replacements: BTreeMap<u64, Vec<u8>>,
    work: PathBuf,
    verify_all_unrelated: bool,
) -> PyResult<Bound<'_, PyAny>> {
    report(
        py,
        native_verify::verify_staged_package(
            &mut DllLoader,
            &game,
            &source,
            &staged,
            &replacements,
            &work,
            verify_all_unrelated,
        ),
    )
}
