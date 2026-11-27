//! The DLL calls on Windows, through `libloading`.

use std::ffi::{CString, c_char, c_void};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use hokace_core::package_metadata::{Loader, QtsVfs};
use hokace_core::scan::PyError;
use libloading::os::windows::{
    LOAD_LIBRARY_SEARCH_DEFAULT_DIRS, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR, Library,
};
use windows_sys::Win32::System::LibraryLoader::{AddDllDirectory, RemoveDllDirectory};

/// Every library loaded so far, kept loaded: ctypes never unloads a `CDLL`, so QtsVFS keeps its
/// process-wide state between calls.
static LIBRARIES: Mutex<Vec<(PathBuf, Library)>> = Mutex::new(Vec::new());

type Text = *const c_char;
type Ptr = *mut c_void;

/// The entry points, each with the signature the runtime declares to ctypes (`c_bool` is a byte,
/// read as nonzero). `None` where the DLL lacks the name.
#[derive(Default)]
struct Calls {
    last_error: Option<unsafe extern "C" fn() -> i32>,
    create_system: Option<unsafe extern "C" fn(Text, Text, Text, Text) -> u8>,
    describe: Option<unsafe extern "C" fn(Text, Text, u8) -> i32>,
    set_prime: Option<unsafe extern "C" fn(i32, u8) -> u8>,
    mount: Option<unsafe extern "C" fn(i32, i32, i32) -> u8>,
    query_info: Option<unsafe extern "C" fn(i32, i32, Ptr) -> u8>,
    new_info: Option<unsafe extern "C" fn() -> Ptr>,
    delete_info: Option<unsafe extern "C" fn(Ptr)>,
    info_hash: Option<unsafe extern "C" fn(Ptr) -> u64>,
    release: Option<unsafe extern "C" fn(i32)>,
    destroy: Option<unsafe extern "C" fn(Text)>,
    file_length: Option<unsafe extern "C" fn(Text, u64) -> u32>,
    open_file: Option<unsafe extern "C" fn(Text, u64, Text) -> Ptr>,
    read: Option<unsafe extern "C" fn(Ptr, u32, u32, Ptr) -> u32>,
    close_file: Option<unsafe extern "C" fn(Ptr) -> i32>,
}

/// Loads the game's QtsVFS from its DLL folder.
#[derive(Debug, Default)]
pub struct DllLoader;

/// A loaded QtsVFS. Dropping it removes the DLL folder from the search path again.
pub struct Dll {
    calls: Calls,
    present: Vec<&'static str>,
    cookie: Ptr,
}

fn load_error(path: &Path, error: impl std::fmt::Display) -> PyError {
    PyError::new("OSError", format!("{error}: {}", path.display()))
}

/// `ctypes.CDLL(str(path))`: a full path, its folder searched for its dependencies.
fn open(path: &Path) -> Result<Library, PyError> {
    let load = || {
        // SAFETY: loading runs the DLL's own initializers. These are the game's installed
        // libraries, loaded with the flags ctypes uses for a path, as the runtime loads them.
        unsafe {
            Library::load_with_flags(
                path,
                LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR,
            )
        }
        .map_err(|error| load_error(path, error))
    };
    let library = load()?;
    let mut libraries = LIBRARIES.lock().unwrap_or_else(|e| e.into_inner());
    if !libraries.iter().any(|(known, _)| known == path) {
        // A second reference to the same module, never released.
        libraries.push((path.to_owned(), load()?));
    }
    Ok(library)
}

/// The symbol `name`, when the library has it.
fn symbol<T: Copy>(library: &Library, name: &str) -> Option<T> {
    let name = CString::new(name).ok()?;
    // SAFETY: each `T` is the signature the runtime declares for `name` to ctypes, and the library
    // stays loaded for the process (`LIBRARIES`), so the pointer outlives every call.
    unsafe { library.get::<T>(name.as_bytes_with_nul()) }
        .ok()
        .map(|symbol| *symbol)
}

impl Loader for DllLoader {
    type Api = Dll;

    fn load(&mut self, bin_dir: &Path) -> Result<Dll, PyError> {
        let wide: Vec<u16> = bin_dir
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();
        // SAFETY: `wide` is a NUL-terminated UTF-16 path that lives across the call.
        let cookie = unsafe { AddDllDirectory(wide.as_ptr()) };
        if cookie.is_null() {
            return Err(load_error(bin_dir, std::io::Error::last_os_error()));
        }
        let dll = Dll {
            calls: Calls::default(),
            present: Vec::new(),
            cookie,
        };
        open(&bin_dir.join("QtskDB.dll"))?;
        let library = open(&bin_dir.join("QtsVFS.dll"))?;
        for name in ["VFS_Initialize_Scripted", "VFS_Initialize"] {
            if let Some(initialize) = symbol::<unsafe extern "C" fn() -> i32>(&library, name) {
                // SAFETY: the runtime calls each initializer it finds, with no arguments.
                unsafe { initialize() };
            }
        }
        let mut dll = dll;
        macro_rules! bind {
            ($($field:ident = $name:literal),* $(,)?) => {
                $(
                    dll.calls.$field = symbol(&library, $name);
                    if dll.calls.$field.is_some() {
                        dll.present.push($name);
                    }
                )*
            };
        }
        bind!(
            last_error = "VFS_GetLastError",
            create_system = "VFS_CreateSystem",
            describe = "VFS_CreatePackageDescription",
            set_prime = "VFS_PackageDescriptionSetHasPrimePackge",
            mount = "VFS_MountPackage",
            query_info = "VFS_QueryPackageInfo",
            new_info = "CSharp_new_QTSPatchInfo",
            delete_info = "CSharp_delete_QTSPatchInfo",
            info_hash = "CSharp_QTSPatchInfo_cur_package_hash_get",
            release = "VFS_ReleasePackageDescription",
            destroy = "VFS_DestorySystem",
            file_length = "VFS_GetFileLengthByHash",
            open_file = "VFS_OpenFileByHash",
            read = "VFS_Read",
            close_file = "VFS_CloseFile",
        );
        Ok(dll)
    }
}

impl Drop for Dll {
    fn drop(&mut self) {
        // SAFETY: `cookie` came from `AddDllDirectory` and is removed once.
        unsafe { RemoveDllDirectory(self.cookie) };
    }
}

/// A `c_char_p` from bytes: ctypes passes the bytes object's NUL-terminated buffer, so QtsVFS
/// reads up to the first NUL.
fn text(bytes: &[u8]) -> CString {
    let end = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
    CString::new(&bytes[..end]).expect("cut at the first NUL")
}

impl QtsVfs for Dll {
    fn require(&mut self, symbols: &[&str]) -> Result<(), PyError> {
        match symbols.iter().find(|name| !self.present.contains(name)) {
            Some(name) => Err(PyError::new(
                "AttributeError",
                format!("function '{name}' not found"),
            )),
            None => Ok(()),
        }
    }

    fn last_error(&mut self) -> i32 {
        // SAFETY: `VFS_GetLastError()` takes nothing and returns `c_int`.
        self.calls.last_error.map_or(0, |f| unsafe { f() })
    }

    fn create_system(&mut self, system: &[u8], root: &[u8], scratch: &[u8]) -> bool {
        let (system, root, scratch) = (text(system), text(root), text(scratch));
        self.calls.create_system.is_some_and(|f| {
            // SAFETY: four NUL-terminated strings that live across the call.
            unsafe { f(system.as_ptr(), root.as_ptr(), scratch.as_ptr(), scratch.as_ptr()) != 0 }
        })
    }

    fn describe(&mut self, system: &[u8], package: &[u8], internal: bool) -> i32 {
        let (system, package) = (text(system), text(package));
        self.calls.describe.map_or(-1, |f| {
            // SAFETY: two NUL-terminated strings that live across the call, and a `c_bool`.
            unsafe { f(system.as_ptr(), package.as_ptr(), u8::from(internal)) }
        })
    }

    fn set_prime(&mut self, handle: i32, prime: bool) -> bool {
        // SAFETY: a package description handle and a `c_bool`.
        self.calls
            .set_prime
            .is_some_and(|f| unsafe { f(handle, u8::from(prime)) != 0 })
    }

    fn mount(&mut self, handle: i32) -> bool {
        // SAFETY: a package description handle and the runtime's two zero arguments.
        self.calls
            .mount
            .is_some_and(|f| unsafe { f(handle, 0, 0) != 0 })
    }

    fn new_info(&mut self) -> usize {
        // SAFETY: the constructor takes nothing and returns a pointer, or NULL.
        self.calls.new_info.map_or(0, |f| unsafe { f() } as usize)
    }

    fn query_info(&mut self, handle: i32, info: usize) -> bool {
        // SAFETY: `info` is a live `QTSPatchInfo` from `new_info`.
        self.calls
            .query_info
            .is_some_and(|f| unsafe { f(handle, 0, info as Ptr) != 0 })
    }

    fn info_hash(&mut self, info: usize) -> u64 {
        // SAFETY: `info` is a live `QTSPatchInfo` from `new_info`.
        self.calls
            .info_hash
            .map_or(0, |f| unsafe { f(info as Ptr) })
    }

    fn delete_info(&mut self, info: usize) {
        if let Some(f) = self.calls.delete_info {
            // SAFETY: `info` came from `new_info` and is deleted once.
            unsafe { f(info as Ptr) };
        }
    }

    fn release(&mut self, handle: i32) {
        if let Some(f) = self.calls.release {
            // SAFETY: a package description handle, released once.
            unsafe { f(handle) };
        }
    }

    fn destroy(&mut self, system: &[u8]) {
        let system = text(system);
        if let Some(f) = self.calls.destroy {
            // SAFETY: a NUL-terminated system name that lives across the call.
            unsafe { f(system.as_ptr()) };
        }
    }

    fn file_length(&mut self, system: &[u8], hash: u64) -> u32 {
        let system = text(system);
        // SAFETY: a NUL-terminated system name that lives across the call, and a hash.
        self.calls
            .file_length
            .map_or(0, |f| unsafe { f(system.as_ptr(), hash) })
    }

    fn open_file(&mut self, system: &[u8], hash: u64) -> usize {
        let (system, mode) = (text(system), text(b"rb"));
        self.calls.open_file.map_or(0, |f| {
            // SAFETY: two NUL-terminated strings that live across the call, and a hash.
            unsafe { f(system.as_ptr(), hash, mode.as_ptr()) as usize }
        })
    }

    fn read(&mut self, buffer: &mut [u8], file: usize) -> u32 {
        let Ok(size) = u32::try_from(buffer.len()) else {
            return 0;
        };
        self.calls.read.map_or(0, |f| {
            // SAFETY: `buffer` holds `size` writable bytes, read as `size` items of one byte from
            // a file `open_file` returned; QtsVFS writes at most that many.
            unsafe { f(buffer.as_mut_ptr().cast(), 1, size, file as Ptr) }
        })
    }

    fn close_file(&mut self, file: usize) {
        if let Some(f) = self.calls.close_file {
            // SAFETY: a file `open_file` returned, closed once.
            unsafe { f(file as Ptr) };
        }
    }
}
