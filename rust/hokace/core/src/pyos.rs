//! The pieces of Python's `os`, `pathlib`, `str` and `json` behaviour the PC engine's port relies on
//! (`wxq_patch.adaptive`'s transaction layer and `launcher_metadata`).
//!
//! Each helper mirrors CPython 3.12 on Windows, the PC edition's only platform, and keeps a POSIX
//! branch so the core still builds for the phone:
//! - [`resolve`] is `Path.resolve()`: `ntpath.realpath`'s lexical `normpath`, then the final path of
//!   the longest prefix that exists, without the `\\?\` prefix.
//! - [`is_relative_to`] and [`relative_to`] compare as `WindowsPath` does, case-insensitively.
//! - [`os_error`] gives an `OSError`'s class and `str()`: `[WinError n] text: 'path'` for the Win32
//!   calls (`stat`, `unlink`, `replace`, `link`, `mkdir`, `chmod`, `scandir`) and
//!   `[Errno n] text: 'path'` for `open()`, with the class `OSError.__new__` picks from the errno.
//! - [`dumps`] writes JSON as `json.dump(indent=2)` and `json.dumps(ensure_ascii=False,
//!   separators=(', ', ': '))` do, floats as `repr` writes them.
//! - [`casefold`] is `str.casefold()`, from the 297 characters where it differs from `lower()` in
//!   Python 3.12's Unicode 15.0 and `char::to_lowercase` elsewhere.
//!
//! The port's own: a JSON file that will not parse carries `serde_json`'s message under Python's
//! class (`JSONDecodeError`), and a file read as text is read as UTF-8 (`read_text()` uses the
//! locale's code page; the receipts it reads are ASCII, as `write_json` writes them).

use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};

use crate::catalog::py_repr;
use crate::scan::{PyError, PyErrorDetail};

/// Which call raised an `OSError`, which fixes how Python words it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Call {
    /// A Win32 call: `[WinError n]` on Windows.
    Win,
    /// The C runtime's `open()`: `[Errno n]`.
    Crt,
}

/// Python's errno for a Windows error code (`PC/errmap.h`, as `OSError(None, None, None, code)`
/// reports it), `EINVAL` (22) for every code it does not list.
fn winerror_errno(code: i32) -> i32 {
    match code {
        2 | 3 | 15 | 18 | 53 | 67 | 161 | 206 => 2,
        4 => 24,
        5 | 16 | 19..=36 | 65 | 82 | 83 | 108 | 132 | 158 | 167 | 10013 => 13,
        6 | 114 | 130 => 9,
        7..=9 | 1816 => 12,
        10 => 7,
        11 | 188..=202 => 8,
        17 => 18,
        80 | 183 => 17,
        89 | 164 | 215 => 11,
        109 | 232 => 32,
        112 => 28,
        128 | 129 => 10,
        145 => 41,
        267 => 20,
        1113 => 42,
        10045 => 10045,
        _ => 22,
    }
}

/// `os.strerror(errno)` on Windows, for the errnos [`winerror_errno`] yields.
fn strerror(errno: i32) -> &'static str {
    match errno {
        2 => "No such file or directory",
        7 => "Arg list too long",
        8 => "Exec format error",
        9 => "Bad file descriptor",
        10 => "No child processes",
        11 => "Resource temporarily unavailable",
        12 => "Not enough space",
        13 => "Permission denied",
        17 => "File exists",
        18 => "Improper link",
        20 => "Not a directory",
        21 => "Is a directory",
        22 => "Invalid argument",
        24 => "Too many open files",
        28 => "No space left on device",
        32 => "Broken pipe",
        41 => "Directory not empty",
        42 => "Illegal byte sequence",
        _ => "Unknown error",
    }
}

/// The `OSError` subclass `OSError.__new__` picks for an errno.
fn errno_class(errno: i32) -> &'static str {
    match errno {
        1 | 13 => "PermissionError",
        2 => "FileNotFoundError",
        10 => "ChildProcessError",
        11 => "BlockingIOError",
        17 => "FileExistsError",
        20 => "NotADirectoryError",
        21 => "IsADirectoryError",
        32 => "BrokenPipeError",
        _ => "OSError",
    }
}

/// The errno Python gives `error` (on Windows mapped from its Win32 code).
pub fn errno(error: &io::Error) -> Option<i32> {
    let code = error.raw_os_error()?;
    Some(if cfg!(windows) {
        winerror_errno(code)
    } else {
        code
    })
}

/// The system's own text for `error`, as Python trims it: no ` (os error n)`, no trailing
/// whitespace or full stops.
fn system_text(error: &io::Error) -> String {
    let text = error.to_string();
    let text = match (error.raw_os_error(), text.rfind(" (os error ")) {
        (Some(_), Some(at)) => &text[..at],
        _ => text.as_str(),
    };
    text.trim_end_matches(|c: char| c <= ' ' || c == '.')
        .to_owned()
}

/// `OSError` as CPython raises it for `call` on `paths` (one, or the two of `replace`/`link`).
pub fn os_error(error: &io::Error, call: Call, paths: &[&Path]) -> PyError {
    let names: Vec<String> = paths
        .iter()
        .map(|p| py_repr(&p.display().to_string()))
        .collect();
    let suffix = match names.as_slice() {
        [] => String::new(),
        [one] => format!(": {one}"),
        [first, second, ..] => format!(": {first} -> {second}"),
    };
    let Some(code) = error.raw_os_error() else {
        return PyError::new("OSError", format!("{error}{suffix}"));
    };
    let number = errno(error).unwrap_or(code);
    let class = errno_class(number);
    if cfg!(windows) && call == Call::Win {
        return PyError::new(
            class,
            format!("[WinError {code}] {}{suffix}", system_text(error)),
        )
        .with_detail(PyErrorDetail::Os {
            errno: number,
            winerror: Some(code),
        });
    }
    let text = if cfg!(windows) {
        strerror(number).to_owned()
    } else {
        system_text(error)
    };
    PyError::new(class, format!("[Errno {number}] {text}{suffix}")).with_detail(PyErrorDetail::Os {
        errno: number,
        winerror: None,
    })
}

/// `pathlib._ignore_error`: the errors `exists()`, `is_file()` and `is_dir()` read as "no".
fn ignored(error: &io::Error) -> bool {
    if error.kind() == io::ErrorKind::NotFound {
        return true;
    }
    match error.raw_os_error() {
        Some(code) if cfg!(windows) => {
            matches!(code, 21 | 123 | 1921) || matches!(winerror_errno(code), 2 | 9 | 20)
        }
        Some(code) => matches!(code, 2 | 9 | 20 | 40),
        None => false,
    }
}

fn stat(path: &Path, follow: bool) -> Result<Option<fs::Metadata>, PyError> {
    let result = if follow {
        fs::metadata(path)
    } else {
        fs::symlink_metadata(path)
    };
    match result {
        Ok(meta) => Ok(Some(meta)),
        Err(error) if ignored(&error) => Ok(None),
        Err(error) => Err(os_error(&error, Call::Win, &[path])),
    }
}

/// `Path.exists()`.
pub fn exists(path: &Path) -> Result<bool, PyError> {
    Ok(stat(path, true)?.is_some())
}

/// `os.path.lexists`, as the last part of a `glob` checks a literal name.
pub fn lexists(path: &Path) -> Result<bool, PyError> {
    Ok(stat(path, false)?.is_some())
}

/// `Path.is_file()`.
pub fn is_file(path: &Path) -> Result<bool, PyError> {
    Ok(stat(path, true)?.is_some_and(|m| m.is_file()))
}

/// `Path.is_dir()`.
pub fn is_dir(path: &Path) -> Result<bool, PyError> {
    Ok(stat(path, true)?.is_some_and(|m| m.is_dir()))
}

/// `Path.is_symlink()`.
pub fn is_symlink(path: &Path) -> Result<bool, PyError> {
    Ok(stat(path, false)?.is_some_and(|m| m.file_type().is_symlink()))
}

/// `Path.stat().st_size`.
pub fn size(path: &Path) -> Result<u64, PyError> {
    fs::metadata(path)
        .map(|m| m.len())
        .map_err(|e| os_error(&e, Call::Win, &[path]))
}

/// `ntpath.normpath` / `posixpath.normpath` on an absolute path: no `.`, `..` folded.
fn normalize(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    let mut depth = 0usize;
    for part in path.components() {
        match part {
            Component::CurDir => {}
            Component::ParentDir => {
                if depth > 0 {
                    out.pop();
                    depth -= 1;
                }
            }
            Component::Normal(name) => {
                out.push(name);
                depth += 1;
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// `canonicalize`'s answer without Windows' verbatim prefix, as `realpath` strips it.
fn plain(path: PathBuf) -> PathBuf {
    let text = path.display().to_string();
    if let Some(rest) = text.strip_prefix(r"\\?\UNC\") {
        PathBuf::from(format!(r"\\{rest}"))
    } else if let Some(rest) = text.strip_prefix(r"\\?\") {
        PathBuf::from(rest)
    } else {
        path
    }
}

/// `Path.resolve()` (not strict).
pub fn resolve(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map(|cwd| cwd.join(path))
            .unwrap_or_else(|_| path.to_path_buf())
    };
    let normal = normalize(&absolute);
    let mut head = normal.clone();
    let mut tail = Vec::new();
    loop {
        if let Ok(found) = fs::canonicalize(&head) {
            let mut out = plain(found);
            for name in tail.iter().rev() {
                out.push(name);
            }
            return out;
        }
        match (head.file_name().map(ToOwned::to_owned), head.parent()) {
            (Some(name), Some(parent)) => {
                tail.push(name);
                head = parent.to_path_buf();
            }
            _ => return normal,
        }
    }
}

/// `str(path).lower()` on Windows (`WindowsPath`'s `_str_normcase`), the text elsewhere.
pub fn normcase(path: &Path) -> String {
    let text = path.display().to_string();
    if cfg!(windows) {
        text.to_lowercase()
    } else {
        text
    }
}

/// `path == other` for two `pathlib` paths.
pub fn same_path(path: &Path, other: &Path) -> bool {
    normcase(path) == normcase(other)
}

/// `path.is_relative_to(root)`: `root == path or root in path.parents`.
pub fn is_relative_to(path: &Path, root: &Path) -> bool {
    let key = normcase(root);
    path.ancestors()
        .any(|a| !a.as_os_str().is_empty() && normcase(a) == key)
}

/// `str(path.relative_to(root))`.
pub fn relative_to(path: &Path, root: &Path) -> Result<String, PyError> {
    let key = normcase(root);
    for ancestor in path.ancestors() {
        if !ancestor.as_os_str().is_empty() && normcase(ancestor) == key {
            let rest = path
                .strip_prefix(ancestor)
                .map(Path::to_path_buf)
                .unwrap_or_else(|_| {
                    let skip = ancestor.components().count();
                    path.components().skip(skip).collect()
                });
            return Ok(rest.display().to_string());
        }
    }
    Err(PyError::new(
        "ValueError",
        format!(
            "{} is not in the subpath of {}",
            py_repr(&path.display().to_string()),
            py_repr(&root.display().to_string())
        ),
    ))
}

/// The key `sorted()` orders `pathlib` paths by: their parts, lower-cased on Windows.
pub fn sort_key(path: &Path) -> Vec<String> {
    path.components()
        .map(|c| {
            let text = c.as_os_str().to_string_lossy().into_owned();
            if cfg!(windows) {
                text.to_lowercase()
            } else {
                text
            }
        })
        .collect()
}

/// `sorted(paths)`, or `sorted(paths, reverse=True)`.
pub fn sort_paths(paths: &mut [PathBuf], reverse: bool) {
    paths.sort_by_cached_key(|p| sort_key(p));
    if reverse {
        // `sorted(reverse=True)` keeps equal keys in their original order.
        let mut keyed: Vec<(Vec<String>, PathBuf)> = paths
            .iter()
            .rev()
            .map(|p| (sort_key(p), p.clone()))
            .collect();
        keyed.sort_by(|a, b| b.0.cmp(&a.0));
        for (slot, (_, path)) in paths.iter_mut().zip(keyed) {
            *slot = path;
        }
    }
}

/// `list(path.iterdir())`, in the directory's own order.
pub fn iterdir(path: &Path) -> Result<Vec<PathBuf>, PyError> {
    let reader = fs::read_dir(path).map_err(|e| os_error(&e, Call::Win, &[path]))?;
    let mut out = Vec::new();
    for item in reader {
        out.push(item.map_err(|e| os_error(&e, Call::Win, &[path]))?.path());
    }
    Ok(out)
}

/// `path.glob(f"*/{name}")`: each folder under `path` holding `name` (lexists), in directory
/// order. A folder that cannot be listed or tested is passed over, as `glob` does.
pub fn glob_children(path: &Path, name: &str) -> Vec<PathBuf> {
    let Ok(reader) = fs::read_dir(path) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for item in reader.flatten() {
        let folder = item.path();
        if !fs::metadata(&folder).is_ok_and(|m| m.is_dir()) {
            continue;
        }
        let candidate = folder.join(name);
        if lexists(&candidate).unwrap_or(false) {
            out.push(candidate);
        }
    }
    out
}

/// `path.glob(f"*/*{suffix}")`: the entries of each folder under `path` whose name ends with
/// `suffix` (case-insensitively on Windows), in directory order.
pub fn glob_suffix(path: &Path, suffix: &str) -> Vec<PathBuf> {
    let suffix = if cfg!(windows) {
        suffix.to_lowercase()
    } else {
        suffix.to_owned()
    };
    let Ok(reader) = fs::read_dir(path) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for item in reader.flatten() {
        let folder = item.path();
        if !fs::metadata(&folder).is_ok_and(|m| m.is_dir()) {
            continue;
        }
        let Ok(inner) = fs::read_dir(&folder) else {
            continue;
        };
        for entry in inner.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            let name = if cfg!(windows) {
                name.to_lowercase()
            } else {
                name
            };
            if name.ends_with(&suffix) {
                out.push(entry.path());
            }
        }
    }
    out
}

/// Every file under `path` (`path.rglob('*')`, files only), with its size.
pub fn tree_size(path: &Path) -> Result<u64, PyError> {
    let mut total = 0;
    let mut stack = vec![path.to_path_buf()];
    while let Some(folder) = stack.pop() {
        for child in iterdir(&folder)? {
            let meta =
                fs::symlink_metadata(&child).map_err(|e| os_error(&e, Call::Win, &[&child]))?;
            if meta.is_dir() {
                stack.push(child);
            } else if is_file(&child)? {
                total += size(&child)?;
            }
        }
    }
    Ok(total)
}

/// `installer.sha256_file`.
pub fn sha256_file(path: &Path) -> Result<String, PyError> {
    let mut file = File::open(path).map_err(|e| os_error(&e, Call::Crt, &[path]))?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0; 1 << 20];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|e| os_error(&e, Call::Crt, &[path]))?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

/// `json.loads(path.read_text(encoding=...))`; `sig` strips a leading BOM (`utf-8-sig`). The runtime
/// reads receipts with the locale's encoding, which the port takes as UTF-8: receipts are ASCII.
pub fn read_json(path: &Path, sig: bool) -> Result<Value, PyError> {
    let bytes = fs::read(path).map_err(|e| os_error(&e, Call::Crt, &[path]))?;
    let bytes = if sig {
        bytes.strip_prefix(b"\xef\xbb\xbf").unwrap_or(&bytes)
    } else {
        &bytes
    };
    let text = std::str::from_utf8(bytes).map_err(|error| {
        PyError::new(
            "UnicodeDecodeError",
            format!("'utf-8' codec can't decode bytes: {error}"),
        )
        .with_detail(PyErrorDetail::Utf8(bytes.to_vec()))
    })?;
    // Text mode reads `\r\n` and a lone `\r` as `\n`; Python's error positions count the result.
    let text = text.replace("\r\n", "\n").replace('\r', "\n");
    serde_json::from_str(&text).map_err(|error| {
        // Where Python would accept what serde refuses (`NaN`, a lone surrogate), serde's wording.
        let message = crate::pyjson::decode_error(&text).unwrap_or_else(|| error.to_string());
        PyError::new("JSONDecodeError", message).with_detail(PyErrorDetail::Json(text))
    })
}

/// Write `text` as a text-mode `open('w')` does: `\n` becomes `\r\n` on Windows.
pub fn text_bytes(text: &str) -> Vec<u8> {
    if cfg!(windows) {
        text.replace('\n', "\r\n").into_bytes()
    } else {
        text.as_bytes().to_vec()
    }
}

/// `path.write_text(text, encoding='utf-8')`.
pub fn write_text(path: &Path, text: &str) -> Result<(), PyError> {
    let mut file = File::create(path).map_err(|e| os_error(&e, Call::Crt, &[path]))?;
    file.write_all(&text_bytes(text))
        .map_err(|e| os_error(&e, Call::Crt, &[path]))
}

/// `path.mkdir(parents=True, exist_ok=...)`.
pub fn mkdir(path: &Path, exist_ok: bool) -> Result<(), PyError> {
    if is_dir(path)? {
        if exist_ok {
            return Ok(());
        }
        return Err(os_error(
            &io::Error::from_raw_os_error(if cfg!(windows) { 183 } else { 17 }),
            Call::Win,
            &[path],
        ));
    }
    fs::create_dir_all(path).map_err(|e| os_error(&e, Call::Win, &[path]))
}

/// `shutil.copytree(source, target)`, or with `copy_function=os.link` when `link` is set: every
/// file and folder error is collected and raised together as `shutil.Error` (an `OSError`), whose
/// `str()` is the list of `(source, target, reason)` triples. The port's own: the folders'
/// timestamps are not copied (`copystat`), and an error listing a folder is raised at once.
pub fn copytree(source: &Path, target: &Path, link: bool) -> Result<(), PyError> {
    let mut errors = Vec::new();
    copy_into(source, target, link, &mut errors)?;
    if errors.is_empty() {
        return Ok(());
    }
    let items: Vec<String> = errors
        .iter()
        .map(|(from, to, why): &(PathBuf, PathBuf, String)| {
            format!(
                "({}, {}, {})",
                py_repr(&from.display().to_string()),
                py_repr(&to.display().to_string()),
                py_repr(why)
            )
        })
        .collect();
    Err(PyError::new("Error", format!("[{}]", items.join(", "))))
}

fn copy_into(
    source: &Path,
    target: &Path,
    link: bool,
    errors: &mut Vec<(PathBuf, PathBuf, String)>,
) -> Result<(), PyError> {
    let mut entries = Vec::new();
    for entry in fs::read_dir(source).map_err(|e| os_error(&e, Call::Win, &[source]))? {
        entries.push(entry.map_err(|e| os_error(&e, Call::Win, &[source]))?);
    }
    if is_dir(target)? || lexists(target)? {
        return Err(os_error(
            &io::Error::from_raw_os_error(if cfg!(windows) { 183 } else { 17 }),
            Call::Win,
            &[target],
        ));
    }
    fs::create_dir_all(target).map_err(|e| os_error(&e, Call::Win, &[target]))?;
    for entry in entries {
        let from = entry.path();
        let to = target.join(entry.file_name());
        let is_folder = entry
            .file_type()
            .map(|kind| kind.is_dir())
            .map_err(|e| os_error(&e, Call::Win, &[&from]))?;
        if is_folder {
            match copy_into(&from, &to, link, errors) {
                Err(error) if error.class == "Error" => errors.push((from, to, error.message)),
                other => other?,
            }
            continue;
        }
        let copied = if link {
            fs::hard_link(&from, &to).map_err(|e| os_error(&e, Call::Win, &[&from, &to]))
        } else {
            fs::copy(&from, &to)
                .map(|_| ())
                .map_err(|e| os_error(&e, Call::Win, &[&from, &to]))
        };
        if let Err(error) = copied {
            errors.push((from, to, error.message));
        }
    }
    Ok(())
}

/// `shutil.rmtree(path)`. The port's own: read-only files are removed too.
pub fn rmtree(path: &Path) -> Result<(), PyError> {
    fs::remove_dir_all(path).map_err(|e| os_error(&e, Call::Win, &[path]))
}

/// `uuid.uuid4().hex`'s shape: 32 lowercase hex digits, from the standard library's random seed.
pub fn random_hex() -> String {
    use std::hash::{BuildHasher, Hasher};
    let state = std::collections::hash_map::RandomState::new();
    let mut out = String::with_capacity(32);
    for part in 0..2u8 {
        let mut hasher = state.build_hasher();
        hasher.write_u8(part);
        hasher.write_u128(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default(),
        );
        out.push_str(&format!("{:016x}", hasher.finish()));
    }
    out
}

/// `os.replace(source, target)`.
pub fn replace(source: &Path, target: &Path) -> Result<(), PyError> {
    fs::rename(source, target).map_err(|e| os_error(&e, Call::Win, &[source, target]))
}

/// `path.unlink()`.
pub fn unlink(path: &Path) -> Result<(), PyError> {
    fs::remove_file(path).map_err(|e| os_error(&e, Call::Win, &[path]))
}

/// `adaptive._make_writable`: `os.chmod(path, path.stat().st_mode | stat.S_IWRITE)`.
pub fn make_writable(path: &Path) -> Result<(), PyError> {
    let meta = fs::metadata(path).map_err(|e| os_error(&e, Call::Win, &[path]))?;
    let mut permissions = meta.permissions();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        permissions.set_mode(permissions.mode() | 0o200);
    }
    // `stat.S_IWRITE` on Windows clears the read-only attribute, which is all `chmod` can set.
    #[cfg(not(unix))]
    #[allow(clippy::permissions_set_readonly_false)]
    permissions.set_readonly(false);
    fs::set_permissions(path, permissions).map_err(|e| os_error(&e, Call::Win, &[path]))
}

// ---------------------------------------------------------------------------------------------
// Strings

include!("pyos_casefold.rs");

/// `str.casefold()`.
pub fn casefold(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match CASEFOLD.binary_search_by_key(&c, |&(from, _)| from) {
            Ok(at) => out.push_str(CASEFOLD[at].1),
            Err(_) => out.extend(c.to_lowercase()),
        }
    }
    out
}

/// `str.isdecimal()` for ASCII digits; any other character counts as not decimal (the port's
/// own: Python also accepts the other Unicode `Nd` digits).
pub fn is_ascii_decimal(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit())
}

// ---------------------------------------------------------------------------------------------
// Python values held as JSON

/// `type(value).__name__`.
pub fn type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) if n.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// `bool(value)`.
pub fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// `value[key]` for a string key.
pub fn subscript<'a>(value: &'a Value, key: &str) -> Result<&'a Value, PyError> {
    match value {
        Value::Object(map) => map.get(key).ok_or_else(|| PyError::key(key)),
        Value::Array(_) => Err(PyError::new(
            "TypeError",
            "list indices must be integers or slices, not str",
        )),
        Value::String(_) => Err(PyError::new(
            "TypeError",
            "string indices must be integers, not 'str'",
        )),
        other => Err(PyError::new(
            "TypeError",
            format!("'{}' object is not subscriptable", type_name(other)),
        )),
    }
}

/// `value.get(key)` (`None` when missing).
pub fn get<'a>(value: &'a Value, key: &str) -> Result<Option<&'a Value>, PyError> {
    match value {
        Value::Object(map) => Ok(map.get(key)),
        other => Err(PyError::new(
            "AttributeError",
            format!("'{}' object has no attribute 'get'", type_name(other)),
        )),
    }
}

/// `value.get(key)` with `None` as a JSON null.
pub fn get_or_null(value: &Value, key: &str) -> Result<Value, PyError> {
    Ok(get(value, key)?.cloned().unwrap_or(Value::Null))
}

/// `iter(value)`: a list's items, a dict's keys, a string's characters.
pub fn iterate(value: &Value) -> Result<Vec<Value>, PyError> {
    match value {
        Value::Array(items) => Ok(items.clone()),
        Value::Object(map) => Ok(map.keys().map(|k| Value::String(k.clone())).collect()),
        Value::String(text) => Ok(text.chars().map(|c| Value::String(c.to_string())).collect()),
        other => Err(PyError::new(
            "TypeError",
            format!("'{}' object is not iterable", type_name(other)),
        )),
    }
}

/// `isinstance(value, int)` (`bool` included, as in Python).
pub fn is_int(value: &Value) -> bool {
    matches!(value, Value::Bool(_)) || matches!(value, Value::Number(n) if !n.is_f64())
}

/// `str(value)`.
pub fn py_str(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(n) => number_repr(n),
        other => python_repr(other),
    }
}

/// `repr(value)` for the containers [`py_str`] meets.
fn python_repr(value: &Value) -> String {
    match value {
        Value::String(text) => py_repr(text),
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(python_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(map) => format!(
            "{{{}}}",
            map.iter()
                .map(|(k, v)| format!("{}: {}", py_repr(k), python_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        other => py_str(other),
    }
}

/// `format(value, ',')` for an int (Python's thousands separator), `str()` otherwise.
pub fn thousands(value: &Value) -> String {
    let text = match value {
        Value::Number(n) if !n.is_f64() => n.to_string(),
        Value::Bool(b) => u8::from(*b).to_string(),
        other => return py_str(other),
    };
    let (sign, digits) = match text.strip_prefix('-') {
        Some(rest) => ("-", rest),
        None => ("", text.as_str()),
    };
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    format!("{sign}{out}")
}

/// `float.__repr__`.
fn float_repr(value: f64) -> String {
    if value.is_nan() {
        return "NaN".to_owned();
    }
    if value.is_infinite() {
        return if value > 0.0 { "Infinity" } else { "-Infinity" }.to_owned();
    }
    if value == 0.0 {
        return if value.is_sign_negative() {
            "-0.0"
        } else {
            "0.0"
        }
        .to_owned();
    }
    // `{:e}` gives the shortest digits that round-trip, as `repr` uses.
    let scientific = format!("{value:e}");
    let (mantissa, exponent) = scientific.split_once('e').unwrap_or((&scientific, "0"));
    let exponent: i32 = exponent.parse().unwrap_or(0);
    let (sign, mantissa) = match mantissa.strip_prefix('-') {
        Some(rest) => ("-", rest),
        None => ("", mantissa),
    };
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    if (-4..16).contains(&exponent) {
        let point = exponent + 1;
        let body = if point <= 0 {
            format!("0.{}{}", "0".repeat(point.unsigned_abs() as usize), digits)
        } else if point as usize >= digits.len() {
            format!("{}{}.0", digits, "0".repeat(point as usize - digits.len()))
        } else {
            format!(
                "{}.{}",
                &digits[..point as usize],
                &digits[point as usize..]
            )
        };
        return format!("{sign}{body}");
    }
    let lead = &digits[..1];
    let rest = &digits[1..];
    let mantissa = if rest.is_empty() {
        lead.to_owned()
    } else {
        format!("{lead}.{rest}")
    };
    let exp_sign = if exponent < 0 { '-' } else { '+' };
    format!("{sign}{mantissa}e{exp_sign}{:02}", exponent.unsigned_abs())
}

fn number_repr(number: &Number) -> String {
    if number.is_f64() {
        float_repr(number.as_f64().unwrap_or(0.0))
    } else {
        number.to_string()
    }
}

/// How [`dumps`] lays a value out.
#[derive(Debug, Clone, Copy)]
pub enum Layout {
    /// `json.dump(value, f, indent=2)`: ASCII only, `,` and `: `, one item per line.
    Indent2,
    /// `json.dumps(value, ensure_ascii=False, separators=(', ', ': '))`.
    Inline,
}

fn dump_string(text: &str, ascii: bool, out: &mut String) {
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            c if c < ' ' => out.push_str(&format!("\\u{:04x}", u32::from(c))),
            c if ascii && !c.is_ascii() => {
                let mut units = [0u16; 2];
                for unit in c.encode_utf16(&mut units) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

fn dump(value: &Value, layout: Layout, level: usize, out: &mut String) {
    let ascii = matches!(layout, Layout::Indent2);
    let (open_sep, item_sep, close_sep) = match layout {
        Layout::Indent2 => (
            format!("\n{}", "  ".repeat(level + 1)),
            format!(",\n{}", "  ".repeat(level + 1)),
            format!("\n{}", "  ".repeat(level)),
        ),
        Layout::Inline => (String::new(), ", ".to_owned(), String::new()),
    };
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(&number_repr(n)),
        Value::String(text) => dump_string(text, ascii, out),
        Value::Array(items) if items.is_empty() => out.push_str("[]"),
        Value::Array(items) => {
            out.push('[');
            out.push_str(&open_sep);
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(&item_sep);
                }
                dump(item, layout, level + 1, out);
            }
            out.push_str(&close_sep);
            out.push(']');
        }
        Value::Object(map) if map.is_empty() => out.push_str("{}"),
        Value::Object(map) => {
            out.push('{');
            out.push_str(&open_sep);
            for (i, (key, item)) in map.iter().enumerate() {
                if i > 0 {
                    out.push_str(&item_sep);
                }
                dump_string(key, ascii, out);
                out.push_str(": ");
                dump(item, layout, level + 1, out);
            }
            out.push_str(&close_sep);
            out.push('}');
        }
    }
}

/// `json.dumps` with the layout's arguments.
pub fn dumps(value: &Value, layout: Layout) -> String {
    let mut out = String::new();
    dump(value, layout, 0, &mut out);
    out
}

/// A JSON object from `(key, value)` pairs, in order.
pub fn object<const N: usize>(pairs: [(&str, Value); N]) -> Map<String, Value> {
    pairs.into_iter().map(|(k, v)| (k.to_owned(), v)).collect()
}

/// A path as a JSON string, as `str(path)` gives it.
pub fn path_value(path: &Path) -> Value {
    Value::String(path.display().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn floats_print_as_repr() {
        for (value, text) in [
            (1.0, "1.0"),
            (0.1, "0.1"),
            (1e16, "1e+16"),
            (1.5e-5, "1.5e-05"),
            (0.0001, "0.0001"),
            (123456789012345.6, "123456789012345.6"),
            (-2.5, "-2.5"),
        ] {
            assert_eq!(float_repr(value), text);
        }
    }

    #[test]
    fn dumps_matches_json_module() {
        let value = json!({"a": [1, "é😀", null], "b": {}, "c": []});
        assert_eq!(
            dumps(&value, Layout::Indent2),
            "{\n  \"a\": [\n    1,\n    \"\\u00e9\\ud83d\\ude00\",\n    null\n  ],\n  \"b\": {},\n  \"c\": []\n}"
        );
        assert_eq!(
            dumps(&value, Layout::Inline),
            "{\"a\": [1, \"é😀\", null], \"b\": {}, \"c\": []}"
        );
    }

    #[test]
    fn casefold_folds_past_lower() {
        assert_eq!(casefold("Straße ΣΑΣ"), "strasse σασ");
        assert_eq!(casefold("ﬁ"), "fi");
    }

    #[test]
    fn thousands_separates() {
        assert_eq!(thousands(&json!(1234567)), "1,234,567");
        assert_eq!(thousands(&json!(12)), "12");
        assert_eq!(thousands(&json!(-1000)), "-1,000");
    }

    #[test]
    fn reverse_sort_is_stable() {
        let mut paths = vec![PathBuf::from("b"), PathBuf::from("a"), PathBuf::from("c")];
        sort_paths(&mut paths, true);
        assert_eq!(
            paths,
            [PathBuf::from("c"), PathBuf::from("b"), PathBuf::from("a")]
        );
    }
}
