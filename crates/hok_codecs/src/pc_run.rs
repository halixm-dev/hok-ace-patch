//! The Windows PC transaction engine and its callbacks into the Python patcher.

use crate::pc::python_error;
use hokace_core::{
    run::{self, RunHost, RunPlan, RunScan},
    scan::PyError,
};
use indexmap::IndexMap;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};
use serde_json::{Map, Value};
use std::path::{Path, PathBuf};

struct PythonHost<'py> {
    runtime: Bound<'py, PyModule>,
    json: Bound<'py, PyModule>,
    preserve_launcher_list: bool,
    callback_error: Option<PyErr>,
}

type StagingPlan<'py> = (Bound<'py, PyAny>, PathBuf, Bound<'py, PyAny>);

impl PythonHost<'_> {
    fn capture<T>(&mut self, result: PyResult<T>) -> Result<T, PyError> {
        result.map_err(|error| {
            // The core propagates callback failures. Keep Python's original exception and attributes.
            self.callback_error = Some(error);
            PyError::new("RuntimeError", "PC engine callback failed")
        })
    }

    fn value(&self, object: &Bound<'_, PyAny>) -> PyResult<Value> {
        let text: String = self.json.call_method1("dumps", (object,))?.extract()?;
        serde_json::from_str(&text).map_err(|error| PyValueError::new_err(error.to_string()))
    }
}

impl RunHost for PythonHost<'_> {
    type Replacements = PathBuf;

    fn receipt_root(&mut self, game: &Path) -> Result<PathBuf, PyError> {
        let result = self
            .runtime
            .call_method1("receipt_root", (game,))
            .and_then(|path| path.extract());
        self.capture(result)
    }

    fn preserve_launcher_list(&self) -> bool {
        self.preserve_launcher_list
    }

    fn assert_game_stopped(&mut self) -> Result<(), PyError> {
        let result = self
            .runtime
            .call_method0("_assert_game_stopped")
            .map(|_| ());
        self.capture(result)
    }

    fn scan(
        &mut self,
        game: &Path,
        assets: &Path,
        work: &Path,
        materialize: bool,
    ) -> Result<RunScan<PathBuf>, PyError> {
        let result = (|| {
            let options = PyDict::new(self.runtime.py());
            options.set_item("materialize", materialize)?;
            let result = self
                .runtime
                .call_method("scan", (game, assets, work), Some(&options))?;
            let (plans, fingerprints, counts, skipped): (
                Vec<StagingPlan<'_>>,
                Bound<'_, PyDict>,
                Bound<'_, PyAny>,
                Bound<'_, PyAny>,
            ) = result.extract()?;
            let plans = plans
                .into_iter()
                .map(|(package, replacements, _)| {
                    Ok(RunPlan {
                        package_id: package.getattr("package_id")?.extract()?,
                        package_dir: package.getattr("package_dir")?.extract()?,
                        index_path: package.getattr("index_path")?.extract()?,
                        shard_paths: package.getattr("shard_paths")?.extract()?,
                        replacements,
                    })
                })
                .collect::<PyResult<_>>()?;
            let fingerprints = fingerprints
                .iter()
                .map(|(key, value)| Ok((key.extract()?, value.extract()?)))
                .collect::<PyResult<_>>()?;
            let counts = self.value(&counts)?;
            let counts = counts
                .as_object()
                .cloned()
                .ok_or_else(|| PyValueError::new_err("PC scan counts must be an object"))?;
            Ok(RunScan {
                plans,
                fingerprints,
                counts,
                skipped: self.value(&skipped)?,
            })
        })();
        self.capture(result)
    }

    fn stage_unity_package(
        &mut self,
        game: &Path,
        replacements: &PathBuf,
        stage: &Path,
        source_package_dir: &Path,
        source_hashes: &IndexMap<String, String>,
    ) -> Result<Value, PyError> {
        let result = (|| {
            let hashes = PyDict::new(self.runtime.py());
            for (path, hash) in source_hashes {
                hashes.set_item(path, hash)?;
            }
            let options = PyDict::new(self.runtime.py());
            options.set_item("source_package_dir", source_package_dir)?;
            options.set_item("global_donations", true)?;
            options.set_item("verify_all_unrelated", false)?;
            options.set_item("source_hashes", hashes)?;
            let answer = self.runtime.call_method(
                "stage_unity_package",
                (game, replacements, stage),
                Some(&options),
            )?;
            self.value(&answer)
        })();
        self.capture(result)
    }

    fn query_package_hash(&mut self, game: &Path, package_dir: &Path) -> Result<Value, PyError> {
        let result = self
            .runtime
            .call_method1("query_package_hash", (game, package_dir))
            .and_then(|hash| self.value(&hash));
        self.capture(result)
    }

    fn stage_package_hash_metadata_batch(
        &mut self,
        game: &Path,
        package_hashes: &Map<String, Value>,
        output: &Path,
    ) -> Result<Value, PyError> {
        let result = (|| {
            let hashes = self.json.call_method1(
                "loads",
                (Value::Object(package_hashes.clone()).to_string(),),
            )?;
            let answer = self
                .runtime
                .call_method1("stage_package_hash_metadata_batch", (game, hashes, output))?;
            self.value(&answer)
        })();
        self.capture(result)
    }
}

#[pyfunction]
#[pyo3(signature = (action, game, assets, work, *, preserve_launcher_list=true))]
pub(crate) fn pc_run<'py>(
    py: Python<'py>,
    action: &str,
    game: PathBuf,
    assets: PathBuf,
    work: PathBuf,
    preserve_launcher_list: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let mut host = PythonHost {
        runtime: py.import("wxq_patch.adaptive")?,
        json: py.import("json")?,
        preserve_launcher_list,
        callback_error: None,
    };
    // PC jobs are child processes. Keep the GIL while callbacks use the game's DLLs and CWD.
    let report = run::run(action, &game, &assets, &work, &mut host).map_err(|error| {
        host.callback_error
            .take()
            .unwrap_or_else(|| python_error(py, error))
    })?;
    host.json
        .call_method1("loads", (Value::Object(report).to_string(),))
}
