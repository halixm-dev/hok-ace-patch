//! The game's own QtsVFS for the PC edition (ADR-021): [`DllLoader`] loads the installed
//! `QtskDB.dll` and `QtsVFS.dll` as `wxq_patch.installer._load_qtsvfs` does, and its [`Dll`]
//! calls them with the argument types the runtime gives ctypes.
//!
//! The workspace's one crate with `unsafe`: every call into the DLLs is here, and nothing else.
//! `hokace-core` holds the logic (`package_metadata::query_package_hash`,
//! `native_verify::verify_staged_package`) over the [`QtsVfs`] trait.
//!
//! As under ctypes, the libraries stay loaded for the life of the process, and each load adds
//! the DLL folder to the search path (`os.add_dll_directory`) until the [`Dll`] is dropped.
//! The port's own: a DLL that will not load raises `OSError` with the loader's text.

pub use hokace_core::package_metadata::{Loader, QtsVfs};

#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use windows::{Dll, DllLoader};

#[cfg(not(windows))]
mod other {
    use std::path::Path;

    use hokace_core::package_metadata::{Loader, QtsVfs};
    use hokace_core::scan::PyError;

    /// QtsVFS exists only on Windows; every load is refused.
    pub struct DllLoader;

    /// Never constructed off Windows.
    pub enum Dll {}

    impl Loader for DllLoader {
        type Api = Dll;
        fn load(&mut self, bin_dir: &Path) -> Result<Dll, PyError> {
            Err(PyError::new(
                "OSError",
                format!("QtsVFS loads only on Windows: {}", bin_dir.display()),
            ))
        }
    }

    impl QtsVfs for Dll {
        fn require(&mut self, _: &[&str]) -> Result<(), PyError> {
            match *self {}
        }
        fn last_error(&mut self) -> i32 {
            match *self {}
        }
        fn create_system(&mut self, _: &[u8], _: &[u8], _: &[u8]) -> bool {
            match *self {}
        }
        fn describe(&mut self, _: &[u8], _: &[u8], _: bool) -> i32 {
            match *self {}
        }
        fn set_prime(&mut self, _: i32, _: bool) -> bool {
            match *self {}
        }
        fn mount(&mut self, _: i32) -> bool {
            match *self {}
        }
        fn new_info(&mut self) -> usize {
            match *self {}
        }
        fn query_info(&mut self, _: i32, _: usize) -> bool {
            match *self {}
        }
        fn info_hash(&mut self, _: usize) -> u64 {
            match *self {}
        }
        fn delete_info(&mut self, _: usize) {
            match *self {}
        }
        fn release(&mut self, _: i32) {
            match *self {}
        }
        fn destroy(&mut self, _: &[u8]) {
            match *self {}
        }
        fn file_length(&mut self, _: &[u8], _: u64) -> u32 {
            match *self {}
        }
        fn open_file(&mut self, _: &[u8], _: u64) -> usize {
            match *self {}
        }
        fn read(&mut self, _: &mut [u8], _: usize) -> u32 {
            match *self {}
        }
        fn close_file(&mut self, _: usize) {
            match *self {}
        }
    }
}
#[cfg(not(windows))]
pub use other::{Dll, DllLoader};
